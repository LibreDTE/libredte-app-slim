"""
Servicio: catálogos reales de `libredte-lib-core`, de facturación.

Único módulo de esta app que llama a `system.repository.catalog` del
SDK — nada fuera de `services/*.py` debe tocarlo directamente. No
modela cada repositorio como DTO (el esquema varía por repositorio
pedido, ver el propio SDK): devuelve el `dict`/`list[dict]` tal cual
la API, listo para que quien llame lo mapee a sus propios modelos.

Comuna/país viven en el `repository_provider` de `apps/libredte/` —
son parte de la base compartida, no de facturación.
"""

from __future__ import annotations

from typing import Any

from libredte_lib_sdk.exceptions import LibreDteSdkError

from apps.libredte.services.exceptions import wrap
from apps.libredte.services.libredte_backend import get_backend

_DOCUMENT_ENTITY = 'libredte\\lib\\Core\\Package\\Billing\\Component\\Document'
_TIPO_DOCUMENTO_REPOSITORY = (
    f'{_DOCUMENT_ENTITY}\\Contract\\TipoDocumentoInterface'
)
_TRASLADO_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\Traslado'
_FORMA_PAGO_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\FormaPago'
_ADUANA_FORMA_PAGO_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\AduanaFormaPago'
_MEDIO_PAGO_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\MedioPago'
_IMPUESTO_ADICIONAL_REPOSITORY = (
    f'{_DOCUMENT_ENTITY}\\Entity\\ImpuestoAdicionalRetencion'
)
_ADUANA_TRANSPORTE_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\AduanaTransporte'
_ADUANA_MODALIDAD_VENTA_REPOSITORY = (
    f'{_DOCUMENT_ENTITY}\\Entity\\AduanaModalidadVenta'
)
_ADUANA_CLAUSULA_VENTA_REPOSITORY = (
    f'{_DOCUMENT_ENTITY}\\Entity\\AduanaClausulaVenta'
)
_ADUANA_UNIDAD_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\AduanaUnidad'
_ADUANA_PUERTO_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\AduanaPuerto'
_ADUANA_TIPO_BULTO_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\AduanaTipoBulto'
_ADUANA_MONEDA_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\AduanaMoneda'


def _find_all(repository: str) -> list[dict[str, Any]]:
    """Todos los elementos de `repository`, tal como los entrega la API."""
    try:
        with get_backend() as backend:
            return backend.system.repository.catalog.find_all(repository)
    except LibreDteSdkError as error:
        raise wrap(error) from error


def load_tipos_dte(codigos: list[int]) -> list[dict[str, Any]]:
    """Tipos de documento cuyo código está en `codigos`."""
    try:
        with get_backend() as backend:
            return backend.system.repository.catalog.find_by(
                _TIPO_DOCUMENTO_REPOSITORY,
                criteria={'codigo': codigos},
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error


def load_traslados() -> list[dict[str, Any]]:
    """Indicadores de traslado (guía de despacho)."""
    return _find_all(_TRASLADO_REPOSITORY)


def load_formas_pago() -> list[dict[str, Any]]:
    """Formas de pago (contado/crédito/etc) del SII."""
    return _find_all(_FORMA_PAGO_REPOSITORY)


def load_aduana_formas_pago() -> list[dict[str, Any]]:
    """Formas de pago de exportación (`FmaPagExp`), nomenclatura Aduana."""
    return _find_all(_ADUANA_FORMA_PAGO_REPOSITORY)


def load_medios_pago() -> list[dict[str, Any]]:
    """Medios de pago (efectivo/transferencia/etc) de un pago programado."""
    return _find_all(_MEDIO_PAGO_REPOSITORY)


def load_impuestos_adicionales() -> list[dict[str, Any]]:
    """Impuestos adicionales o retenciones aplicables a un ítem."""
    return _find_all(_IMPUESTO_ADICIONAL_REPOSITORY)


def load_aduana_transportes() -> list[dict[str, Any]]:
    """Vías de transporte internacional (marítimo/aéreo/etc), Aduana."""
    return _find_all(_ADUANA_TRANSPORTE_REPOSITORY)


def load_aduana_modalidades_venta() -> list[dict[str, Any]]:
    """Modalidades de venta de una exportación, Aduana."""
    return _find_all(_ADUANA_MODALIDAD_VENTA_REPOSITORY)


def load_aduana_clausulas_venta() -> list[dict[str, Any]]:
    """Cláusulas de venta (CIF/CFR/FOB/etc) de una exportación, Aduana."""
    return _find_all(_ADUANA_CLAUSULA_VENTA_REPOSITORY)


def load_aduana_unidades() -> list[dict[str, Any]]:
    """Unidades de peso/medida (tara, peso bruto/neto), Aduana."""
    return _find_all(_ADUANA_UNIDAD_REPOSITORY)


def load_aduana_puertos() -> list[dict[str, Any]]:
    """Puertos de embarque/desembarque de una exportación, Aduana."""
    return _find_all(_ADUANA_PUERTO_REPOSITORY)


def load_aduana_tipos_bulto() -> list[dict[str, Any]]:
    """Tipos de bulto/embalaje de una exportación, Aduana."""
    return _find_all(_ADUANA_TIPO_BULTO_REPOSITORY)


def load_aduana_monedas() -> list[dict[str, Any]]:
    """Monedas de un documento de exportación, Aduana."""
    return _find_all(_ADUANA_MONEDA_REPOSITORY)
