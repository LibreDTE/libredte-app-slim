"""Tests para el plugin `libredte_lib_api` (capability `libredte.backend`)."""

from __future__ import annotations

from unittest import mock

from django.test import override_settings

from apps.core.plugin.catalog import (
    all_plugins,
    get_capability,
    plugins_for_capability,
)
from apps.libredte.plugins.contracts import (
    LibredteBackend,
    LibredteBackendPluginCapabilityDefinition,
)
from apps.libredte.plugins.libredte_lib_api.forms import (
    LibredteLibApiConfigForm,
)
from apps.libredte.plugins.libredte_lib_api.plugin import LibredteLibApiPlugin


def test_it_is_registered_in_the_catalog() -> None:
    """`apps/core/apps.py::ready()` lo registra vía `autodiscover_modules`."""
    assert LibredteLibApiPlugin in all_plugins()


def test_it_implements_the_libredte_backend_capability() -> None:
    assert LibredteLibApiPlugin in plugins_for_capability(
        LibredteBackendPluginCapabilityDefinition
    )


def test_the_libredte_backend_capability_is_registered() -> None:
    """`apps/libredte/platform.py` la registra vía `autodiscover_modules`."""
    capability = get_capability('libredte.backend')

    assert capability is not None
    assert capability.label


def test_get_backend_returns_an_instance_of_libredte_backend() -> None:
    plugin = LibredteLibApiPlugin(
        {'base_url': 'https://libredte.example.cl', 'api_token': 'un-token'},
    )

    capability = plugin.get_capability(
        LibredteBackendPluginCapabilityDefinition
    )
    assert isinstance(capability, LibredteBackendPluginCapabilityDefinition)
    backend = capability.get_backend()

    assert isinstance(backend, LibredteBackend)


@mock.patch(
    'apps.libredte.plugins.libredte_lib_api.capabilities.LibredteBackend'
)
def test_get_backend_uses_the_tenants_own_config_when_present(
    libredte_backend_mock: mock.Mock,
) -> None:
    plugin = LibredteLibApiPlugin(
        {
            'base_url': 'https://tenant.example.cl',
            'api_token': 'tenant-token',
            'auth_scheme': 'Token',
        },
    )

    capability = plugin.get_capability(
        LibredteBackendPluginCapabilityDefinition
    )
    assert isinstance(capability, LibredteBackendPluginCapabilityDefinition)
    capability.get_backend()

    libredte_backend_mock.assert_called_once_with(
        base_url='https://tenant.example.cl',
        api_token='tenant-token',
        auth_scheme='Token',
    )


@override_settings(
    PLUGIN_LIBREDTE_BACKEND_API_URL='https://global.example.cl',
    PLUGIN_LIBREDTE_BACKEND_API_TOKEN='global-token',
    PLUGIN_LIBREDTE_BACKEND_API_AUTH_SCHEME='Bearer',
)
@mock.patch(
    'apps.libredte.plugins.libredte_lib_api.capabilities.LibredteBackend'
)
def test_get_backend_falls_back_to_the_global_settings_when_config_is_empty(
    libredte_backend_mock: mock.Mock,
) -> None:
    """Activar el plugin sin configurar nada no cambia el comportamiento."""
    plugin = LibredteLibApiPlugin({})

    capability = plugin.get_capability(
        LibredteBackendPluginCapabilityDefinition
    )
    assert isinstance(capability, LibredteBackendPluginCapabilityDefinition)
    capability.get_backend()

    libredte_backend_mock.assert_called_once_with(
        base_url='https://global.example.cl',
        api_token='global-token',
        auth_scheme='Bearer',
    )


@override_settings(PLUGIN_LIBREDTE_BACKEND_API_TOKEN='')
def test_get_extra_context_reports_no_global_token_when_unset() -> None:
    assert LibredteLibApiPlugin({}).get_extra_context() == {
        'has_global_token': False,
    }


@override_settings(PLUGIN_LIBREDTE_BACKEND_API_TOKEN='global-token')
def test_get_extra_context_reports_a_global_token_when_set() -> None:
    assert LibredteLibApiPlugin({}).get_extra_context() == {
        'has_global_token': True,
    }


def test_config_form_does_not_require_base_url_or_token() -> None:
    """Ambos son opcionales: vacíos, `get_backend()` usa los globales."""
    form = LibredteLibApiConfigForm(data={'auth_scheme': 'Bearer'})

    assert form.is_valid()


def test_config_form_auth_scheme_defaults_to_bearer_when_missing() -> None:
    """Una config guardada antes de que existiera este campo no rompe."""
    form = LibredteLibApiConfigForm(initial={})

    assert form['auth_scheme'].value() == 'Bearer'


@override_settings(PLUGIN_LIBREDTE_BACKEND_API_URL='https://global.example.cl')
def test_config_form_shows_the_global_url_as_a_placeholder() -> None:
    form = LibredteLibApiConfigForm(data={})

    placeholder = form.fields['base_url'].widget.attrs['placeholder']
    assert placeholder == 'https://global.example.cl'


@override_settings(PLUGIN_LIBREDTE_BACKEND_API_TOKEN='global-token')
def test_config_form_mentions_the_global_token_when_one_is_set() -> None:
    form = LibredteLibApiConfigForm(data={})

    assert form.fields['api_token'].help_text


@override_settings(
    PLUGIN_LIBREDTE_BACKEND_API_URL='https://global.example.cl',
    PLUGIN_LIBREDTE_BACKEND_API_TOKEN='global-token',
)
def test_config_form_rejects_a_custom_url_without_a_custom_token() -> None:
    """
    Sin esto, `get_backend()` mandaría el token global a una URL ajena.

    Dejar `api_token` vacío resuelve al token global (ver
    `config_resolver.py`) — combinado con una `base_url` propia,
    filtraría ese token a un servidor que el tenant controla.
    """
    form = LibredteLibApiConfigForm(
        data={
            'base_url': 'https://tenant.example.cl',
            'auth_scheme': 'Bearer',
        },
    )

    assert not form.is_valid()


@override_settings(
    PLUGIN_LIBREDTE_BACKEND_API_URL='https://global.example.cl',
    PLUGIN_LIBREDTE_BACKEND_API_TOKEN='global-token',
)
def test_config_form_accepts_a_custom_url_with_a_custom_token() -> None:
    """Con token propio, no hay ningún secreto de la plataforma en juego."""
    form = LibredteLibApiConfigForm(
        data={
            'base_url': 'https://tenant.example.cl',
            'api_token': 'tenant-token',
            'auth_scheme': 'Bearer',
        },
    )

    assert form.is_valid()


@override_settings(
    PLUGIN_LIBREDTE_BACKEND_API_URL='https://global.example.cl',
    PLUGIN_LIBREDTE_BACKEND_API_TOKEN='global-token',
)
def test_config_form_accepts_leaving_both_empty() -> None:
    """Vacíos ambos, resuelve a la URL global — sin URL ajena, sin riesgo."""
    form = LibredteLibApiConfigForm(data={'auth_scheme': 'Bearer'})

    assert form.is_valid()


@override_settings(PLUGIN_LIBREDTE_BACKEND_API_TOKEN='')
def test_config_form_accepts_a_custom_url_without_any_global_token() -> None:
    """Sin token global configurado, no hay nada que filtrar — no aplica."""
    form = LibredteLibApiConfigForm(
        data={
            'base_url': 'https://tenant.example.cl',
            'auth_scheme': 'Bearer',
        },
    )

    assert form.is_valid()
