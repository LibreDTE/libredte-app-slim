"""Exige un contribuyente activo en toda vista autenticada de la app."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponseBase
from django.shortcuts import redirect

from .models import Contribuyente
from .tenancy import get_current_contribuyente

EXEMPT_VIEW_NAMES = {
    'libredte:wizard_contribuyente',
    'libredte:contribuyentes',
    'libredte:contribuyente_seleccionar',
    'login',
    'logout',
    'password_change',
    'password_change_done',
    'password_reset',
    'password_reset_done',
    'password_reset_confirm',
    'password_reset_complete',
    'billing:emitir_masivo_pdf',
}


class RequireContribuyenteMiddleware:
    """Redirige a dar de alta o elegir un contribuyente, según falte cuál."""

    def __init__(
        self, get_response: Callable[[HttpRequest], HttpResponseBase]
    ) -> None:
        """Guarda el `get_response` que exige el contrato de middleware."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        _view_func: Callable[..., HttpResponseBase],
        _view_args: tuple[Any, ...],
        _view_kwargs: dict[str, Any],
    ) -> HttpResponseBase | None:
        """Corta hacia el wizard/listado antes de la vista, si corresponde."""
        if not request.user.is_authenticated:
            return None
        if request.path.startswith('/admin/'):
            return None
        # Django ya lo dejó seteado antes de llamar a `process_view()`.
        assert request.resolver_match is not None
        if request.resolver_match.view_name in EXEMPT_VIEW_NAMES:
            return None
        if get_current_contribuyente(request) is not None:
            return None
        # `get_current_contribuyente()` ya autoselecciona si el usuario
        # tiene exactamente un contribuyente — llegar acá con `None`
        # significa que tiene dos o más (falta elegir cuál) o ninguno.
        if Contribuyente.objects.filter(usuario=request.user).exists():
            messages.info(
                request,
                'Tienes más de un contribuyente — selecciona con cuál '
                'quieres trabajar.',
            )
            return redirect('libredte:contribuyentes')
        messages.info(
            request,
            'Registra tu contribuyente para poder usar la plataforma.',
        )
        return redirect('libredte:wizard_contribuyente')
