"""
Resuelve qué `BasePluginCapability` tiene activa un tenant.

Cruza el catálogo estático (`catalog.py` — qué `BasePlugin` existen y
qué `BasePluginCapability` proveen) con la activación por tenant
(`PluginConfig` — quién la tiene activa, con qué config y en qué
orden). Ninguna de las dos mitades sabe hacer esto sola: el catálogo
no sabe de tenants, y `PluginConfig` no sabe qué plugins hay
disponibles.

Devuelve `BasePluginCapability` a secas (no genérico sobre la clase
concreta pedida): `definition_class` suele ser abstracta, y mypy no
permite pasar una clase abstracta donde espera poder construirla
(`type-abstract`) — quien llama angosta con su propio `isinstance()`,
igual que hace `BasePlugin.get_capability()`.
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model

from ..models import PluginConfig
from .base import BasePluginCapability
from .catalog import plugins_for_capability


def resolve_all(
    definition_class: type[BasePluginCapability], tenant: Model
) -> list[BasePluginCapability]:
    """
    Las implementaciones de `definition_class` activas de `tenant`, en cascada.

    Orden: `PluginConfig.priority` ascendente (menor primero — mismo
    criterio que `registry.get_all()`), pensado para que quien llama
    las recorra y se quede con la primera que le resuelva el problema
    (ej. la primera que logre renderizar el PDF) — sin que el mecanismo
    decida por quién llama qué significa "falló".
    """
    plugin_classes = {
        cls.id: cls for cls in plugins_for_capability(definition_class)
    }
    if not plugin_classes:
        return []
    content_type = ContentType.objects.get_for_model(tenant)
    plugin_configs = PluginConfig.objects.filter(
        content_type=content_type,
        object_id=tenant.pk,
        plugin_id__in=plugin_classes,
        active=True,
    ).order_by('priority')
    return [
        plugin_classes[plugin_config.plugin_id](
            plugin_config.config
        ).get_capability(definition_class)
        for plugin_config in plugin_configs
    ]


def resolve(
    definition_class: type[BasePluginCapability], tenant: Model
) -> BasePluginCapability | None:
    """
    La primera implementación activa de `definition_class` en `tenant`.

    Para capacidades que solo admiten un reemplazo a la vez (ej.
    `libredte.backend`, donde no tiene sentido tener dos backends
    activos a la vez). Si la capacidad admite cascada, usar
    `resolve_all()` en vez de esta.
    """
    capabilities = resolve_all(definition_class, tenant)
    return capabilities[0] if capabilities else None
