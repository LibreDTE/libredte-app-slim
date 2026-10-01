"""
URLs de `libredte` bajo Configuración (prefijo `/settings/libredte/`).

Namespace `libredte_settings`, no `libredte`: Django no resuelve
`reverse()`/`{% url %}` de forma confiable cuando dos `include()`
distintos declaran el mismo `app_name` (ver `urls.W005`) — con un
namespace propio para esta mitad no hay ambigüedad. Ver `urls/app.py`
(páginas de la app en sí, prefijo `/libredte/`, namespace `libredte`) y
`config/urls.py`.
"""

from django.urls import path

from ..views import settings as views

app_name = 'libredte_settings'

urlpatterns = [
    path('empresa/', views.empresa, name='empresa'),
    path('certificado/', views.certificado, name='certificado'),
    path('actividades/', views.actividades, name='actividades'),
    path('sucursales/', views.sucursales, name='sucursales'),
    path(
        'sucursales/nueva/',
        views.SucursalCreateView.as_view(),
        name='sucursal_nueva',
    ),
    path(
        'sucursales/<int:pk>/editar/',
        views.SucursalUpdateView.as_view(),
        name='sucursal_editar',
    ),
    path(
        'sucursales/<int:pk>/eliminar/',
        views.SucursalDeleteView.as_view(),
        name='sucursal_eliminar',
    ),
]
