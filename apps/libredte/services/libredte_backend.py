"""
Punto único de construcción del backend (`LibredteBackend`) para esta app.

Vive en `services/` a propósito: es el único lugar de todo el proyecto
que importa `libredte_lib_sdk` fuera de un módulo de `services/*.py`
que ya lo hace — nada fuera de `services/` debe construir ni llamar al
backend directamente. Se usa como context manager (`with get_backend()
as backend:`), igual que en los ejemplos del propio SDK — cierra la
conexión HTTP al salir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings

from apps.core.plugin.resolver import resolve

from ..plugins.contracts import (
    LibredteBackend,
    LibredteBackendPluginCapabilityDefinition,
)

if TYPE_CHECKING:
    from ..models import Contribuyente


def get_backend(contribuyente: Contribuyente | None = None) -> LibredteBackend:
    """
    El backend de `libredte.backend` activo de `contribuyente`.

    Sin plugin activo, o sin `contribuyente` (operaciones sin tenant,
    ej. catálogos globales — nunca resuelve ningún plugin en ese
    caso), el del `base_url` configurado.
    """
    if contribuyente is not None:
        capability = resolve(
            LibredteBackendPluginCapabilityDefinition, tenant=contribuyente
        )
        if capability is not None:
            assert isinstance(
                capability, LibredteBackendPluginCapabilityDefinition
            )
            return capability.get_backend()
    return LibredteBackend(
        base_url=settings.PLUGIN_LIBREDTE_BACKEND_API_URL,
        auth_scheme=settings.PLUGIN_LIBREDTE_BACKEND_API_AUTH_SCHEME,
    )
