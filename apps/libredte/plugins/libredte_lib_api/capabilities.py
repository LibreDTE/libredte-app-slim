"""Implementación de `libredte.backend` que provee este plugin."""

from __future__ import annotations

from typing import Any

from apps.libredte.plugins.contracts import (
    LibredteBackend,
    LibredteBackendPluginCapabilityDefinition,
)

from .config_resolver import (
    resolve_api_token,
    resolve_auth_scheme,
    resolve_base_url,
)


class LibredteBackendPluginCapability(
    LibredteBackendPluginCapabilityDefinition
):
    """Implementación de `libredte.backend` de `libredte_lib_api`."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Guarda `config` (`base_url`/`api_token`/`auth_scheme`)."""
        self.config = config

    def get_backend(self) -> LibredteBackend:
        """`base_url`/`api_token`/`auth_scheme` de `config`, o los globales."""
        return LibredteBackend(
            base_url=resolve_base_url(self.config),
            api_token=resolve_api_token(self.config),
            auth_scheme=resolve_auth_scheme(self.config),
        )
