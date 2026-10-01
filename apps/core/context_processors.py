"""Context processors de `core` — exponen los registries a cada template."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from .registry import get_all
from .version import get_version_detail, get_version_label


def menu_sections(request: HttpRequest) -> dict[str, Any]:
    """Secciones del menú principal (sidebar), registro `'menu'`."""
    return {'menu_sections': get_all('menu')}


def settings_sections(request: HttpRequest) -> dict[str, Any]:
    """Secciones del menú de Configuración, registro `'settings'`."""
    return {'settings_sections': get_all('settings')}


def app_version(request: HttpRequest) -> dict[str, Any]:
    """Versión y commits de la app: resumen para el pie y detalle completo."""
    return {
        'app_version': get_version_label(),
        'app_version_detail': get_version_detail(),
    }
