"""URLs de la API (JSON) de `billing`."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = 'billing_api'

urlpatterns = [
    path(
        'emitidos/',
        views.DteEmitidoListView.as_view(),
        name='emitidos',
    ),
    path(
        'recibidos/',
        views.DteRecibidoListView.as_view(),
        name='recibidos',
    ),
    path(
        'borradores/',
        views.BorradorListView.as_view(),
        name='borradores',
    ),
    path(
        'receptores/',
        views.ReceptorListView.as_view(),
        name='receptores',
    ),
    path(
        'receptores/buscar/',
        views.ReceptorBuscarView.as_view(),
        name='receptor_buscar',
    ),
    path(
        'emisores/',
        views.EmisorListView.as_view(),
        name='emisores',
    ),
    path(
        'items/',
        views.ItemListView.as_view(),
        name='items',
    ),
    path(
        'items/categorias/',
        views.ItemCategoriaListView.as_view(),
        name='item_categorias',
    ),
    path(
        'items/buscar/',
        views.ItemBuscarView.as_view(),
        name='item_buscar',
    ),
    path(
        'ventas/periodos/',
        views.VentasPeriodosListView.as_view(),
        name='ventas_periodos',
    ),
    path(
        'compras/periodos/',
        views.ComprasPeriodosListView.as_view(),
        name='compras_periodos',
    ),
    path(
        'compras/documentos/',
        views.ComprasPeriodoDocumentosListView.as_view(),
        name='compras_periodo_documentos',
    ),
]
