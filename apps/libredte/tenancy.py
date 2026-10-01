"""
Resolución del contribuyente activo para el request/sesión actual.

Punto único de acceso: `get_current_contribuyente()`/
`set_current_contribuyente()` son los únicos lugares que conocen la
llave de sesión — nada más debe leer/escribir `request.session`
directo para esto.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Contribuyente

if TYPE_CHECKING:
    from django.http import HttpRequest

_SESSION_KEY = 'contribuyente_id'


def get_current_contribuyente(request: HttpRequest) -> Contribuyente | None:
    """
    Contribuyente activo para este usuario/sesión, o `None` si no hay.

    Un usuario puede ser dueño de más de un `Contribuyente`
    (`Contribuyente.usuario` es `ForeignKey`, no `OneToOne`) — cuál
    está activo ahora se decide en `set_current_contribuyente()`, no
    acá. Se llama también desde un context processor global (corre en
    cada request, autenticado o no), por eso el chequeo explícito de
    `is_authenticated` antes de tocar sesión/DB.

    Sin nada seleccionado (o lo seleccionado ya no es del usuario), si
    tiene exactamente un `Contribuyente` propio se autoselecciona —no
    tiene sentido pedirle elegir entre uno solo— y de paso queda
    guardado en sesión, para no repetir esta búsqueda en cada request.
    """
    if not request.user.is_authenticated:
        return None
    contribuyente_id = request.session.get(_SESSION_KEY)
    if contribuyente_id is not None:
        contribuyente = Contribuyente.objects.filter(
            pk=contribuyente_id,
            usuario=request.user,
        ).first()
        if contribuyente is not None:
            return contribuyente
    propios = list(Contribuyente.objects.filter(usuario=request.user)[:2])
    if len(propios) == 1:
        set_current_contribuyente(request, propios[0])
        return propios[0]
    return None


def set_current_contribuyente(
    request: HttpRequest,
    contribuyente: Contribuyente,
) -> None:
    """
    Selecciona `contribuyente` como activo para esta sesión.

    Quien llama ya validó que `contribuyente` pertenece al usuario
    actual (ver `get_current_contribuyente()`, que vuelve a validarlo
    en cada lectura) — acá no se repite ese chequeo.
    """
    request.session[_SESSION_KEY] = contribuyente.pk


def require_current_contribuyente(request: HttpRequest) -> Contribuyente:
    """
    Como `get_current_contribuyente()`, pero nunca `None`.

    Para usar solo en vistas ya protegidas por
    `RequireContribuyenteMiddleware`, que garantiza esto en la práctica.
    """
    contribuyente = get_current_contribuyente(request)
    assert contribuyente is not None
    return contribuyente
