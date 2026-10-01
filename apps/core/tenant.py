"""
Resuelve "quién es el tenant actual", sin dominio en `core`.

Ni `Contribuyente` ni ningún otro modelo de dominio se importa acá.
Registro de un solo valor, no una lista (a diferencia de
`registry.py`): solo puede existir UN resolver de tenant a la vez, no
tiene sentido agregarlos ni ordenarlos por `priority` — quien decide
qué es "el tenant" de esta instancia (hoy,
`apps.libredte.tenancy.get_current_contribuyente`) lo registra una
sola vez, típicamente desde su propio `platform.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models import Model
    from django.http import HttpRequest

# Un `dict` en vez de una variable de módulo reasignable: mutar una
# entrada evita el `global` que haría falta para reasignar esa
# variable desde `register_tenant_resolver()`.
_state: dict[str, Callable[[HttpRequest], Model | None]] = {}


def register_tenant_resolver(
    resolver: Callable[[HttpRequest], Model | None],
) -> None:
    """Registra `resolver` como la función que resuelve "el tenant actual"."""
    _state['resolver'] = resolver


def get_current_tenant(request: HttpRequest) -> Model | None:
    """El tenant actual para `request`, o `None` sin resolver/sin tenant."""
    resolver = _state.get('resolver')
    if resolver is None:
        return None
    return resolver(request)


def require_current_tenant(request: HttpRequest) -> Model:
    """Como `get_current_tenant()`, pero nunca `None`."""
    tenant = get_current_tenant(request)
    assert tenant is not None
    return tenant
