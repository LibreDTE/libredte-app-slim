"""
Vistas de `accounting` fuera de Configuración — placeholders.

URL + vista + template ya conectados al menú para que la app sea
navegable de punta a punta, pero sin modelo ni lógica propia todavía.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


@login_required
def registrar(request: HttpRequest) -> HttpResponse:
    """Registrar un asiento contable — placeholder."""
    return render(request, 'accounting/registrar.html')


@login_required
def asientos(request: HttpRequest) -> HttpResponse:
    """Lista de asientos contables — placeholder."""
    return render(request, 'accounting/asientos.html')


@login_required
def libro_diario(request: HttpRequest) -> HttpResponse:
    """Libro diario por rango de fechas — placeholder."""
    return render(request, 'accounting/libro_diario.html')


@login_required
def libro_mayor(request: HttpRequest) -> HttpResponse:
    """Libro mayor por rango/período — placeholder."""
    return render(request, 'accounting/libro_mayor.html')


@login_required
def balance_general(request: HttpRequest) -> HttpResponse:
    """Balance general por período contable — placeholder."""
    return render(request, 'accounting/balance_general.html')
