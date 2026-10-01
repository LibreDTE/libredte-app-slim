"""
Registro de `billing` en los menús de `core`.

Importado por `core.apps.CoreConfig.ready()` vía
`autodiscover_modules('platform')` — el `import` en sí ya registra,
nada de esto se llama a mano.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.core.plugin.catalog import register_capability
from apps.core.registrations import DashboardWidget, MenuItem, MenuSection
from apps.core.registry import register

from .plugins.contracts import DocumentRendererPluginCapabilityDefinition
from .services.dashboard_reporter import get_dashboard_stats

register_capability(DocumentRendererPluginCapabilityDefinition)

# Sin columna de estado SII acá: "Estado ante el SII" (gráfico) y
# "Documentos con reparos" (KPI) ya cubren eso en la misma página —
# repetirlo en esta tabla angosta solo le quita espacio a las demás
# columnas. "Documento"/"Folio" se combinan en una sola columna por el
# mismo motivo: es una tarjeta de media página, no la lista completa de
# "Documentos emitidos" (esa sí separa ambos datos en columnas propias).
# Config de presentación (Tabulator), no un dato de negocio — por eso
# vive acá, no en `DashboardStats`.
_LAST_DOCUMENTS_COLUMNS = [
    {
        'title': 'Documento',
        'field': 'documento',
        'widthGrow': 2,
        'minWidth': 200,
    },
    {
        'title': 'Receptor',
        'field': 'receptor',
        'widthGrow': 2,
        'minWidth': 140,
    },
    {
        'title': 'Total',
        'field': 'total',
        'hozAlign': 'right',
        'formatter': 'money',
        'formatterParams': {'symbol': '$', 'precision': 0},
        'width': 110,
    },
    {'title': 'Fecha', 'field': 'fecha', 'width': 130},
]

# Igual que `_LAST_DOCUMENTS_COLUMNS`, pero para "Últimos recibidos"
# (`Emisor` en vez de `Receptor` — es la contraparte del documento).
_LAST_RECEIVED_COLUMNS = [
    {
        'title': 'Documento',
        'field': 'documento',
        'widthGrow': 2,
        'minWidth': 200,
    },
    {
        'title': 'Emisor',
        'field': 'emisor',
        'widthGrow': 2,
        'minWidth': 140,
    },
    {
        'title': 'Total',
        'field': 'total',
        'hozAlign': 'right',
        'formatter': 'money',
        'formatterParams': {'symbol': '$', 'precision': 0},
        'width': 110,
    },
    {'title': 'Fecha', 'field': 'fecha', 'width': 130},
]


def _dashboard_context(request: HttpRequest) -> dict[str, Any]:
    """Contexto del widget de dashboard (`?periodo=` viene de la URL)."""
    periodo_param = request.GET.get('periodo')
    periodo = (
        int(periodo_param)
        if periodo_param and periodo_param.isdigit()
        else None
    )
    return {
        'stats': get_dashboard_stats(request, periodo=periodo),
        'last_documents_columns': _LAST_DOCUMENTS_COLUMNS,
        'last_received_columns': _LAST_RECEIVED_COLUMNS,
    }


register(
    'menu',
    MenuSection(
        label='Facturación',
        icon='file-invoice-dollar',
        priority=10,
        items=[
            MenuItem(
                'Emitir',
                'billing:emitir',
                'file-circle-plus',
                '/billing/emitir',
            ),
            MenuItem(
                'Emitir masivo',
                'billing:emitir_masivo',
                'file-arrow-up',
                '/billing/emitir/masivo',
            ),
            MenuItem(
                'Borradores',
                'billing:borradores',
                'file-pen',
                '/billing/borradores',
            ),
            MenuItem(
                'Emitidos',
                'billing:emitidos',
                'file-lines',
                '/billing/emitidos',
            ),
            MenuItem(
                'Recibidos',
                'billing:recibidos',
                'file-import',
                '/billing/recibidos',
            ),
            MenuItem(
                'Ventas',
                'billing:ventas',
                'chart-line',
                '/billing/ventas',
            ),
            MenuItem(
                'Compras',
                'billing:compras',
                'cart-shopping',
                '/billing/compras',
            ),
            MenuItem(
                'Receptores',
                'billing:receptores',
                'address-book',
                '/billing/receptores',
            ),
            MenuItem(
                'Emisores',
                'billing:emisores',
                'building',
                '/billing/emisores',
            ),
        ],
    ),
)
register(
    'settings',
    MenuSection(
        label='Facturación',
        icon='file-invoice-dollar',
        priority=10,
        items=[
            MenuItem(
                'Ambiente',
                'billing_settings:ambiente',
                'globe',
                '/settings/billing/ambiente',
            ),
            MenuItem(
                'Folios',
                'billing_settings:folios',
                'hashtag',
                '/settings/billing/folios',
            ),
            MenuItem(
                'Ítems',
                'billing_settings:items',
                'boxes-stacked',
                '/settings/billing/items',
            ),
        ],
    ),
)
register(
    'dashboard',
    DashboardWidget(
        template='billing/dashboard_widget.html',
        get_context=_dashboard_context,
        priority=10,
    ),
)
