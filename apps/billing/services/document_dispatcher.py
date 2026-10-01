"""
Servicio: envío de un DTE emitido al SII y consulta de su estado.

Único módulo que llama a `integration.sii_dte` del SDK — nada fuera de
`services/*.py` debe tocarlo directamente (`document.dispatcher`
también lo usa `document_receiver.py`, para el sentido inverso: cargar
un sobre recibido en vez de armar uno para enviar).

Con un certificado de prueba (autofirmado, ej.
`certificate_manager.create_fake_certificate`) el envío real al SII
siempre falla en la autenticación — es una limitación del SII mismo,
no de este servicio: un certificado no lo emite una entidad
certificadora real. Con un certificado real, funciona igual contra
certificación (`Contribuyente.autorizacion_dte_resolucion_numero == 0`)
o producción.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from libredte_lib_sdk.billing.enums import SiiEnvironment
from libredte_lib_sdk.exceptions import LibreDteSdkError

from apps.libredte.models import Contribuyente
from apps.libredte.services import certificate_manager
from apps.libredte.services.exceptions import ServiceError, wrap
from apps.libredte.services.libredte_backend import get_backend

from ..models import DteEmitido


def send(documento: DteEmitido) -> DteEmitido:
    """
    Envía `documento` al SII: arma el sobre `EnvioDTE` y lo envía.

    Requiere que `documento.track_id` sea `None` — un documento ya
    enviado no se reenvía (usar `check_status()` para consultar su
    estado en vez de enviarlo de nuevo). Guarda el `track_id` que
    devuelve el SII.
    """
    if documento.track_id is not None:
        raise ServiceError(
            'Este documento ya fue enviado al SII (Track ID '
            f'{documento.track_id}) — no se puede reenviar.',
        )

    contribuyente = documento.contribuyente
    certificate = certificate_manager.certificate_for(contribuyente)

    try:
        with get_backend(contribuyente) as backend:
            bag = backend.billing.document.loader.load_xml(
                documento.xml_base64,
            )
            # `emisor` siempre viene poblado tras cargar un XML real
            # (ver docstring de `DocumentBag`) — el tipo es `Optional`
            # solo porque la bolsa también puede representar un
            # documento todavía sin construir.
            assert bag.emisor is not None
            bag = dataclasses.replace(
                bag,
                certificate=certificate,
                emisor={
                    **bag.emisor,
                    **_autorizacion_dte_extra(contribuyente),
                },
            )
            sobre = backend.billing.document.dispatcher.create(bag)
            resultado = backend.billing.integration.sii_dte.send(
                sobre.xml_base64,
                certificate=certificate,
                company_rut=_company_rut(contribuyente),
                environment=_environment(contribuyente),
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error

    if resultado.track_id is None:
        raise ServiceError('El SII no devolvió un Track ID para el envío.')

    documento.track_id = resultado.track_id
    documento.save(update_fields=['track_id'])
    return documento


def check_status(documento: DteEmitido) -> DteEmitido:
    """
    Consulta al SII el estado del envío de `documento`.

    Requiere que ya se haya enviado (`documento.track_id` no `None`).
    Actualiza `revision_estado`/`revision_detalle` con lo que devuelva
    el SII, siempre en el mismo formato (`"CÓDIGO - glosa"`) que espera
    el resto de la app para este campo (ver `_CODIGOS_REPARO`/
    `_CODIGOS_RECHAZO` en `services/dashboard_reporter.py`).
    """
    if documento.track_id is None:
        raise ServiceError('Este documento aún no se ha enviado al SII.')

    contribuyente = documento.contribuyente
    certificate = certificate_manager.certificate_for(contribuyente)

    try:
        with get_backend(contribuyente) as backend:
            resultado = backend.billing.integration.sii_dte.check_status(
                documento.track_id,
                certificate=certificate,
                company_rut=_company_rut(contribuyente),
                environment=_environment(contribuyente),
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error

    if resultado.status and resultado.description:
        documento.revision_estado = (
            f'{resultado.status} - {resultado.description}'
        )
    elif resultado.status:
        documento.revision_estado = resultado.status
    documento.revision_detalle = resultado.description or ''
    documento.save(update_fields=['revision_estado', 'revision_detalle'])
    return documento


def _company_rut(contribuyente: Contribuyente) -> str:
    """RUT del emisor, formato `NNNNNNNN-D`."""
    return f'{contribuyente.rut}-{contribuyente.dv}'


def _environment(contribuyente: Contribuyente) -> SiiEnvironment:
    """Ambiente SII — mismo criterio que `Contribuyente.ambiente`."""
    if contribuyente.autorizacion_dte_resolucion_numero == 0:
        return SiiEnvironment.CERTIFICATION
    return SiiEnvironment.PRODUCTION


def _autorizacion_dte_extra(contribuyente: Contribuyente) -> dict[str, Any]:
    """
    `autorizacion_dte` a mezclar en el `emisor` de la bolsa, si existe.

    `DocumentLoaderService.load_xml()` reconstruye el `emisor` desde el
    propio XML del documento — que nunca trae `autorizacion_dte`, no
    es un dato del DTE sino de la relación SII-contribuyente. Se agrega
    aparte para que la carátula del sobre se pueda armar; se omite por
    completo si falta la fecha (`autorizacion_dte_resolucion_fecha` sí
    es un dato real que puede no estar cargado). Ojo: `numero_
    resolucion` no se puede chequear con `and`/truthy — `0` es un
    valor válido (SII, "Resolución N° 0", certificación).
    """
    if contribuyente.autorizacion_dte_resolucion_fecha is None:
        return {}
    return {
        'autorizacion_dte': {
            'fecha_resolucion': (
                contribuyente.autorizacion_dte_resolucion_fecha.isoformat()
            ),
            'numero_resolucion': (
                contribuyente.autorizacion_dte_resolucion_numero
            ),
        },
    }
