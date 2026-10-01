"""
Vistas de `accounting` bajo Configuración — placeholders.

Ver `apps/accounting/views/app.py` para el resto — mismo criterio.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


@login_required
def cuentas(request: HttpRequest) -> HttpResponse:
    """Plan de cuentas contables ("Configuración") — placeholder."""
    return render(request, 'accounting/cuentas.html')
