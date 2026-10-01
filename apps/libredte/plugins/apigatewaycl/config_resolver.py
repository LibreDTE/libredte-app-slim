"""
Resuelve el `base_url`/`api_token` efectivos del plugin `apigatewaycl`.

Funciones sueltas, no métodos/properties de `ApiGatewayClPlugin`: las
necesita también `ApiGatewayClConfigForm.clean()` (ver `forms.py`),
que valida sobre `cleaned_data` (un `dict`) antes de que exista ningún
`BasePlugin` guardado — instanciar un `BasePlugin` solo para leer esto
sería al revés, y además `plugin.py` ya importa
`ApiGatewayClConfigForm` desde `forms.py`, así que `forms.py` no puede
importar de vuelta desde `plugin.py` sin circularidad.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings


def resolve_base_url(config: dict[str, Any]) -> str:
    """`base_url` de `config`, o el global de la plataforma si falta."""
    return config.get('base_url') or settings.PLUGIN_APIGATEWAYCL_API_URL


def resolve_api_token(config: dict[str, Any]) -> str | None:
    """`api_token` de `config`, o el global de la plataforma si falta."""
    return (
        config.get('api_token')
        or settings.PLUGIN_APIGATEWAYCL_API_TOKEN
        or None
    )
