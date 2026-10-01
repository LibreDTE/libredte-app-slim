"""
Punto único de construcción del backend (`SiiBackend`) para esta app.

Vive en `services/` a propósito, igual que `libredte_backend.py` para
`libredte.backend`: nada fuera de `services/*.py` debe construir ni
llamar al cliente de `apigatewaycl` directamente.

A diferencia de `libredte_backend.py`, acá no hay un `SiiBackend` de
reserva para operaciones sin tenant — sin `contribuyente` no tiene
sentido resolver ningún plugin (a diferencia de `libredte.backend`,
`sii.backend` no sirve catálogos globales sin tenant), así que
simplemente no hay backend. El fallback a la cuenta de la plataforma
(`PLUGIN_APIGATEWAYCL_API_URL`/`PLUGIN_APIGATEWAYCL_API_TOKEN`) vive
un nivel más abajo, dentro de `SiiBackendPluginCapability` — solo
aplica cuando el plugin SÍ está activo pero el tenant no configuró su
propia cuenta (ver `apps/libredte/plugins/apigatewaycl/config_resolver.py`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.core.plugin.catalog import plugins_for_capability
from apps.core.plugin.resolver import resolve

from ..plugins.contracts import (
    SiiBackend,
    SiiBackendPluginCapabilityDefinition,
)

if TYPE_CHECKING:
    from ..models import Contribuyente


def get_backend(
    contribuyente: Contribuyente | None = None,
) -> SiiBackend | None:
    """El backend de `sii.backend` activo de `contribuyente`, si lo tiene."""
    if contribuyente is None:
        return None
    capability = resolve(
        SiiBackendPluginCapabilityDefinition, tenant=contribuyente
    )
    if capability is None:
        return None
    assert isinstance(capability, SiiBackendPluginCapabilityDefinition)
    return capability.get_backend(contribuyente)


def upsell_context() -> dict[str, Any]:
    """
    Contexto para `libredte/_sii_backend_upsell.html`.

    Pensado para cuando `get_backend()` da `None`: qué plugin(s)
    activar para tener `sii.backend` disponible, sin hardcodear
    `apigatewaycl` — si mañana hay más de uno, salen todos.
    """
    return {
        'plugins': plugins_for_capability(
            SiiBackendPluginCapabilityDefinition
        ),
    }
