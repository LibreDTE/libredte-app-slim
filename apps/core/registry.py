"""
Registro genérico de lo que cada app expone a `core` (menú, Configuración).

Sin nada de Django ni de este proyecto acá tampoco — es solo un
`dict[str, list]` con dos funciones. `kind` distingue qué se está
registrando (`'menu'` = menú principal, `'settings'` = menú de
Configuración) — ver `contracts.py` para el tipo que se registra en
cada uno.
"""

from __future__ import annotations

from typing import Any

_registries: dict[str, list[Any]] = {}


def register(kind: str, item: Any) -> None:
    """Agrega `item` al registro `kind`."""
    _registries.setdefault(kind, []).append(item)


def get_all(kind: str) -> list[Any]:
    """Todo lo registrado en `kind`, ordenado por `item.priority`."""
    return sorted(_registries.get(kind, []), key=lambda item: item.priority)
