"""
Servicio: emisión masiva de DTE a partir de una planilla.

`parse()` entrega los documentos de la planilla, parseados por la
biblioteca (CSV o XLSX). Se llama en la solicitud: ante un error, el
usuario lo ve en el formulario y no se emite nada. Si sale bien, los
documentos se guardan (`save_documentos()`) y `process()`, el cuerpo de
la tarea en segundo plano, los emite uno por uno y avisa el resultado
por correo.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from django.conf import settings
from django.core import signing
from django.core.cache import cache as django_cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone
from libredte_lib_sdk.exceptions import LibreDteApiError, LibreDteSdkError

from apps.libredte.models import Contribuyente
from apps.libredte.services.exceptions import ServiceError, wrap
from apps.libredte.services.libredte_backend import get_backend

from ..models import Borrador, DteEmitido, TipoDte
from ..utils.spreadsheet import write_rows
from . import biller, document_renderer

if TYPE_CHECKING:
    from django.contrib.auth.models import User


# Duración máxima del bloqueo contra doble envío, por si el worker cae
# antes de liberarlo (igual al `visibility_timeout` del broker).
_BLOQUEO_SEGUNDOS = 3600

# Códigos de resultado de la emisión. Los demás números no se usan: eran
# del formato de la planilla (ahora lo valida la biblioteca al parsear) y
# del envío del DTE por correo al receptor, que no se hace.
CODIGO_BORRADOR = 4
CODIGO_EMISION = 5

GLOSAS_CODIGO = {
    CODIGO_BORRADOR: 'No fue posible crear el borrador del documento',
    CODIGO_EMISION: 'No fue posible emitir el DTE real desde el borrador',
}

# Estrategia de la biblioteca para cada formato de planilla. `xlsx` solo
# existe en la API Pro: con la Core, la API informa el error.
_ESTRATEGIAS = {'csv': 'spreadsheet.csv', 'xlsx': 'spreadsheet.xlsx'}


@dataclass(frozen=True)
class Resultado:
    """
    Qué pasó con un documento de la planilla.

    `numero` es la posición del documento en la planilla (desde 1). Viene
    lleno `emitido_pk` si se emitió el DTE real, o `borrador_pk` si quedó
    como borrador.
    """

    numero: int
    tipo_dte: str
    folio_planilla: str
    rut_receptor: str
    codigo: int | None
    glosa: str
    borrador_pk: int | None = None
    emitido_pk: int | None = None

    @property
    def ok(self) -> bool:
        """
        `True` si el documento se procesó sin error.

        :return: `True` si el documento no tiene código de error.
        :rtype: bool
        """
        return self.codigo is None


class BulkBillingInProgressError(ServiceError):
    """La misma planilla ya está encolada o procesándose."""


def acquire_lock(contribuyente_id: int, huella: str) -> None:
    """
    Bloquea una planilla para que no se encole dos veces a la vez.

    Es por contribuyente y por huella de los documentos (el nombre del
    archivo que deja `save_documentos()`, sin extensión). Lo libera la
    tarea al terminar (`release_lock()`) o vence solo tras
    `_BLOQUEO_SEGUNDOS`.

    :param contribuyente_id: El emisor de los documentos.
    :type contribuyente_id: int
    :param huella: La huella de los documentos que se van a encolar.
    :type huella: str
    :raises BulkBillingInProgressError: Si ese mismo archivo ya está encolado
        o procesándose.
    """
    tomado = django_cache.add(
        _lock_key(contribuyente_id, huella),
        True,
        timeout=_BLOQUEO_SEGUNDOS,
    )
    if not tomado:
        raise BulkBillingInProgressError(
            'La planilla ya se está procesando, no se volvió a encolar.',
        )


def release_lock(contribuyente_id: int, huella: str) -> None:
    """
    Libera el bloqueo de una planilla (ver `acquire_lock()`).

    :param contribuyente_id: El emisor de los documentos.
    :type contribuyente_id: int
    :param huella: La huella de los documentos que se habían bloqueado.
    :type huella: str
    """
    django_cache.delete(_lock_key(contribuyente_id, huella))


def _lock_key(contribuyente_id: int, huella: str) -> str:
    """
    Llave de caché del bloqueo de una planilla.

    :param contribuyente_id: El emisor de los documentos.
    :type contribuyente_id: int
    :param huella: La huella de los documentos.
    :type huella: str
    :return: La llave del bloqueo.
    :rtype: str
    """
    return f'emision_masiva:{contribuyente_id}:{huella}'


_ENCABEZADO_RESULTADO = [
    'N°',
    'Tipo DTE',
    'Folio',
    'RUT Receptor',
    'Resultado código',
    'Resultado glosa',
]

_MIME_XLSX = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)

# Nombre por defecto de cada PDF. En un borrador `{folio}` es su código.
_NOMBRE_PDF_BORRADOR = 'LibreDTE_{rut}_{folio}'
_NOMBRE_PDF_EMITIDO = 'LibreDTE_{rut}_T{dte}F{folio}'

# `salt` de la firma del enlace de descarga del ZIP de PDF.
_FIRMA_PDF = 'billing.emision_masiva_pdf'


@dataclass(frozen=True)
class Emision:
    """
    Lo que dejó una emisión masiva ya procesada.

    `envio` es el identificador que va en el asunto del correo.
    """

    envio: str
    resultados: list[Resultado]
    pdf_fallidos: int
    pdf_enlace: str | None


def parse(
    contribuyente: Contribuyente,
    archivo: bytes,
    extension: str,
) -> list[dict[str, Any]]:
    """
    Los documentos de una planilla, parseados por la biblioteca.

    La biblioteca decide el formato y las reglas de la planilla; ante el
    primer error informa la fila (`Fila 3: ...`).

    :param contribuyente: El emisor, para elegir el backend.
    :type contribuyente: Contribuyente
    :param archivo: El contenido de la planilla subida.
    :type archivo: bytes
    :param extension: La extensión del archivo (`csv` o `xlsx`).
    :type extension: str
    :return: Cada documento, en el formato del SII.
    :rtype: list[dict[str, Any]]
    :raises ServiceError: Si la extensión no es la de un formato soportado
        o la biblioteca rechaza la planilla.
    """
    estrategia = _ESTRATEGIAS.get(extension)
    if estrategia is None:
        raise ServiceError('El archivo debe ser una planilla CSV o XLSX.')

    try:
        with get_backend(contribuyente) as backend:
            lote = backend.billing.document.batch_processor.parse(
                archivo, strategy=estrategia
            )
    except LibreDteApiError as error:
        # El detalle trae la fila (`Fila 3: ...`); el nombre de la clase de
        # la excepción de la biblioteca no le sirve a quien sube la planilla.
        raise ServiceError(error.detail) from error
    except LibreDteSdkError as error:
        raise wrap(error) from error

    return [bag.document_parsed or {} for bag in lote.document_bags]


def documentos_to_yaml(documentos: list[dict[str, Any]]) -> str:
    """
    Los documentos de una planilla como YAML, para revisarlos.

    :param documentos: Los documentos que entregó `parse()`.
    :type documentos: list[dict[str, Any]]
    :return: El YAML, en el orden de la planilla.
    :rtype: str
    """
    return yaml.safe_dump(documentos, allow_unicode=True, sort_keys=False)


def save_documentos(
    contribuyente: Contribuyente,
    documentos: list[dict[str, Any]],
) -> Path:
    """
    Guarda en disco los documentos de una planilla ya parseada.

    El archivo se llama como la huella de su contenido: la misma planilla
    siempre cae en el mismo archivo, y esa huella es la del bloqueo contra
    el doble envío (`acquire_lock()`). Lo borra la tarea al terminar.

    :param contribuyente: El emisor de los documentos.
    :type contribuyente: Contribuyente
    :param documentos: Los documentos que entregó `parse()`.
    :type documentos: list[dict[str, Any]]
    :return: La ruta del archivo JSON.
    :rtype: Path
    """
    contenido = json.dumps(documentos, ensure_ascii=False, sort_keys=True)
    huella = hashlib.sha256(contenido.encode()).hexdigest()
    directorio = _pdf_dir(contribuyente.rut) / 'lotes'
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / f'{huella}.json'
    ruta.write_text(contenido, encoding='utf-8')
    return ruta


def load_documentos(ruta: Path) -> list[dict[str, Any]]:
    """
    Los documentos que dejó `save_documentos()`.

    :param ruta: El archivo JSON.
    :type ruta: Path
    :return: Cada documento, en el formato del SII.
    :rtype: list[dict[str, Any]]
    """
    documentos: list[dict[str, Any]] = json.loads(
        ruta.read_text(encoding='utf-8')
    )
    return documentos


def process(
    contribuyente: Contribuyente,
    documentos: list[dict[str, Any]],
    usuario: User,
    *,
    dte_real: bool,
    pdf: bool,
) -> Emision:
    """
    Emite los documentos de una planilla, arma el resultado y avisa por correo.

    El correo va siempre. Si algo inesperado corta la emisión, trae lo
    que alcanzó a procesarse y el error se vuelve a levantar.

    :param contribuyente: El emisor de los documentos.
    :type contribuyente: Contribuyente
    :param documentos: Los documentos que entregó `parse()`.
    :type documentos: list[dict[str, Any]]
    :param usuario: Quien subió la planilla; recibe el correo.
    :type usuario: User
    :param dte_real: `True` para confirmar cada borrador en un DTE real.
    :type dte_real: bool
    :param pdf: `True` para generar el ZIP con el PDF de cada documento,
        que el correo entrega como enlace de descarga.
    :type pdf: bool
    :return: El identificador del envío, el resultado de cada documento,
        cuántos PDF no se pudieron generar y el enlace del ZIP.
    :rtype: Emision
    :raises Exception: Cualquier error inesperado, después de avisarlo por
        correo.
    """
    inicio = time.monotonic()
    envio = timezone.localtime().strftime('%Y%m%d%H%M%S')
    base = f'{contribuyente.rut}_dte_masivo_{envio}'

    resultados: list[Resultado] = []
    adjuntos: list[tuple[str, bytes, str]] = []
    enlace: str | None = None
    pdf_fallidos = 0
    error: Exception | None = None
    try:
        # De a uno: si algo corta la emisión, lo emitido queda.
        for numero, datos in enumerate(documentos, start=1):
            resultados.append(
                _bill_documento(
                    contribuyente, numero, datos, usuario, dte_real=dte_real
                )
            )
    except Exception as exc:
        # Los errores de la API ya van en cada `Resultado`: esto es
        # algo inesperado.
        error = exc

    # También después de un error, con lo que se alcanzó a procesar.
    if resultados:
        try:
            adjuntos.append(
                (
                    f'{base}.xlsx',
                    build_result_sheet(resultados),
                    _MIME_XLSX,
                ),
            )
            if pdf:
                enlace, pdf_fallidos = _save_pdf_zip(
                    contribuyente, documentos, resultados, base
                )
        except Exception as exc:
            error = error or exc

    _notify(
        usuario,
        envio=envio,
        resultados=resultados,
        adjuntos=adjuntos,
        dte_real=dte_real,
        pdf=pdf,
        pdf_enlace=enlace,
        pdf_fallidos=pdf_fallidos,
        segundos=time.monotonic() - inicio,
        error=error,
    )
    if error is not None:
        raise error
    return Emision(
        envio=envio,
        resultados=resultados,
        pdf_fallidos=pdf_fallidos,
        pdf_enlace=enlace,
    )


def _bill_documento(
    contribuyente: Contribuyente,
    numero: int,
    datos: dict[str, Any],
    usuario: User,
    *,
    dte_real: bool,
) -> Resultado:
    """
    Borrador del documento y, si se pidió, su DTE real.

    Los errores de la API vuelven como `Resultado`, sin frenar a los
    demás documentos.

    :param contribuyente: El emisor del documento.
    :type contribuyente: Contribuyente
    :param numero: La posición del documento en la planilla.
    :type numero: int
    :param datos: El documento, en el formato del SII.
    :type datos: dict[str, Any]
    :param usuario: Quien subió la planilla.
    :type usuario: User
    :param dte_real: `True` para confirmar el borrador en un DTE real.
    :type dte_real: bool
    :return: Qué pasó con el documento, con el borrador o DTE que dejó.
    :rtype: Resultado
    """
    try:
        tipo_dte = TipoDte.objects.get(
            codigo=datos['Encabezado']['IdDoc']['TipoDTE']
        )
        borrador = biller.draft(contribuyente, tipo_dte, datos, usuario)
    except (ObjectDoesNotExist, ServiceError) as error:
        return _build_resultado(numero, datos, CODIGO_BORRADOR, str(error))

    if not dte_real:
        return _build_resultado(
            numero,
            datos,
            None,
            f'Borrador creado {borrador.codigo}',
            borrador_pk=borrador.pk,
        )

    try:
        emitido = biller.bill_draft(borrador)
    except ServiceError as error:
        # El borrador queda guardado: se informa cuál es.
        return _build_resultado(
            numero,
            datos,
            CODIGO_EMISION,
            f'{error} (quedó el borrador {borrador.codigo})',
            borrador_pk=borrador.pk,
        )

    return _build_resultado(
        numero,
        datos,
        None,
        f'DTE emitido, folio {emitido.folio}',
        emitido_pk=emitido.pk,
    )


def _build_resultado(
    numero: int,
    datos: dict[str, Any],
    codigo: int | None,
    glosa: str,
    *,
    borrador_pk: int | None = None,
    emitido_pk: int | None = None,
) -> Resultado:
    """
    `Resultado` del documento `datos` con su tipo, folio y receptor.

    :param numero: La posición del documento en la planilla.
    :type numero: int
    :param datos: El documento, en el formato del SII.
    :type datos: dict[str, Any]
    :param codigo: El código de resultado, o `None` si no hubo error.
    :type codigo: int | None
    :param glosa: El detalle del resultado.
    :type glosa: str
    :param borrador_pk: El borrador que quedó guardado, si quedó alguno.
    :type borrador_pk: int | None
    :param emitido_pk: El DTE que quedó emitido, si quedó alguno.
    :type emitido_pk: int | None
    :return: El resultado del documento.
    :rtype: Resultado
    """
    encabezado = datos['Encabezado']
    return Resultado(
        numero=numero,
        tipo_dte=str(encabezado['IdDoc']['TipoDTE']),
        folio_planilla=str(encabezado['IdDoc']['Folio']),
        rut_receptor=str(encabezado['Receptor']['RUTRecep']),
        codigo=codigo,
        glosa=glosa,
        borrador_pk=borrador_pk,
        emitido_pk=emitido_pk,
    )


def build_result_sheet(resultados: list[Resultado]) -> bytes:
    """
    La planilla de resultado: una fila por documento.

    Un código vacío es un documento generado.

    :param resultados: El resultado de cada documento.
    :type resultados: list[Resultado]
    :return: El XLSX de resultado.
    :rtype: bytes
    """
    filas = [_ENCABEZADO_RESULTADO]
    for resultado in resultados:
        codigo = '' if resultado.codigo is None else str(resultado.codigo)
        filas.append(
            [
                str(resultado.numero),
                resultado.tipo_dte,
                resultado.folio_planilla,
                resultado.rut_receptor,
                codigo,
                resultado.glosa,
            ]
        )
    return write_rows(filas)


def _save_pdf_zip(
    contribuyente: Contribuyente,
    documentos: list[dict[str, Any]],
    resultados: list[Resultado],
    base: str,
) -> tuple[str, int]:
    """
    Guarda el ZIP de PDF en disco y devuelve su enlace de descarga.

    Queda en la carpeta del contribuyente, con un nombre aleatorio. Se
    escribe a un temporal y se renombra, para no servir uno a medias.

    :param contribuyente: El emisor, para el nombre de cada PDF.
    :type contribuyente: Contribuyente
    :param documentos: Los documentos de la planilla, de donde sale el
        nombre del PDF.
    :type documentos: list[dict[str, Any]]
    :param resultados: El resultado de cada documento.
    :type resultados: list[Resultado]
    :param base: El nombre base de los archivos de esta emisión.
    :type base: str
    :return: `(enlace, fallidos)`: el enlace de descarga y cuántos PDF no
        se pudieron generar.
    :rtype: tuple[str, int]
    """
    directorio = _pdf_dir(contribuyente.rut)
    directorio.mkdir(parents=True, exist_ok=True)
    archivo = f'{base}_pdf_{secrets.token_hex(8)}.zip'
    ruta = directorio / archivo
    temporal = ruta.with_name(f'{archivo}.tmp')
    with zipfile.ZipFile(temporal, 'w', zipfile.ZIP_DEFLATED) as zip_pdf:
        fallidos = _build_pdf_zip(
            zip_pdf, contribuyente, documentos, resultados
        )
    temporal.replace(ruta)
    enlace = _build_pdf_link(contribuyente.rut, archivo, f'{base}_pdf.zip')
    return enlace, fallidos


def _pdf_dir(rut: int) -> Path:
    """
    La carpeta de los ZIP de PDF de un contribuyente.

    :param rut: El RUT del contribuyente, sin dígito verificador.
    :type rut: int
    :return: `EMISION_MASIVA_PDF_DIR/<rut>`.
    :rtype: Path
    """
    return settings.EMISION_MASIVA_PDF_DIR / str(rut)


def _build_pdf_link(rut: int, archivo: str, nombre: str) -> str:
    """
    Enlace firmado y absoluto (va en un correo) de descarga del ZIP.

    :param rut: El RUT del contribuyente, sin dígito verificador: la
        carpeta del ZIP (ver `_pdf_dir()`).
    :type rut: int
    :param archivo: El nombre del ZIP en esa carpeta.
    :type archivo: str
    :param nombre: El nombre con que se descarga.
    :type nombre: str
    :return: El enlace.
    :rtype: str
    """
    token = signing.dumps(
        {'rut': rut, 'archivo': archivo, 'nombre': nombre}, salt=_FIRMA_PDF
    )
    ruta = reverse('billing:emitir_masivo_pdf', kwargs={'token': token})
    return f'{settings.URL_SCHEMA}://{settings.HOSTNAME[0]}{ruta}'


def find_pdf_zip(token: str) -> tuple[Path, str] | None:
    """
    El ZIP de PDF al que apunta un enlace de descarga, si existe.

    El enlace no pide login: lo protege la firma.

    :param token: El token del enlace.
    :type token: str
    :return: `(ruta, nombre)`: el ZIP en disco y el nombre con que se
        descarga; `None` si el enlace no sirve.
    :rtype: tuple[Path, str] | None
    """
    try:
        datos = signing.loads(token, salt=_FIRMA_PDF)
    except signing.BadSignature:
        return None
    # `int()` y `.name`: nunca se sale de la carpeta de los ZIP.
    ruta = _pdf_dir(int(datos['rut'])) / Path(datos['archivo']).name
    if not ruta.is_file():
        return None
    return ruta, str(datos['nombre'])


def _build_pdf_zip(
    zip_pdf: zipfile.ZipFile,
    contribuyente: Contribuyente,
    documentos: list[dict[str, Any]],
    resultados: list[Resultado],
) -> int:
    """
    Escribe en `zip_pdf` el PDF de cada documento generado.

    Uno que no se puede generar se cuenta y se sigue con los demás.

    :param zip_pdf: El ZIP, abierto para escribir.
    :type zip_pdf: zipfile.ZipFile
    :param contribuyente: El emisor, para el nombre de cada PDF.
    :type contribuyente: Contribuyente
    :param documentos: Los documentos de la planilla, de donde sale el
        nombre del PDF.
    :type documentos: list[dict[str, Any]]
    :param resultados: El resultado de cada documento.
    :type resultados: list[Resultado]
    :return: Cuántos PDF no se pudieron generar.
    :rtype: int
    """
    usados: set[str] = set()
    fallidos = 0
    for resultado in resultados:
        documento: DteEmitido | Borrador
        try:
            if resultado.emitido_pk is not None:
                documento = DteEmitido.objects.get(pk=resultado.emitido_pk)
                por_defecto = _NOMBRE_PDF_EMITIDO
                folio = str(documento.folio)
            elif resultado.borrador_pk is not None and resultado.ok:
                documento = Borrador.objects.get(pk=resultado.borrador_pk)
                por_defecto, folio = _NOMBRE_PDF_BORRADOR, documento.codigo
            else:
                continue
        except ObjectDoesNotExist:
            fallidos += 1
            continue

        try:
            pdf = document_renderer.render_pdf(documento)
        except ServiceError:
            fallidos += 1
            continue

        libredte = documentos[resultado.numero - 1].get('LibreDTE', {})
        plantilla = libredte.get('pdf', {}).get('nombre') or por_defecto
        nombre = _make_unique_name(
            _build_pdf_name(
                plantilla,
                contribuyente,
                dte=resultado.tipo_dte,
                folio=folio,
            ),
            usados,
        )
        zip_pdf.writestr(nombre, pdf.content_bytes)
    return fallidos


def _build_pdf_name(
    plantilla: str,
    contribuyente: Contribuyente,
    *,
    dte: str,
    folio: str,
) -> str:
    """
    Nombre de archivo de un PDF desde el "Nombre PDF" del documento.

    Admite `{rut}`, `{dv}`, `{dte}` y `{folio}`. Lo que no sea letra,
    número, punto o guion se reemplaza (una barra crearía carpetas).

    :param plantilla: El nombre con sus variables, del documento o el de
        por defecto.
    :type plantilla: str
    :param contribuyente: El emisor, para `{rut}` y `{dv}`.
    :type contribuyente: Contribuyente
    :param dte: El código del tipo de documento, para `{dte}`.
    :type dte: str
    :param folio: El folio del DTE, o el código del borrador, para
        `{folio}`.
    :type folio: str
    :return: El nombre del archivo, terminado en `.pdf`.
    :rtype: str
    """
    nombre = (
        plantilla.replace('{rut}', str(contribuyente.rut))
        .replace('{dv}', contribuyente.dv)
        .replace('{dte}', dte)
        .replace('{folio}', folio)
    )
    nombre = re.sub(r'[^\w.-]', '_', nombre).strip('._') or 'documento'
    return nombre.removesuffix('.pdf') + '.pdf'


def _make_unique_name(nombre: str, usados: set[str]) -> str:
    """
    `nombre`, o con un sufijo si otro PDF del ZIP ya lo usa.

    :param nombre: El nombre que se quiere usar.
    :type nombre: str
    :param usados: Los nombres ya usados en el ZIP; se agrega el elegido.
    :type usados: set[str]
    :return: El nombre, con sufijo si ya estaba usado.
    :rtype: str
    """
    candidato = nombre
    raiz = nombre.removesuffix('.pdf')
    numero = 2
    while candidato in usados:
        candidato = f'{raiz}_{numero}.pdf'
        numero += 1
    usados.add(candidato)
    return candidato


def _notify(
    usuario: User,
    *,
    envio: str,
    resultados: list[Resultado],
    adjuntos: list[tuple[str, bytes, str]],
    dte_real: bool,
    pdf: bool,
    pdf_enlace: str | None,
    pdf_fallidos: int,
    segundos: float,
    error: Exception | None,
) -> None:
    """
    Correo de resultado al usuario que subió la planilla.

    :param usuario: Quien subió la planilla.
    :type usuario: User
    :param envio: El identificador del envío, que va en el asunto.
    :type envio: str
    :param resultados: El resultado de cada documento.
    :type resultados: list[Resultado]
    :param adjuntos: `(nombre, contenido, tipo MIME)` de cada adjunto.
    :type adjuntos: list[tuple[str, bytes, str]]
    :param dte_real: Si se pidió emitir el DTE real.
    :type dte_real: bool
    :param pdf: Si se pidieron los PDF.
    :type pdf: bool
    :param pdf_enlace: El enlace de descarga del ZIP de PDF, o `None` si
        no se pidieron o no se alcanzó a generar.
    :type pdf_enlace: str | None
    :param pdf_fallidos: Cuántos PDF no se pudieron generar.
    :type pdf_fallidos: int
    :param segundos: Lo que tardó la emisión.
    :type segundos: float
    :param error: El error que cortó la emisión, o `None`.
    :type error: Exception | None
    """
    lineas = [f'{usuario.get_full_name() or usuario.username},', '']
    con_error = sum(1 for resultado in resultados if not resultado.ok)
    if error is None:
        lineas += [
            'Se adjunta la planilla con el detalle de la emisión de cada '
            'documento solicitado.',
            '',
            f'- Documentos: {len(resultados)} ({con_error} con error)',
        ]
    elif adjuntos:
        lineas += [
            'Ha ocurrido un error y la planilla no pudo procesarse completa: '
            f'{error}',
            '',
            'Se adjunta la planilla con el resultado de los documentos que '
            'alcanzaron a procesarse antes del error; los que no tienen '
            'resultado no se procesaron. Antes de volver a subirla, quite '
            'los que ya se generaron, o se generarán de nuevo.',
            '',
            f'- Documentos procesados: {len(resultados)} ({con_error} con '
            'error)',
        ]
    else:
        lineas += [
            'Ha ocurrido un error y la planilla no pudo procesarse completa: '
            f'{error}',
            '',
            'Es posible que parte de los documentos se haya generado antes '
            'del error. Revise sus borradores y documentos emitidos antes de '
            'volver a subirla.',
            '',
        ]

    if not pdf:
        linea_pdf = 'No'
    elif pdf_enlace is None:
        linea_pdf = 'Sí, pero no se pudieron generar'
    elif pdf_fallidos:
        linea_pdf = f'Sí (no se pudieron generar {pdf_fallidos})'
    else:
        linea_pdf = 'Sí'
    lineas += [
        f'- Generar DTE real: {"Sí" if dte_real else "No"}',
        f'- PDF: {linea_pdf}',
        f'- Tiempo de ejecución: {segundos:.0f} segundos',
    ]
    if pdf_enlace is not None:
        lineas += [
            '',
            'Descargue los PDF en el siguiente enlace:',
            pdf_enlace,
        ]

    _send_mail(usuario, envio, lineas, adjuntos)


def _send_mail(
    usuario: User,
    envio: str,
    lineas: list[str],
    adjuntos: list[tuple[str, bytes, str]],
) -> None:
    """
    Envía el correo de resultado, solo al usuario (nunca al receptor).

    :param usuario: Quien subió la planilla.
    :type usuario: User
    :param envio: El identificador del envío, que va en el asunto.
    :type envio: str
    :param lineas: El cuerpo del correo, una línea por elemento.
    :type lineas: list[str]
    :param adjuntos: `(nombre, contenido, tipo MIME)` de cada adjunto.
    :type adjuntos: list[tuple[str, bytes, str]]
    """
    if not usuario.email:
        # Lo borró de su perfil mientras la tarea esperaba.
        return

    mensaje = EmailMessage(
        subject=f'Resultado emisión masiva de DTE #{envio}',
        body='\n'.join(lineas),
        to=[usuario.email],
    )
    for nombre, contenido, mime in adjuntos:
        mensaje.attach(nombre, contenido, mime)
    mensaje.send()
