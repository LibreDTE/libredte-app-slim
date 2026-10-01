"""
Shell de Configuración (prefijo `/settings/`).

Namespace `core_settings`, no `core`: Django no resuelve
`reverse()`/`{% url %}` de forma confiable cuando dos `include()`
distintos declaran el mismo `app_name` (ver `urls.W005`) — con un
namespace propio para esta mitad no hay ambigüedad. Ver `urls/app.py`
(dashboard/perfil/sudo/setup, sin prefijo, namespace `core`) y
`config/urls.py`.
"""

from django.urls import path

from ..views import settings as views

app_name = 'core_settings'

urlpatterns = [
    path('', views.settings_index, name='settings_index'),
    path('plugins/', views.plugins, name='plugins'),
    path(
        'plugins/<str:plugin_id>/',
        views.plugin_configure,
        name='plugin_configure',
    ),
]
