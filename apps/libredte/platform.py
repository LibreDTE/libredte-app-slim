"""
Registro de `libredte` en los menús de `core`.

Importado por `core.apps.CoreConfig.ready()` vía
`autodiscover_modules('platform')` — el `import` en sí ya registra,
nada de esto se llama a mano.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.core.auth import require_authenticated_user
from apps.core.plugin.catalog import register_capability
from apps.core.registrations import MenuItem, MenuSection, ProfileSection
from apps.core.registry import register
from apps.core.tenant import register_tenant_resolver

from .forms import CertificadoUploadForm
from .plugins.contracts import (
    LibredteBackendPluginCapabilityDefinition,
    SiiBackendPluginCapabilityDefinition,
)
from .tenancy import get_current_contribuyente

register_tenant_resolver(get_current_contribuyente)

register_capability(LibredteBackendPluginCapabilityDefinition)
register_capability(SiiBackendPluginCapabilityDefinition)

register(
    'settings',
    MenuSection(
        label='LibreDTE',
        icon='building',
        priority=5,
        items=[
            MenuItem(
                'Mi empresa',
                'libredte_settings:empresa',
                'building',
                '/settings/libredte/empresa',
            ),
            MenuItem(
                'Actividades económicas',
                'libredte_settings:actividades',
                'briefcase',
                '/settings/libredte/actividades',
            ),
            MenuItem(
                'Sucursales',
                'libredte_settings:sucursales',
                'store',
                '/settings/libredte/sucursales',
            ),
            MenuItem(
                'Certificado digital',
                'libredte_settings:certificado',
                'file-shield',
                '/settings/libredte/certificado',
            ),
        ],
    ),
)


def _certificados_context(request: HttpRequest) -> dict[str, Any]:
    """Contexto de la pestaña "Certificados" del perfil."""
    return {
        'form': CertificadoUploadForm(),
        'certificados': require_authenticated_user(request).certificados.all(),
    }


register(
    'profile',
    ProfileSection(
        label='Certificados',
        tab_id='certificados',
        template='libredte/_profile_certificados.html',
        get_context=_certificados_context,
        priority=10,
    ),
)
