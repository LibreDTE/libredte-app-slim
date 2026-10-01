"""
Vistas de `human_resources` — placeholders.

URL + vista + template ya conectados al menú para que la app sea
navegable de punta a punta, pero sin modelo ni lógica propia todavía.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


@login_required
def calcular(request: HttpRequest) -> HttpResponse:
    """Calcular liquidación de sueldo de un período — placeholder."""
    return render(request, 'human_resources/calcular.html')


@login_required
def liquidaciones(request: HttpRequest) -> HttpResponse:
    """Liquidaciones de sueldo por período — placeholder."""
    return render(request, 'human_resources/liquidaciones.html')


@login_required
def empleados(request: HttpRequest) -> HttpResponse:
    """Ficha de empleados de la empresa — placeholder."""
    return render(request, 'human_resources/empleados.html')
