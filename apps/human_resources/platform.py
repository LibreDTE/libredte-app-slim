"""
Registro de `human_resources` en los menús de `core`.

Importado por `core.apps.CoreConfig.ready()` vía
`autodiscover_modules('platform')` — el `import` en sí ya registra,
nada de esto se llama a mano. Ver `apps/billing/platform.py` para el
mismo patrón ya en uso.
"""

from __future__ import annotations

from apps.core.plugin.catalog import register_capability
from apps.core.registrations import MenuItem, MenuSection
from apps.core.registry import register

from .plugins.contracts import PayslipRendererPluginCapabilityDefinition

register_capability(PayslipRendererPluginCapabilityDefinition)

register(
    'menu',
    MenuSection(
        label='Recursos Humanos',
        icon='people-group',
        priority=30,
        items=[
            MenuItem(
                'Empleados',
                'human_resources:empleados',
                'id-card',
                '/human_resources/empleados',
            ),
            MenuItem(
                'Calcular liquidación',
                'human_resources:calcular',
                'calculator',
                '/human_resources/calcular',
            ),
            MenuItem(
                'Liquidaciones',
                'human_resources:liquidaciones',
                'file-invoice',
                '/human_resources/liquidaciones',
            ),
        ],
    ),
)
