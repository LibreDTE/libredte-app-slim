"""
URLs de `accounting` bajo Configuración (prefijo `/settings/accounting/`).

Ver `apps/billing/urls/settings.py` para el motivo del namespace propio.
"""

from django.urls import path

from ..views import settings as views

app_name = 'accounting_settings'

urlpatterns = [
    path('cuentas/', views.cuentas, name='cuentas'),
]
