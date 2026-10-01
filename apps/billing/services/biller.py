"""
Servicio: emisión de un DTE — arma un borrador, lo timbra/firma y persiste.

El proceso es siempre en dos pasos, nunca directo: primero un
`Borrador` (sin folio, timbre ni firma — `draft()`/`draft_from_form()`,
según si `input_data` ya viene en formato SII o crudo de
`/billing/emitir`), después se confirma en un `DteEmitido` real
(`bill_draft()`). Entre medio no se vuelve a normalizar lo que el
borrador ya calculó — ver `Borrador.datos` en `models.py`. `draft()`/
`draft_from_form()` resuelven `Encabezado.Emisor`/`Receptor`/
`IdDoc.TipoDTE` a partir de `contribuyente`/`tipo_dte` y de los datos
del propio receptor que trae el documento (`_resolver_receptor()`: se
busca por `CdgIntRecep` o RUT entre los `Receptor` ya guardados de
`contribuyente`, se actualiza con los datos de este documento, o se
crea si no existe) — nadie más allá de acá resuelve, crea o actualiza
un `Receptor`. `input_data`/`datos_formulario` solo
traen lo que no tiene representación en el modelo (`Detalle`,
`Referencia`, el resto de `IdDoc`); Emisor/Receptor se sobrescriben
igual aunque ya vengan con algo (ej. un ejemplo real de
`document.examples` trae su propio Emisor/Receptor de fixture).

La fecha de emisión de un `Borrador` es la que trae el propio
documento (`Encabezado.IdDoc.FchEmis`) — puede ser pasada o futura,
no es "siempre hoy". La de un `DteEmitido` confirmado vía `bill_draft()`
sí es siempre hoy (el momento real de la firma) — no es un parámetro:
si quien llama necesita otra fecha (ej. para poblar datos de prueba con
apariencia histórica), es su responsabilidad reescribir `fecha`/
`periodo` en el `DteEmitido` que `bill_draft()` devuelve, después de
crearlo — no de este servicio. Un `DteEmitido` registrado vía
`load_xml()` es la excepción: su `fecha` es la que trae el propio
documento, porque la firma no ocurrió recién — el documento ya estaba
timbrado y firmado antes de subirlo.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from django.utils import timezone
from libredte_lib_sdk.exceptions import LibreDteSdkError

from apps.libredte.models import Comuna, Contribuyente, Pais
from apps.libredte.services import certificate_manager
from apps.libredte.services.exceptions import ServiceError, wrap
from apps.libredte.services.libredte_backend import get_backend

from ..models import (
    Borrador,
    DteEmitido,
    DteEmitidoReferencia,
    Receptor,
    TipoDte,
)
from ..utils.dte import montos_en_clp
from . import caf_manager

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from libredte_lib_sdk.billing.document import DocumentBag


def draft(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    input_data: dict[str, Any],
    usuario: User,
) -> Borrador:
    """
    Arma el borrador de un DTE desde datos ya en formato SII (anidado).

    Para flujos que ya traen `Encabezado`/`Detalle` armado (ej. un
    ejemplo real de `document.examples`) — a diferencia de
    `draft_from_form()`, no pasa por `form.estandar`.

    El receptor se resuelve (`_resolver_receptor()`) a partir de
    `input_data['Encabezado']['Receptor']` tal cual venía — no hace
    falta que quien llama ya tenga un `Receptor` propio resuelto de
    antemano. No altera `input_data` más que sobrescribir
    `IdDoc.TipoDTE`/`Emisor`/`Receptor` con los datos reales de quien
    factura (los ejemplos de `document.examples` traen su propio
    Emisor/Receptor de fixture, que no corresponde a un envío real) —
    cualquier `Folio` que `input_data` traiga se deja tal cual,
    `draft()` no decide qué significa. Si quien llama necesita que el
    borrador se muestre sin folio (ej. uno que nunca se va a
    confirmar), es responsabilidad de quien llama dejarlo en `0` antes
    de invocar esto — no de `draft()`.
    """
    receptor = _resolver_receptor(
        contribuyente,
        input_data['Encabezado']['Receptor'],
    )

    input_data['Encabezado']['IdDoc']['TipoDTE'] = tipo_dte.codigo
    input_data['Encabezado']['Emisor'] = _emisor_payload(contribuyente)
    input_data['Encabezado']['Receptor'] = _receptor_payload(receptor)

    try:
        with get_backend(contribuyente) as backend:
            bag = backend.billing.document.builder.build_draft(input_data)
    except LibreDteSdkError as error:
        raise wrap(error) from error

    return _crear_borrador(contribuyente, tipo_dte, receptor, usuario, bag)


def draft_from_form(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    datos_formulario: dict[str, Any],
    usuario: User,
) -> Borrador:
    """
    Arma el borrador de un DTE desde los datos crudos de `/billing/emitir`.

    A diferencia de `draft()`, `datos_formulario` no viene en el
    formato anidado del SII — viene tal cual lo entregó el HTML
    (`request.POST`, con listas para los campos repetibles de
    `Detalle`/`Referencia`) y se pasa server-side con
    `options={'parser': {'strategy': 'form.estandar'}}`: es esa
    estrategia (`EstandarParserStrategy` en `libredte-lib-core`, no
    Slim) quien arma toda la estructura `Encabezado`/`Detalle` y
    calcula neto/IVA/total.

    El receptor se resuelve (`_resolver_receptor()`) a partir de las
    mismas llaves planas del receptor que ya vienen en
    `datos_formulario` (`RUTRecep`/`CdgIntRecep`/etc. — el HTML manda
    los campos oficiales del SII directo, no un `Receptor` ya elegido
    de una lista: `/billing/emitir` puede facturar a alguien nuevo, sin
    tener que crearlo antes en otro lado). Acá solo se agrega la llave
    plana que Slim conoce y `form.estandar` no (`TpoDoc`) y se
    sobrescribe Emisor/Receptor con los datos reales, sin tocar el
    resto de lo que vino del formulario. Sin CAF ni certificado
    (`build_draft()`, no `build_signed()`) — no queda timbrado ni
    firmado, y no consume folio.
    """
    receptor = _resolver_receptor(contribuyente, datos_formulario)

    datos_formulario['TpoDoc'] = tipo_dte.codigo
    datos_formulario.update(_emisor_payload_plano(contribuyente))
    datos_formulario.update(_receptor_payload_plano(receptor))

    try:
        with get_backend(contribuyente) as backend:
            bag = backend.billing.document.builder.build_draft(
                datos_formulario,
                options={'parser': {'strategy': 'form.estandar'}},
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error

    return _crear_borrador(contribuyente, tipo_dte, receptor, usuario, bag)


def calculate_totals_from_form(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    datos_formulario: dict[str, Any],
) -> dict[str, Any]:
    """
    Calcula `Detalle`/`Totales` de un documento sin persistir nada.

    Mismo builder que `draft_from_form()` (`form.estandar`, sin CAF ni
    certificado), pero deliberadamente sin `_resolver_receptor()` ni
    `_crear_borrador()`: los datos del receptor se mandan tal como los
    tipeó el usuario, sin buscar ni crear un `Receptor`, y sin validar
    contra las reglas de negocio del SII
    (`options={'validator': {'validate': False}}`) — alcanza con
    armar y normalizar para obtener los montos, no hace falta un
    documento válido de punta a punta. Se usa para recalcular en vivo
    mientras se completa `/billing/emitir` (ver
    `views.emitir_calcular()`), nunca para guardar un borrador real.
    """
    datos_formulario['TpoDoc'] = tipo_dte.codigo
    datos_formulario.update(_emisor_payload_plano(contribuyente))

    try:
        with get_backend(contribuyente) as backend:
            bag = backend.billing.document.builder.build_draft(
                datos_formulario,
                options={
                    'parser': {'strategy': 'form.estandar'},
                    'validator': {'validate': False},
                },
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error

    document = bag.require_document()
    return {
        'detalle': document.get('Detalle', []),
        'totales': document['Encabezado']['Totales'],
    }


def _resolver_receptor(
    contribuyente: Contribuyente,
    receptor_data: dict[str, Any],
) -> Receptor:
    """
    Busca (o crea) el `Receptor` de `contribuyente` y actualiza sus datos.

    Los datos vienen en llaves planas del SII (`RUTRecep`/
    `CdgIntRecep`/etc.), el mismo formato tanto si vienen anidados en
    `Encabezado.Receptor` como directo en `datos_formulario`.

    Se busca primero por `CdgIntRecep` si el documento lo trae — es el
    código propio del contribuyente para ese cliente (ej. "amazon"), y
    puede no coincidir con ningún RUT ya guardado si el mismo receptor
    quedó registrado con datos distintos antes. Si no viene, se busca
    por RUT.

    Igual que `document_receiver._resolver_emisor()`: siempre sobrescribe los
    datos de un `Receptor` ya existente con los de ESTE documento (RUT
    incluido, si se encontró por `CdgIntRecep` y viene con uno
    distinto al guardado) — la idea es que el receptor se mantenga al
    día con lo último usado para facturarle, no que quede pegado en lo
    que se tipeó la primera vez. Si no existe ninguno, se crea.

    `Nacionalidad` y `NumId` (datos del receptor extranjero) son las
    únicas llaves que cambian de forma según el origen: anidadas bajo
    `Extranjero` en el formato de `draft()` (`_receptor_payload()`),
    planas en el de `draft_from_form()` (`_receptor_payload_plano()`,
    `form.estandar` no tiene ese nodo) — se acepta cualquiera de las
    dos formas.
    """
    rut, dv = _rut_dv(receptor_data['RUTRecep'])
    codigo_interno = receptor_data.get('CdgIntRecep') or ''

    extranjero = receptor_data.get('Extranjero') or {}
    nacionalidad = receptor_data.get('Nacionalidad') or extranjero.get(
        'Nacionalidad'
    )
    numero_identificacion = (
        receptor_data.get('NumId') or extranjero.get('NumId') or ''
    )

    comuna = None
    if receptor_data.get('CmnaRecep'):
        comuna = Comuna.objects.filter(
            glosa__iexact=receptor_data['CmnaRecep'],
        ).first()
    pais = None
    if nacionalidad:
        pais = Pais.objects.filter(codigo=nacionalidad).first()

    datos = {
        'rut': rut,
        'dv': dv,
        'codigo_interno': codigo_interno,
        'razon_social': receptor_data.get('RznSocRecep') or '',
        'giro': receptor_data.get('GiroRecep') or '',
        'telefono': receptor_data.get('Contacto') or '',
        'correo': receptor_data.get('CorreoRecep') or '',
        'direccion': receptor_data.get('DirRecep') or '',
        'comuna': comuna,
        'ciudad': receptor_data.get('CiudadRecep') or '',
        'pais': pais,
        'numero_identificacion': numero_identificacion,
    }

    receptor = None
    if codigo_interno:
        receptor = Receptor.objects.filter(
            contribuyente=contribuyente,
            codigo_interno=codigo_interno,
        ).first()
    if receptor is None:
        receptor = Receptor.objects.filter(
            contribuyente=contribuyente,
            rut=rut,
            dv=dv,
        ).first()

    if receptor is None:
        return Receptor.objects.create(contribuyente=contribuyente, **datos)

    for campo, valor in datos.items():
        setattr(receptor, campo, valor)
    receptor.save()
    return receptor


def _rut_dv(rut_con_dv: str) -> tuple[int, str]:
    """`(rut, dv)` desde un RUT con el formato `NNNNNNNN-D` del DTE."""
    rut, dv = rut_con_dv.split('-')
    return int(rut), dv


def _crear_borrador(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    receptor: Receptor,
    usuario: User,
    bag: DocumentBag,
) -> Borrador:
    """Persiste el `Borrador` desde la `DocumentBag` que devolvió el SDK."""
    document = bag.require_document()
    neto, exento, iva, total = montos_en_clp(document['Encabezado'])
    fecha = date.fromisoformat(document['Encabezado']['IdDoc']['FchEmis'])
    return Borrador.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        receptor=receptor,
        usuario=usuario,
        fecha=fecha,
        datos=bag.document_normalized,
        extra=bag.document_extra,
        xml_base64=bag.xml_base64,
        neto=neto,
        exento=exento,
        iva=iva,
        total=total,
    )


def bill_draft(borrador: Borrador, *, folio: int | None = None) -> DteEmitido:
    """
    Confirma un `Borrador`: genera el DTE real, timbrado y firmado.

    Reutiliza `borrador.datos` (los datos ya normalizados, ver
    `draft_from_form()`) sin volver a normalizar
    (`options={'normalizer': {'normalize': False}}`) — evita recalcular
    lo que el borrador ya calculó. El borrador se elimina al terminar
    con éxito: nunca se reutiliza ni se actualiza.

    Las `Referencia` del documento (si trae) se resuelven contra los
    DTE ya emitidos *antes* de reservar folio y firmar — así una
    referencia inválida no consume un folio en vano (ver
    `_resolver_referencias()`, es lo que sostiene `DteEmitido.libro()`).

    `folio` es solo para reproducir el folio exacto de un ejemplo real
    de la biblioteca (`caf_manager.reserve_folio()`) en vez de pedirle
    "el siguiente" al CAF — necesario porque `_resolver_referencias()`
    busca el documento referenciado por su folio real, y ese folio ya
    viene decidido por la biblioteca (ver `ExamplesWorker::list()` en
    libredte-lib-core). La emisión real (`/billing/emitir`) nunca lo
    pasa: ahí el folio siempre lo decide el CAF (`reserve_next_folio()`).
    """
    contribuyente = borrador.contribuyente
    input_data = borrador.datos
    referencias = _resolver_referencias(contribuyente, input_data)

    certificate = certificate_manager.certificate_for(contribuyente)
    if folio is None:
        folio, caf_xml = caf_manager.reserve_next_folio(
            contribuyente,
            borrador.tipo_dte,
        )
    else:
        caf_xml = caf_manager.reserve_folio(
            contribuyente,
            borrador.tipo_dte,
            folio,
        )
    input_data['Encabezado']['IdDoc']['Folio'] = folio

    try:
        with get_backend(contribuyente) as backend:
            documento = backend.billing.document.builder.build_signed(
                input_data,
                options={'normalizer': {'normalize': False}},
                caf_xml=caf_xml,
                certificate=certificate,
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error

    document = documento.require_document()
    neto, exento, iva, total = montos_en_clp(document['Encabezado'])
    fecha = timezone.localdate()
    dte_emitido = DteEmitido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=borrador.tipo_dte,
        receptor=borrador.receptor,
        usuario=borrador.usuario,
        folio=folio,
        periodo=fecha.year * 100 + fecha.month,
        fecha=fecha,
        neto=neto,
        exento=exento,
        iva=iva,
        total=total,
        xml_base64=documento.xml_base64,
    )
    _persistir_referencias(dte_emitido, referencias)
    borrador.delete()
    return dte_emitido


def load_xml(
    contribuyente: Contribuyente,
    xml_base64: str,
    usuario: User,
) -> DteEmitido:
    """
    Registra un DTE ya timbrado y firmado, emitido por otro medio.

    A diferencia de `draft()`/`bill_draft()`, no arma ni timbra nada —
    parte de un XML ya completo (`document.loader`, no `document
    .builder`). Sirve para dejar en `/billing/emitidos` un documento
    que este contribuyente emitió fuera de Slim (otro sistema, o un
    respaldo recuperado). `fecha` es la que trae el propio documento
    (`Encabezado.IdDoc.FchEmis`), no "hoy" — a diferencia de
    `bill_draft()`, acá la firma no ocurrió recién. No se resuelven
    `Referencia` (a diferencia de `bill_draft()`): un documento
    importado no participa de `DteEmitido.libro()` vía cadena de
    referencias con documentos que Slim nunca vio.
    """
    try:
        with get_backend(contribuyente) as backend:
            bag = backend.billing.document.loader.load_xml(xml_base64)
    except LibreDteSdkError as error:
        raise wrap(error) from error

    encabezado = bag.require_document()['Encabezado']
    emisor_rut, emisor_dv = _rut_dv(encabezado['Emisor']['RUTEmisor'])
    if (emisor_rut, emisor_dv) != (contribuyente.rut, contribuyente.dv):
        raise ServiceError(
            f'El documento fue emitido por {emisor_rut}-{emisor_dv}, no '
            f'por {contribuyente.rut}-{contribuyente.dv} — no '
            f'corresponde importarlo a este contribuyente.',
        )

    tipo_dte = TipoDte.objects.get(codigo=encabezado['IdDoc']['TipoDTE'])
    folio = encabezado['IdDoc']['Folio']
    if DteEmitido.objects.filter(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        folio=folio,
    ).exists():
        raise ServiceError(
            f'Ya existe un documento {tipo_dte.label} folio {folio} '
            f'para este contribuyente.',
        )

    receptor = _resolver_receptor(contribuyente, encabezado['Receptor'])
    fecha = date.fromisoformat(encabezado['IdDoc']['FchEmis'])
    neto, exento, iva, total = montos_en_clp(encabezado)

    return DteEmitido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        receptor=receptor,
        usuario=usuario,
        folio=folio,
        periodo=fecha.year * 100 + fecha.month,
        fecha=fecha,
        neto=neto,
        exento=exento,
        iva=iva,
        total=total,
        xml_base64=bag.xml_base64,
    )


def _resolver_referencias(
    contribuyente: Contribuyente,
    input_data: dict[str, Any],
) -> list[tuple[DteEmitido, int | None, str]]:
    """
    Resuelve `input_data['Referencia']` contra los `DteEmitido` ya emitidos.

    Solo se resuelven referencias cuyo `TpoDocRef` corresponde a un
    `TipoDte` conocido (documento tributario electrónico) — otro tipo
    de respaldo (ej. HES, guía en papel) no tiene representación en
    `TipoDte` y se descarta sin error: no aporta señal de clasificación
    (`DteEmitido.libro()`) ni es algo que este sistema pueda resolver.

    Para las que sí corresponden a un DTE, el documento referenciado
    debe existir entre los ya emitidos de este contribuyente — si no,
    es un error de negocio: no se puede timbrar una referencia a algo
    que el sistema no conoce, y sin esa referencia resuelta el libro de
    una Nota de Crédito/Débito quedaría mal clasificado.
    """
    resueltas: list[tuple[DteEmitido, int | None, str]] = []
    for referencia in input_data.get('Referencia', []) or []:
        tpo_doc_ref = referencia.get('TpoDocRef')
        if tpo_doc_ref is None or not str(tpo_doc_ref).isdigit():
            continue
        tipo_dte_ref = TipoDte.objects.filter(codigo=int(tpo_doc_ref)).first()
        if tipo_dte_ref is None:
            continue

        try:
            folio_ref = int(referencia.get('FolioRef'))
        except TypeError, ValueError:
            continue
        if folio_ref <= 0:
            continue

        referenciado = DteEmitido.objects.filter(
            contribuyente=contribuyente,
            tipo_dte=tipo_dte_ref,
            folio=folio_ref,
        ).first()
        if referenciado is None:
            raise ServiceError(
                f'El documento referenciado (tipo {tipo_dte_ref.codigo}, '
                f'folio {folio_ref}) no existe entre los DTE emitidos de '
                f'este contribuyente — solo se puede referenciar '
                f'documentos ya emitidos en el sistema.',
            )

        try:
            cod_ref = int(referencia.get('CodRef'))
        except TypeError, ValueError:
            cod_ref = None

        resueltas.append(
            (referenciado, cod_ref, referencia.get('RazonRef') or ''),
        )
    return resueltas


def _persistir_referencias(
    dte_emitido: DteEmitido,
    resueltas: list[tuple[DteEmitido, int | None, str]],
) -> None:
    """Persiste las referencias ya resueltas por `_resolver_referencias()`."""
    for referenciado, cod_ref, razon in resueltas:
        DteEmitidoReferencia.objects.create(
            emitido=dte_emitido,
            referencia=referenciado,
            tipo_referencia=cod_ref,
            razon=razon,
        )


def _emisor_payload_plano(contribuyente: Contribuyente) -> dict[str, Any]:
    """
    Mismos datos que `_emisor_payload()`, en llaves planas.

    Sin nodo `Emisor` anidado — es lo que espera `form.estandar`. El
    teléfono es la excepción de nombre: `form.estandar` lee la entrada
    como `TelefonoEmisor` (no `Telefono`, a diferencia del XML final —
    ver `EstandarParserStrategy::setInitialDTE()`).
    """
    payload: dict[str, Any] = {
        'RUTEmisor': f'{contribuyente.rut}-{contribuyente.dv}',
        'RznSoc': contribuyente.razon_social,
        'GiroEmis': contribuyente.giro,
        'DirOrigen': contribuyente.direccion,
        'CmnaOrigen': contribuyente.comuna.glosa,
    }
    actividad = contribuyente.actividad_economica_principal
    if actividad:
        payload['Acteco'] = actividad.codigo
    if contribuyente.telefono:
        payload['TelefonoEmisor'] = contribuyente.telefono
    if contribuyente.correo:
        payload['CorreoEmisor'] = contribuyente.correo
    return payload


def _receptor_payload_plano(receptor: Receptor) -> dict[str, Any]:
    """
    Mismos datos que `_receptor_payload()`, en llaves planas.

    `form.estandar` no tiene un nodo `Extranjero` anidado, usa
    `Nacionalidad` directo (ver
    `EstandarParserStrategy::addExportData()`).
    """
    payload: dict[str, Any] = {
        'RUTRecep': f'{receptor.rut}-{receptor.dv}',
        'RznSocRecep': receptor.razon_social,
        'GiroRecep': receptor.giro,
        'DirRecep': receptor.direccion,
    }
    if receptor.codigo_interno:
        payload['CdgIntRecep'] = receptor.codigo_interno
    if receptor.telefono:
        payload['Contacto'] = receptor.telefono
    if receptor.correo:
        payload['CorreoRecep'] = receptor.correo
    if receptor.comuna:
        payload['CmnaRecep'] = receptor.comuna.glosa
    if receptor.ciudad:
        payload['CiudadRecep'] = receptor.ciudad
    if receptor.es_extranjero:
        payload['Nacionalidad'] = receptor.pais.codigo
        if receptor.numero_identificacion:
            payload['NumId'] = receptor.numero_identificacion
    return payload


def _emisor_payload(contribuyente: Contribuyente) -> dict[str, Any]:
    """
    `Encabezado.Emisor` desde un `Contribuyente` ya persistido.

    `Acteco` solo se agrega si el contribuyente tiene una actividad
    económica marcada como principal — no es un dato que el modelo
    exija hoy (ver `Contribuyente.actividad_economica_principal`).
    """
    payload: dict[str, Any] = {
        'RUTEmisor': f'{contribuyente.rut}-{contribuyente.dv}',
        'RznSoc': contribuyente.razon_social,
        'GiroEmis': contribuyente.giro,
        'DirOrigen': contribuyente.direccion,
        'CmnaOrigen': contribuyente.comuna.glosa,
    }
    actividad = contribuyente.actividad_economica_principal
    if actividad:
        payload['Acteco'] = actividad.codigo
    if contribuyente.telefono:
        payload['Telefono'] = contribuyente.telefono
    if contribuyente.correo:
        payload['CorreoEmisor'] = contribuyente.correo
    return payload


def _receptor_payload(receptor: Receptor) -> dict[str, Any]:
    """
    `Encabezado.Receptor` desde un `Receptor` ya persistido.

    Un receptor extranjero no tiene `comuna` (`ciudad`/`pais` en su
    lugar, ver docstring de `Receptor`) — el nodo `Extranjero` solo se
    agrega en ese caso, igual que en un DTE real, o si el receptor tiene
    su número de identificación (`NumId`), que puede venir sin
    nacionalidad (ej. una exportación cargada por planilla, que no
    tiene esa columna).
    """
    payload: dict[str, Any] = {
        'RUTRecep': f'{receptor.rut}-{receptor.dv}',
        'RznSocRecep': receptor.razon_social,
        'GiroRecep': receptor.giro,
        'DirRecep': receptor.direccion,
    }
    if receptor.codigo_interno:
        payload['CdgIntRecep'] = receptor.codigo_interno
    if receptor.telefono:
        payload['Contacto'] = receptor.telefono
    if receptor.correo:
        payload['CorreoRecep'] = receptor.correo
    if receptor.comuna:
        payload['CmnaRecep'] = receptor.comuna.glosa
    if receptor.es_extranjero:
        payload['Extranjero'] = {'Nacionalidad': receptor.pais.codigo}
    if receptor.numero_identificacion:
        payload.setdefault('Extranjero', {})['NumId'] = (
            receptor.numero_identificacion
        )
    return payload
