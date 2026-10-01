"""
Resuelve el `base_url`/`api_token` efectivos del plugin `libredte_lib_api`.

Funciones sueltas, no métodos/properties de `LibredteLibApiPlugin`: las
necesita también `LibredteLibApiConfigForm.clean()` (ver `forms.py`),
que valida sobre `cleaned_data` (un `dict`) antes de que exista ningún
`BasePlugin` guardado — instanciar un `BasePlugin` solo para leer esto sería al
revés, y además `plugin.py` ya importa `LibredteLibApiConfigForm` desde
`forms.py`, así que `forms.py` no puede importar de vuelta desde
`plugin.py` sin circularidad.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings


def resolve_base_url(config: dict[str, Any]) -> str:
    """`base_url` de `config`, o el global de la plataforma si falta."""
    return config.get('base_url') or settings.PLUGIN_LIBREDTE_BACKEND_API_URL


def resolve_api_token(config: dict[str, Any]) -> str | None:
    """`api_token` de `config`, o el global de la plataforma si falta."""
    return (
        config.get('api_token')
        or settings.PLUGIN_LIBREDTE_BACKEND_API_TOKEN
        or None
    )


def resolve_auth_scheme(config: dict[str, Any]) -> str:
    """`auth_scheme` de `config`, o el global de la plataforma si falta."""
    return (
        config.get('auth_scheme')
        or settings.PLUGIN_LIBREDTE_BACKEND_API_AUTH_SCHEME
    )
