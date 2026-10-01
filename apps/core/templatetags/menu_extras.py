"""
Filtros para resaltar el ítem/sección activa de un menú contra `request.path`.

Viven en un filtro de template, no en un método de `MenuItem`/
`MenuSection`: esos son value objects sin nada de Django a propósito
(ver `registrations.py`) — `request.path` es lo único que hace falta acá,
así que el cálculo de "activo" es lo único que sí es específico de
Django/este proyecto.
"""

from __future__ import annotations

from django import template

from ..registrations import MenuItem, MenuSection

register = template.Library()


def menu_item_is_active(
    item: MenuItem,
    section: MenuSection,
    path: str,
) -> bool:
    """
    True si `path` pertenece a `item` dentro de `section`.

    Usa el prefijo más largo que calce: `/billing/emitir/masivo/` debe
    marcar "Emitir masivo", no "Emitir" (`/billing/emitir` también calza).
    """
    if not path.startswith(item.active_prefix):
        return False
    matching = [
        menu_item
        for menu_item in section.items
        if path.startswith(menu_item.active_prefix)
    ]
    if not matching:
        return False
    best = max(matching, key=lambda menu_item: len(menu_item.active_prefix))
    return item.url_name == best.url_name


@register.filter
def active_menu_url_name(section: MenuSection, path: str) -> str:
    """`url_name` del ítem activo de `section` para `path`, o `''`."""
    for item in section.items:
        if menu_item_is_active(item, section, path):
            return item.url_name
    return ''


@register.filter
def item_is_active(item: MenuItem, path: str) -> bool:
    """True si `path` cae dentro de `item.active_prefix`."""
    return path.startswith(item.active_prefix)


@register.filter
def section_is_active(section: MenuSection, path: str) -> bool:
    """True si algún ítem de `section` está activo para `path`."""
    return bool(active_menu_url_name(section, path))
