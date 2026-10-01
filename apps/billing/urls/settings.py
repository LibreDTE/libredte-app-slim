"""
URLs de `billing` bajo Configuración (prefijo `/settings/billing/`).

Namespace `billing_settings`, no `billing`: Django no resuelve
`reverse()`/`{% url %}` de forma confiable cuando dos `include()`
distintos declaran el mismo `app_name` (ver `urls.W005`) — con un
namespace propio para esta mitad no hay ambigüedad. Ver `urls/app.py`
(páginas de la app en sí, prefijo `/billing/`, namespace `billing`) y
`config/urls.py`.
"""

from django.urls import path

from ..views import settings as views

app_name = 'billing_settings'

urlpatterns = [
    path('ambiente/', views.ambiente, name='ambiente'),
    path(
        'ambiente/sii-datos-empresa/',
        views.ambiente_sii_datos_empresa,
        name='ambiente_sii_datos_empresa',
    ),
    path(
        'ambiente/sii-usuarios/',
        views.ambiente_sii_usuarios,
        name='ambiente_sii_usuarios',
    ),
    path('items/', views.items, name='items'),
    path('items/nuevo/', views.ItemCreateView.as_view(), name='item_nuevo'),
    path(
        'items/<int:pk>/editar/',
        views.ItemUpdateView.as_view(),
        name='item_editar',
    ),
    path(
        'items/<int:pk>/eliminar/',
        views.ItemDeleteView.as_view(),
        name='item_eliminar',
    ),
    path(
        'items/categorias/nueva/',
        views.ItemCategoriaCreateView.as_view(),
        name='item_categoria_nueva',
    ),
    path(
        'items/categorias/<int:pk>/editar/',
        views.ItemCategoriaUpdateView.as_view(),
        name='item_categoria_editar',
    ),
    path(
        'items/categorias/<int:pk>/eliminar/',
        views.ItemCategoriaDeleteView.as_view(),
        name='item_categoria_eliminar',
    ),
    path('folios/', views.folios, name='folios'),
    path('folios/subir/', views.folio_subir_caf, name='folio_subir_caf'),
    path(
        'folios/solicitar/',
        views.folio_solicitar_caf,
        name='folio_solicitar_caf',
    ),
    path('folios/<int:pk>/', views.folio_detalle, name='folio_detalle'),
    path(
        'folios/<int:pk>/modificar/',
        views.folio_modificar,
        name='folio_modificar',
    ),
    path(
        'folios/<int:pk>/solicitar/',
        views.folio_solicitar_caf,
        name='folio_solicitar_caf_tipo',
    ),
    path(
        'folios/<int:pk>/reobtener/',
        views.folio_reobtener_caf,
        name='folio_reobtener_caf',
    ),
    path(
        'folios/<int:pk>/reobtener/cargar/',
        views.folio_reobtener_caf_cargar,
        name='folio_reobtener_caf_cargar',
    ),
    path(
        'folios/<int:pk>/anular/',
        views.folio_anular_caf,
        name='folio_anular_caf',
    ),
    path(
        'folios/caf/<int:pk>/xml/',
        views.caf_descargar_xml,
        name='caf_descargar_xml',
    ),
    path(
        'folios/caf/<int:pk>/eliminar/',
        views.CafDeleteView.as_view(),
        name='caf_eliminar',
    ),
]
