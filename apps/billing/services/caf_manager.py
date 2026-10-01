"""
Servicio: CAF (Código de Autorización de Folios) y folios.

Único módulo que llama a `billing.identifier.caf_faker`/`caf_validator`
del SDK — nada fuera de `services/*.py` debe tocarlo directamente.
También concentra la reserva del siguiente folio: dos solicitudes
concurrentes nunca deben poder llevarse el mismo.
"""

from __future__ import annotations

import base64
from datetime import date

from django.db import transaction
from libredte_lib_sdk.billing.identifier import Caf as CafDto
from libredte_lib_sdk.exceptions import LibreDteSdkError

from apps.libredte.models import Contribuyente
from apps.libredte.services.exceptions import ServiceError, wrap
from apps.libredte.services.libredte_backend import get_backend

from ..models import Caf, CafFolio, TipoDte


class NoFolioDisponibleError(ServiceError):
    """No quedan folios disponibles para `(contribuyente, tipo_dte)`."""


class CafVencidoError(ServiceError):
    """
    El CAF que cubre el folio a emitir ya venció.

    La verifica tanto `reserve_next_folio()` como `reserve_folio()` —
    ambas reservan un folio que se va a usar para firmar un documento
    real, la única diferencia entre ellas es quién decide el folio (el
    contador o quien llama), no si el resultado se considera "real".
    """


def validate_caf(
    xml_base64: str,
    contribuyente: Contribuyente | None = None,
) -> CafDto:
    """Valida un CAF real (firma, llaves) contra la API — no persiste nada."""
    try:
        with get_backend(contribuyente) as backend:
            return backend.billing.identifier.caf_validator.validate(
                xml_base64,
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error


def create_fake_caf(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    *,
    folio_desde: int = 1,
    folio_hasta: int | None = None,
) -> CafDto:
    """Genera un CAF ficticio (solo pruebas/demo) — no persiste nada."""
    return create_fake_caf_for(
        f'{contribuyente.rut}-{contribuyente.dv}',
        contribuyente.razon_social,
        tipo_dte,
        folio_desde=folio_desde,
        folio_hasta=folio_hasta,
    )


def create_fake_caf_for(
    rut_con_dv: str,
    razon_social: str,
    tipo_dte: TipoDte,
    *,
    folio_desde: int = 1,
    folio_hasta: int | None = None,
) -> CafDto:
    """
    Genera un CAF ficticio para cualquier emisor (solo pruebas/demo).

    A diferencia de `create_fake_caf()`, no requiere un `Contribuyente`
    propio — sirve para un proveedor externo (ej. el `Emisor` de un
    `DteRecibido` de prueba, que nunca se registra como contribuyente de
    esta instancia). No persiste nada.
    """
    emisor = {'rut': rut_con_dv, 'razon_social': razon_social}
    try:
        with get_backend() as backend:
            return backend.billing.identifier.caf_faker.create(
                emisor,
                codigo_documento=tipo_dte.codigo,
                folio_desde=folio_desde,
                folio_hasta=folio_hasta,
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error


def register_caf(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    caf: CafDto,
) -> Caf:
    """
    Persiste `caf` (real o ficticio) y actualiza el contador de folios.

    Crea el `CafFolio` si es el primer CAF cargado para `(contribuyente,
    tipo_dte)`; si ya existe, solo suma los folios nuevos a
    `disponibles` — `siguiente` no se toca (podría estar a mitad del
    rango de un CAF anterior).
    """
    cantidad = caf.folio_hasta - caf.folio_desde + 1

    caf_model = Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        desde=caf.folio_desde,
        hasta=caf.folio_hasta,
        xml_base64=caf.xml_base64,
        fecha_autorizacion=date.fromisoformat(caf.fecha_autorizacion),
        fecha_vencimiento=(
            date.fromisoformat(caf.fecha_vencimiento)
            if caf.fecha_vencimiento
            else None
        ),
        idk=caf.idk,
    )

    folio, creado = CafFolio.objects.get_or_create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        defaults={
            'siguiente': caf.folio_desde,
            'disponibles': cantidad,
            'alerta': max(round(cantidad * 0.1), 1),
        },
    )
    if not creado:
        folio.disponibles += cantidad
        folio.save(update_fields=['disponibles'])

    return caf_model


def register_caf_from_xml(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    xml_bytes: bytes,
) -> Caf:
    """
    Valida un CAF (bytes, de `sii.backend`) y lo persiste.

    Comparte `validate_caf()`/`register_caf()` con la carga manual
    (`CafUploadForm`), pero acá `tipo_dte` ya se conoce de antemano —
    se pidió u obtuvo justo para ese tipo — así que solo se confirma
    que el CAF que volvió coincide, no se vuelve a resolver desde el
    XML como hace el formulario de carga.
    """
    xml_base64 = base64.b64encode(xml_bytes).decode()
    caf = validate_caf(xml_base64, contribuyente)
    if caf.tipo_documento != tipo_dte.codigo:
        raise ServiceError(
            f'El CAF recibido es de tipo {caf.tipo_documento}, se '
            f'esperaba {tipo_dte.codigo}.',
        )
    if Caf.objects.filter(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        desde=caf.folio_desde,
    ).exists():
        raise ServiceError('Ya existe un CAF cargado con ese rango de folios.')
    return register_caf(contribuyente, tipo_dte, caf)


