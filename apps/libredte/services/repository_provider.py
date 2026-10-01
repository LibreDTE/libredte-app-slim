"""
Servicio: catálogos reales de `libredte-lib-core` (comuna, país).

Único módulo de esta app que llama a `system.repository.catalog` del
SDK. Los catálogos de detalle de un documento (formas de pago, Aduana,
tipos de DTE) viven en el `repository_provider` propio de `billing` —
son específicos de facturación, no de esta base compartida.
"""

from __future__ import annotations

from typing import Any

from libredte_lib_sdk.exceptions import LibreDteSdkError

from .exceptions import wrap
from .libredte_backend import get_backend

_DOCUMENT_ENTITY = 'libredte\\lib\\Core\\Package\\Billing\\Component\\Document'
_COMUNA_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\Comuna'
_PAIS_REPOSITORY = f'{_DOCUMENT_ENTITY}\\Entity\\AduanaPais'


def _find_all(repository: str) -> list[dict[str, Any]]:
    """Todos los elementos de `repository`, tal como los entrega la API."""
    try:
        with get_backend() as backend:
            return backend.system.repository.catalog.find_all(repository)
    except LibreDteSdkError as error:
        raise wrap(error) from error


def load_comunas() -> list[dict[str, Any]]:
    """Todas las comunas de Chile."""
    return _find_all(_COMUNA_REPOSITORY)


def load_paises() -> list[dict[str, Any]]:
    """Todos los países (nomenclatura Aduana)."""
    return _find_all(_PAIS_REPOSITORY)
