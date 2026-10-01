"""URLs de `libredte` (prefijo `/libredte/`)."""

from __future__ import annotations

from django.urls import path

from ..views import app as views

app_name = 'libredte'

urlpatterns = [
    path(
        'contribuyente/nuevo/',
        views.ContribuyenteWizardView.as_view(),
        name='wizard_contribuyente',
    ),
    path('contribuyentes/', views.contribuyentes, name='contribuyentes'),
    path(
        'contribuyentes/<int:rut>/seleccionar/',
        views.contribuyente_seleccionar,
        name='contribuyente_seleccionar',
    ),
    path('certificados/', views.certificados, name='certificados'),
    path(
        'certificados/<int:pk>/eliminar/',
        views.CertificadoDeleteView.as_view(),
        name='certificado_eliminar',
    ),
]
