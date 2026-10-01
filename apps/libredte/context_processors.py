"""Context processors de `libredte`."""

from __future__ import annotations

from django.http import HttpRequest

from .models import Contribuyente
from .tenancy import get_current_contribuyente


def current_contribuyente(
    request: HttpRequest,
) -> dict[str, Contribuyente | None]:
    """Expone el contribuyente activo a todos los templates."""
    return {'current_contribuyente': get_current_contribuyente(request)}
