"""
Catálogo de `BasePlugin`/`BasePluginCapability` disponibles en Slim.

Propio y no el `registry.py` genérico (`register('plugin', ...)`) a
propósito: acá sí importa validar que no se registre un `id` dos veces
(dos plugins/capabilities compitiendo por el mismo identificador es un
error de configuración, no algo que deba pasar en silencio como el
resto de lo que registra `registry.py`), y las consultas
(`plugins_for_capability`) son propias del dominio de plugins, no algo
genérico que `core` deba saber hacer sobre cualquier `kind`.

Sin nada de tenant/base de datos acá — eso es `resolver.py`, que cruza
esto con `PluginConfig`.
"""

from __future__ import annotations

from .base import BasePlugin, BasePluginCapability

_plugins: dict[str, type[BasePlugin]] = {}
_capabilities: dict[str, type[BasePluginCapability]] = {}


def register(plugin_class: type[BasePlugin]) -> None:
    """Agrega `plugin_class` al catálogo."""
    if plugin_class.id in _plugins:
        msg = f'Ya hay un plugin registrado con id "{plugin_class.id}".'
        raise ValueError(msg)
    _plugins[plugin_class.id] = plugin_class


def get(plugin_id: str) -> type[BasePlugin] | None:
    """El `BasePlugin` con este id, o `None` si no está registrado."""
    return _plugins.get(plugin_id)


def all_plugins() -> list[type[BasePlugin]]:
    """Todos los `BasePlugin` del catálogo, listables o no, por `priority`."""
    return sorted(_plugins.values(), key=lambda cls: cls.priority)


def plugins_for_capability(
    definition_class: type[BasePluginCapability],
) -> list[type[BasePlugin]]:
    """`BasePlugin` que proveen `definition_class`, por `priority`."""
    return [
        cls for cls in all_plugins() if definition_class in cls.capabilities
    ]


def register_capability(capability_class: type[BasePluginCapability]) -> None:
    """Agrega `capability_class` al catálogo."""
    if capability_class.id in _capabilities:
        msg = (
            f'Ya hay una capability registrada con id "{capability_class.id}".'
        )
        raise ValueError(msg)
    _capabilities[capability_class.id] = capability_class


def get_capability(capability_id: str) -> type[BasePluginCapability] | None:
    """La `BasePluginCapability` de `capability_id`, o `None` si no existe."""
    return _capabilities.get(capability_id)


def all_capabilities() -> list[type[BasePluginCapability]]:
    """Todas las `BasePluginCapability` registradas, por `priority`."""
    return sorted(_capabilities.values(), key=lambda cap: cap.priority)


def capabilities_for_plugin(
    plugin_class: type[BasePlugin],
) -> list[type[BasePluginCapability]]:
    """`BasePluginCapability` que `plugin_class` provee, por `priority`."""
    return sorted(plugin_class.capabilities, key=lambda cap: cap.priority)
