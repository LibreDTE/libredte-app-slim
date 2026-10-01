"""Plugin `apigatewaycl`: conexión a apigateway.cl para consultar al SII."""

from __future__ import annotations

from typing import Any, ClassVar

from django.conf import settings

from apps.core.plugin.base import BasePlugin, BasePluginCapability

from ..contracts import SiiBackendPluginCapabilityDefinition
from .capabilities import SiiBackendPluginCapability
from .forms import ApiGatewayClConfigForm


class ApiGatewayClPlugin(BasePlugin):
    """Conexión a la API de www.apigateway.cl para consultar al SII."""

    id = 'apigatewaycl'
    label = 'API Gateway'
    description = (
        'Conecta LibreDTE Slim a www.apigateway.cl para consultar al SII. '
        'Podrás desbloquear las funcionalidades extra de LibreDTE Slim.'
    )
    config_form = ApiGatewayClConfigForm
    template_name = 'libredte/plugins/apigatewaycl_configure.html'
    capabilities: ClassVar[
        dict[type[BasePluginCapability], type[BasePluginCapability]]
    ] = {
        SiiBackendPluginCapabilityDefinition: SiiBackendPluginCapability,
    }

    def get_extra_context(self) -> dict[str, Any]:
        """Si hay un token global de reserva, para el aviso en la plantilla."""
        return {
            'has_global_token': bool(settings.PLUGIN_APIGATEWAYCL_API_TOKEN),
        }
