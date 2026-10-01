"""Tests para `plugin/catalog.py`."""

from __future__ import annotations

from collections.abc import Generator
from typing import ClassVar

import pytest

from apps.core.plugin import catalog
from apps.core.plugin.base import BasePlugin, BasePluginCapability


class _DummyCapability(BasePluginCapability):
    """Capability de mentira, solo para probar el mecanismo — sin dominio."""

    id = 'test.capability'
    label = 'Test'
    description = ''


class _UnknownCapability(BasePluginCapability):
    """Capability de mentira que ningún plugin de este archivo provee."""

    id = 'nada.aqui'
    label = 'Nada'
    description = ''


class _DummyPlugin(BasePlugin):
    """Plugin de mentira, solo para probar el mecanismo — sin dominio."""

    id = 'dummy'
    label = 'Dummy'
    capabilities: ClassVar[
        dict[type[BasePluginCapability], type[BasePluginCapability]]
    ] = {
        _DummyCapability: _DummyCapability,
    }


class _OtherDummyPlugin(BasePlugin):
    """Segundo plugin de la misma capability, para probar el catálogo."""

    id = 'other_dummy'
    label = 'Other Dummy'
    capabilities: ClassVar[
        dict[type[BasePluginCapability], type[BasePluginCapability]]
    ] = {
        _DummyCapability: _DummyCapability,
    }


@pytest.fixture(autouse=True)
def _clean_catalog() -> Generator[None]:
    """
    Aísla `catalog._plugins`/`_capabilities` entre tests — es estado a
    nivel de módulo.

    Restaura lo que había antes (plugins/capabilities reales,
    registrados por `autodiscover_modules('platform'/'plugins')` al
    arrancar Django) al terminar — limpiar sin restaurar dejaría el
    catálogo vacío para el resto de la sesión de tests, rompiendo
    cualquier test posterior que espere encontrar algo real ya
    registrado.
    """
    original_plugins = dict(catalog._plugins)
    original_capabilities = dict(catalog._capabilities)
    catalog._plugins.clear()
    catalog._capabilities.clear()
    yield
    catalog._plugins.clear()
    catalog._plugins.update(original_plugins)
    catalog._capabilities.clear()
    catalog._capabilities.update(original_capabilities)


def test_register_adds_the_plugin_to_all_plugins() -> None:
    catalog.register(_DummyPlugin)

    assert catalog.all_plugins() == [_DummyPlugin]


def test_register_rejects_a_duplicate_id() -> None:
    catalog.register(_DummyPlugin)

    with pytest.raises(ValueError, match='dummy'):
        catalog.register(_DummyPlugin)


def test_plugins_for_capability_returns_registered_classes_for_it() -> None:
    catalog.register(_DummyPlugin)
    catalog.register(_OtherDummyPlugin)

    classes = catalog.plugins_for_capability(_DummyCapability)

    assert set(classes) == {_DummyPlugin, _OtherDummyPlugin}


def test_plugins_for_capability_returns_empty_for_an_unknown_capability() -> (
    None
):
    catalog.register(_DummyPlugin)

    assert catalog.plugins_for_capability(_UnknownCapability) == []


def test_register_capability_adds_it_to_all_capabilities() -> None:
    catalog.register_capability(_DummyCapability)

    assert catalog.all_capabilities() == [_DummyCapability]
    assert catalog.get_capability('test.capability') == _DummyCapability


def test_register_capability_rejects_a_duplicate_id() -> None:
    catalog.register_capability(_DummyCapability)

    with pytest.raises(ValueError, match='test\\.capability'):
        catalog.register_capability(_DummyCapability)


def test_get_capability_returns_none_for_an_unregistered_id() -> None:
    assert catalog.get_capability('nada.aqui') is None


def test_all_capabilities_are_ordered_by_priority() -> None:
    class _LowCapability(BasePluginCapability):
        id = 'low'
        label = 'Low'
        description = ''
        priority = 10

    class _HighCapability(BasePluginCapability):
        id = 'high'
        label = 'High'
        description = ''
        priority = 1

    catalog.register_capability(_LowCapability)
    catalog.register_capability(_HighCapability)

    assert catalog.all_capabilities() == [_HighCapability, _LowCapability]
