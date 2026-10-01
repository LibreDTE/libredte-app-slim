"""
"Modo sudo": exige confirmar la contraseña antes de una acción sensible.

Confirmar la contraseña marca la sesión como "reciente" por
`SUDO_TTL_SECONDS`; mientras dure, no se vuelve a pedir. Django no trae
nada equivalente — esto es la versión mínima "pluggeable"
(`@requires_sudo` para vistas de función, `RequiresSudoMixin` para
CBVs), sin repetir la lógica de chequeo en cada lugar que la necesite.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.http import HttpRequest, HttpResponseBase
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

if TYPE_CHECKING:
    from django.views import View

    _RequiresSudoMixinBase = View
else:
    # Un mixin puro no tiene una base real con `dispatch()` — se mezcla
    # siempre con una `View` real (ver docstring de la clase), pero
    # declararlo así (`View` solo para tipos) es lo que le permite a
    # `super().dispatch(...)` resolver correctamente sin heredar de
    # `View` de verdad (evitaría los otros mixins del MRO real).
    _RequiresSudoMixinBase = object

SUDO_SESSION_KEY = 'sudo_confirmed_at'
SUDO_TTL_SECONDS = getattr(settings, 'SUDO_TTL_SECONDS', 15 * 60)


def sudo_is_active(request: HttpRequest) -> bool:
    """True si el usuario confirmó su contraseña dentro del TTL."""
    confirmed_at = request.session.get(SUDO_SESSION_KEY)
    if not confirmed_at:
        return False
    elapsed = (
        timezone.now() - datetime.fromisoformat(confirmed_at)
    ).total_seconds()
    return elapsed < SUDO_TTL_SECONDS


def activate_sudo(request: HttpRequest) -> None:
    """Marca la sesión como recién confirmada."""
    request.session[SUDO_SESSION_KEY] = timezone.now().isoformat()


def _redirect_to_sudo(request: HttpRequest) -> HttpResponseBase:
    query = urlencode({'next': request.get_full_path()})
    return redirect(f'{reverse("core:sudo")}?{query}')


def requires_sudo(
    view_func: Callable[..., HttpResponseBase],
) -> Callable[..., HttpResponseBase]:
    """Decorator para vistas de función: exige sudo activo."""

    @wraps(view_func)
    def wrapper(
        request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        if not sudo_is_active(request):
            return _redirect_to_sudo(request)
        return view_func(request, *args, **kwargs)

    return wrapper


class RequiresSudoMixin(_RequiresSudoMixinBase):
    """
    Mismo chequeo que `requires_sudo`, para vistas basadas en clase.

    Debe ir **después** de `LoginRequiredMixin` en la lista de bases
    (ej. `class X(LoginRequiredMixin, RequiresSudoMixin, ...)`) — así,
    por el MRO, el `dispatch()` de `LoginRequiredMixin` corre primero:
    sin sesión iniciada, redirige a login, no a confirmar sudo.
    """

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        """Corta hacia la confirmación de sudo antes de la vista real."""
        if not sudo_is_active(request):
            return _redirect_to_sudo(request)
        return super().dispatch(request, *args, **kwargs)
