"""Administración de Django compartida entre apps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.http import HttpRequest

if TYPE_CHECKING:
    _ReadOnlyModelAdminBase = admin.ModelAdmin[Any]
    _ReadOnlyTabularInlineBase = admin.TabularInline[Any, Any]
else:
    _ReadOnlyModelAdminBase = admin.ModelAdmin
    _ReadOnlyTabularInlineBase = admin.TabularInline


class ReadOnlyModelAdmin(_ReadOnlyModelAdminBase):
    """
    `ModelAdmin` de solo lectura: nada se crea, edita ni elimina acá.

    Migración incremental del admin: hasta que se decida caso a caso
    qué modelo amerita edición real, todo queda visible (listas con
    filtros/búsqueda) pero intocable — la fuente de verdad sigue
    siendo el flujo propio de cada modelo (`seeders.py`, o su propia
    vista con sus propias validaciones), nunca el admin. Django ya
    renderiza el detalle en modo solo-lectura cuando falta permiso de
    cambio pero sí hay de vista — no hace falta declarar
    `readonly_fields` a mano en cada subclase.
    """

    def has_add_permission(self, _request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, _request: HttpRequest, _obj: Any | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, _request: HttpRequest, _obj: Any | None = None
    ) -> bool:
        return False


class ReadOnlyTabularInline(_ReadOnlyTabularInlineBase):
    """Igual que `ReadOnlyModelAdmin`, pero para un inline."""

    extra = 0

    def has_add_permission(
        self, _request: HttpRequest, _obj: Any | None = None
    ) -> bool:
        return False

    def has_change_permission(
        self, _request: HttpRequest, _obj: Any | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, _request: HttpRequest, _obj: Any | None = None
    ) -> bool:
        return False