def reserve_next_folio(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
) -> tuple[int, str]:
    """
    Reserva el siguiente folio disponible de `(contribuyente, tipo_dte)`.

    Atómico: bloquea la fila de `CafFolio` (`select_for_update`) para
    que dos solicitudes concurrentes nunca se lleven el mismo folio —
    en SQLite (desarrollo) `select_for_update` no bloquea a nivel de
    fila (el motor no lo soporta), pero la escritura sigue serializada
    por el lock de archivo que toma la propia transacción, así que la
    exclusión mutua se mantiene igual; en Postgres/MySQL (producción)
    el `select_for_update` sí bloquea la fila puntual. No se libera el
    lock hasta incrementar el contador — la llamada a la API (lenta, de
    red) queda deliberadamente fuera de este bloque.

    Devuelve `(folio, caf_xml_base64)` — el XML del CAF cuyo rango
    cubre ese folio, listo para `document.builder.build_signed`. Si el
    folio se emite y la construcción del documento falla después, el
    folio queda consumido igual (no se revierte): es el mismo criterio
    que usa el SII con folios reales — un folio saltado por un error se
    anula, no se reutiliza.
    """
    with transaction.atomic():
        caf_folio = (
            CafFolio.objects.select_for_update()
            .filter(contribuyente=contribuyente, tipo_dte=tipo_dte)
            .first()
        )
        if caf_folio is None or caf_folio.disponibles <= 0:
            raise NoFolioDisponibleError(
                f'No hay folios disponibles de {tipo_dte} para '
                f'{contribuyente}.',
            )

        folio = caf_folio.siguiente
        caf = Caf.objects.filter(
            contribuyente=contribuyente,
            tipo_dte=tipo_dte,
            desde__lte=folio,
            hasta__gte=folio,
        ).first()
        if caf is None:
            raise NoFolioDisponibleError(
                f'El folio {folio} de {tipo_dte} no está cubierto por '
                f'ningún CAF cargado de {contribuyente}.',
            )
        if not caf.vigente:
            raise CafVencidoError(
                f'El CAF {caf.codigo} venció el '
                f'{caf.fecha_vencimiento:%d-%m-%Y} — carga uno nuevo '
                f'para poder emitir {tipo_dte}.',
            )

        caf_folio.siguiente += 1
        caf_folio.disponibles -= 1
        caf_folio.save(update_fields=['siguiente', 'disponibles'])

        return folio, caf.xml_base64


def reserve_folio(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    folio: int,
) -> str:
    """
    Reserva un folio específico (no "el siguiente") de un contribuyente.

    Para cuando quien llama ya sabe qué folio quiere (ej. al
    reproducir el folio de un ejemplo real de la biblioteca) en vez de
    pedirle al contador el próximo disponible. Sigue siendo una
    reserva real (mismas validaciones que `reserve_next_folio()`,
    incluyendo `CafVencidoError`): el folio resultante se puede usar
    igual para firmar un documento real, así que no hay ningún caso en
    que se pueda relajar la vigencia del CAF.

    `siguiente` avanza a `max(siguiente, folio + 1)`, nunca solo a
    `folio + 1`: los folios pueden pedirse fuera de orden (ej. un
    ejemplo con folio 6 puede procesarse antes que uno con folio 2, si
    el primero es dependencia de un tercero — ver `ExamplesWorker
    ::list()` en libredte-lib-core), y `siguiente` tiene que terminar
    por delante de todos los folios ya usados para que una reserva
    posterior vía `reserve_next_folio()` nunca choque con uno de ellos
    — avanzar solo cuando `folio == siguiente` deja atrás folios ya
    usados fuera de orden (`siguiente` quedaría apuntando a uno de
    ellos, no al primero libre).

    Mismo bloqueo que `reserve_next_folio()` (`select_for_update`) y
    mismo criterio de "un folio saltado por un error no se reutiliza":
    si la construcción del documento falla después de esta reserva, el
    folio queda consumido igual.
    """
    with transaction.atomic():
        caf_folio = (
            CafFolio.objects.select_for_update()
            .filter(contribuyente=contribuyente, tipo_dte=tipo_dte)
            .first()
        )
        if caf_folio is None or caf_folio.disponibles <= 0:
            raise NoFolioDisponibleError(
                f'No hay folios disponibles de {tipo_dte} para '
                f'{contribuyente}.',
            )

        caf = Caf.objects.filter(
            contribuyente=contribuyente,
            tipo_dte=tipo_dte,
            desde__lte=folio,
            hasta__gte=folio,
        ).first()
        if caf is None:
            raise NoFolioDisponibleError(
                f'El folio {folio} de {tipo_dte} no está cubierto por '
                f'ningún CAF cargado de {contribuyente}.',
            )
        if not caf.vigente:
            raise CafVencidoError(
                f'El CAF {caf.codigo} venció el '
                f'{caf.fecha_vencimiento:%d-%m-%Y} — carga uno nuevo '
                f'para poder emitir {tipo_dte}.',
            )

        caf_folio.siguiente = max(caf_folio.siguiente, folio + 1)
        caf_folio.disponibles -= 1
        caf_folio.save(update_fields=['siguiente', 'disponibles'])

        return caf.xml_base64
