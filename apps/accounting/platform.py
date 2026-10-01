"""
Registro de `accounting` en los menús de `core`.

Importado por `core.apps.CoreConfig.ready()` vía
`autodiscover_modules('platform')` — el `import` en sí ya registra,
nada de esto se llama a mano. Ver `apps/billing/platform.py` para el
mismo patrón ya en uso.
"""

from __future__ import annotations

from apps.core.registrations import MenuItem, MenuSection
from apps.core.registry import register

register(
    'menu',
    MenuSection(
        label='Contabilidad',
        icon='book',
        priority=20,
        items=[
            MenuItem(
                'Registrar asiento',
                'accounting:registrar',
                'square-plus',
                '/accounting/registrar',
            ),
            MenuItem(
                'Asientos',
                'accounting:asientos',
                'list',
                '/accounting/asientos',
            ),
            MenuItem(
                'Libro diario',
                'accounting:libro_diario',
                'book-open',
                '/accounting/libro-diario',
            ),
            MenuItem(
                'Libro mayor',
                'accounting:libro_mayor',
                'book-open-reader',
                '/accounting/libro-mayor',
            ),
            MenuItem(
                'Balance general',
                'accounting:balance_general',
                'scale-balanced',
                '/accounting/balance-general',
            ),
        ],
    ),
)
register(
    'settings',
    MenuSection(
        label='Contabilidad',
        icon='book',
        priority=20,
        items=[
            MenuItem(
                'Plan de cuentas',
                'accounting_settings:cuentas',
                'list-check',
                '/settings/accounting/cuentas',
            ),
        ],
    ),
)
