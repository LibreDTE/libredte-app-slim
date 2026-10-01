"""Tests para `plugin/resolver.py`."""

from __future__ import annotations

from collections.abc import Generator
from typing import ClassVar

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from apps.core.models import PluginConfig
from apps.core.plugin import catalog
from apps.core.plugin.base import BasePlugin, BasePluginCapability
from apps.core.plugin.resolver import resolve, resolve_all

pytestmark = pytest.mark.django_db


class _DummyCapability(BasePluginCapability):
    """Contrato de mentira, solo para probar el mecanismo — sin dominio."""

    id = 'test.capability'
    label = 'Test'
    description = ''

    def greet(self) -> str:
        raise NotImplementedError


class _OtraCapability(BasePluginCapability):
    """Otra capability de mentira, que ningún plugin de este archivo provee."""

    id = 'otra.capability'
    label = 'Otra'
    description = ''


class _DummyCapabilityImpl(_DummyCapability):
    """Implementación de `_DummyCapability` de `_DummyPlugin`."""

    def __init__(self, config: dict[str, str]) -> None:
        self.config = config

    def greet(self) -> str:
        return f'hola, {self.config["name"]}'


class _OtherDummyCapabilityImpl(_DummyCapability):
    """Implementación de `_DummyCapability` de `_OtherDummyPlugin`."""

    def __init__(self, config: dict[str, str]) -> None:
        self.config = config

    def greet(self) -> str:
        return f'chau, {self.config["name"]}'


class _DummyPlugin(BasePlugin):
    """Plugin de mentira, solo para probar el mecanismo — sin dominio."""

    id = 'dummy'
    label = 'Dummy'
    capabilities: ClassVar[
        dict[type[BasePluginCapability], type[BasePluginCapability]]
    ] = {
        _DummyCapability: _DummyCapabilityImpl,
    }


class _OtherDummyPlugin(BasePlugin):
    """Segundo plugin de la misma capability, para probar cascada/orden."""

    id = 'other_dummy'
    label = 'Other Dummy'
    capabilities: ClassVar[
        dict[type[BasePluginCapability], type[BasePluginCapability]]
    ] = {
        _DummyCapability: _OtherDummyCapabilityImpl,
    }


@pytest.fixture(autouse=True)
def registered_plugins() -> Generator[None]:
    """Aísla `catalog._plugins`, restaurando lo real al terminar (ver
    `test_plugin_catalog.py::_clean_catalog`)."""
    original = dict(catalog._plugins)
    catalog._plugins.clear()
    catalog.register(_DummyPlugin)
    catalog.register(_OtherDummyPlugin)
    yield
    catalog._plugins.clear()
    catalog._plugins.update(original)


def _activate(tenant: User, plugin_id: str, priority: int = 0) -> PluginConfig:
    return PluginConfig.objects.create(
        content_type=ContentType.objects.get_for_model(tenant),
        object_id=tenant.pk,
        plugin_id=plugin_id,
        active=True,
        priority=priority,
        config={'name': 'Esteban'},
    )


def test_resolve_returns_none_without_an_active_plugin_config() -> None:
    user = User.objects.create_user('demo')

    resolved = resolve(_DummyCapability, tenant=user)
    assert resolved is None


def test_resolve_returns_the_active_capability_instance() -> None:
    user = User.objects.create_user('demo')
    _activate(user, 'dummy')

    capability = resolve(_DummyCapability, tenant=user)

    assert capability is not None
    assert isinstance(capability, _DummyCapabilityImpl)
    assert capability.greet() == 'hola, Esteban'


def test_resolve_returns_none_without_a_matching_capability() -> None:
    """Un `PluginConfig` activo no alcanza si no provee la capability."""
    user = User.objects.create_user('demo')
    _activate(user, 'dummy')

    resolved = resolve(_OtraCapability, tenant=user)
    assert resolved is None


def test_resolve_returns_none_when_plugin_config_is_inactive() -> None:
    user = User.objects.create_user('demo')
    PluginConfig.objects.create(
        content_type=ContentType.objects.get_for_model(user),
        object_id=user.pk,
        plugin_id='dummy',
        active=False,
        config={'name': 'Esteban'},
    )

    resolved = resolve(_DummyCapability, tenant=user)
    assert resolved is None


def test_resolve_all_returns_every_active_capability_ordered_by_priority() -> (
    None
):
    user = User.objects.create_user('demo')
    _activate(user, 'other_dummy', priority=10)
    _activate(user, 'dummy', priority=1)

    capabilities = resolve_all(_DummyCapability, tenant=user)
    greetings = []
    for capability in capabilities:
        assert isinstance(capability, _DummyCapability)
        greetings.append(capability.greet())

    assert greetings == ['hola, Esteban', 'chau, Esteban']


def test_resolve_all_returns_empty_list_without_any_active_plugin() -> None:
    user = User.objects.create_user('demo')
    assert resolve_all(_DummyCapability, tenant=user) == []


def test_resolve_returns_the_first_in_priority_order() -> None:
    user = User.objects.create_user('demo')
    _activate(user, 'other_dummy', priority=10)
    _activate(user, 'dummy', priority=1)

    capability = resolve(_DummyCapability, tenant=user)

    assert capability is not None
    assert isinstance(capability, _DummyCapability)
    assert capability.greet() == 'hola, Esteban'
