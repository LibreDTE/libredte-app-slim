"""Plugin `libredte_lib_api`: apunta a otra instancia de LibreDTE Lib API."""

from __future__ import annotations

from typing import Any, ClassVar

from django.conf import settings

from apps.core.plugin.base import BasePlugin, BasePluginCapability

from ..contracts import LibredteBackendPluginCapabilityDefinition
from .capabilities import LibredteBackendPluginCapability
from .forms import LibredteLibApiConfigForm


class LibredteLibApiPlugin(BasePlugin):
    """
    Backend `libredte.backend` alternativo: otra instancia de LibreDTE Lib API.

    Mismo backend que ya construye por defecto
    `apps/libredte/services/libredte_backend.py::get_backend()` (vía
    `PLUGIN_LIBREDTE_BACKEND_API_URL`) — la diferencia es que acá el
    `base_url`/`api_token` pueden venir de `PluginConfig.config`, por
    tenant, en vez de los valores globales en `settings`. Un tenant
    que no configura los suyos sigue usando los globales (ver
    `LibredteBackendPluginCapability`) — activar el plugin sin
    configurar nada no cambia nada, es el mismo comportamiento de
    siempre.
    """

    id = 'libredte_lib_api'
    label = 'LibreDTE Lib API'
    description = (
        'Por defecto LibreDTE Slim usa LibreDTE Lib Core como backend. '
        '¿Quieres más funcionalidades? '
        '¡Activa este plugin y usa LibreDTE Lib Pro o API Gateway!'
    )
    config_form = LibredteLibApiConfigForm
    template_name = 'libredte/plugins/libredte_lib_api_configure.html'
    capabilities: ClassVar[
        dict[type[BasePluginCapability], type[BasePluginCapability]]
    ] = {
        LibredteBackendPluginCapabilityDefinition: (
            LibredteBackendPluginCapability
        ),
    }

    def get_extra_context(self) -> dict[str, Any]:
        """Si hay un token global de reserva, para el aviso en la plantilla."""
        return {
            'has_global_token': bool(
                settings.PLUGIN_LIBREDTE_BACKEND_API_TOKEN
            ),
        }
