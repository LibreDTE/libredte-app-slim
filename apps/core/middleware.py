"""Exige crear el primer usuario antes de servir cualquier otra página."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponseBase
from django.shortcuts import redirect

EXEMPT_VIEW_NAMES = {'core:setup', 'health'}


class RequireInitialUserMiddleware:
    """Redirige al alta del primer usuario si la base no tiene ninguno."""

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
        """Corta hacia el setup antes de ejecutar la vista, si corresponde."""
        if request.path.startswith('/admin/'):
            return None
        # Django ya lo dejó seteado antes de llamar a `process_view()`.
        assert request.resolver_match is not None
        if request.resolver_match.view_name in EXEMPT_VIEW_NAMES:
            return None
        if User.objects.exists():
            return None
        return redirect('core:setup')
