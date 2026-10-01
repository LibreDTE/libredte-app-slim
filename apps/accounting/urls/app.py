"""
URLs de `accounting` (prefijo `/accounting/`).

Ver `apps/billing/urls/app.py`/`urls/settings.py` para el motivo del
namespace propio (`accounting`, distinto de `accounting_settings`).
"""

from django.urls import path

from ..views import app as views

app_name = 'accounting'

urlpatterns = [
    path('registrar/', views.registrar, name='registrar'),
    path('asientos/', views.asientos, name='asientos'),
    path('libro-diario/', views.libro_diario, name='libro_diario'),
    path('libro-mayor/', views.libro_mayor, name='libro_mayor'),
    path(
        'balance-general/',
        views.balance_general,
        name='balance_general',
    ),
]
