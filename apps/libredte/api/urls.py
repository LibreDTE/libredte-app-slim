"""URLs de la API (JSON) de `libredte`."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = 'libredte_api'

urlpatterns = [
    path(
        'sucursales/',
        views.SucursalListView.as_view(),
        name='sucursales',
    ),
]
