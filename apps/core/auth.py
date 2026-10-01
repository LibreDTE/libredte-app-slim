"""Resolución del usuario autenticado real para el request actual."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.http import HttpRequest


def require_authenticated_user(request: HttpRequest) -> User:
    """
    `request.user`, garantizado autenticado (nunca `AnonymousUser`).

    No es redundante con `@login_required`/`LoginRequiredMixin`: esos
    protegen en tiempo de ejecución, pero no le dicen nada a mypy —
    `HttpRequest.user` sigue tipado `_User | AnonymousUser`
    (`django-stubs`) dentro de una vista protegida, así que acceder a
    un atributo propio de `User` (ej. `.certificados`) sería un error
    de mypy sin este angostamiento. Para usar solo en vistas ya
    protegidas por `@login_required`/`LoginRequiredMixin` — son las
    que garantizan esto en la práctica; el `assert` es la contraparte
    en tiempo de ejecución de esa garantía.
    """
    assert request.user.is_authenticated
    return request.user
