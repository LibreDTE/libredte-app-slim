"""Tests para `PluginActivationForm`."""

from __future__ import annotations

from apps.core.forms import PluginActivationForm


def test_activating_a_non_deprecated_plugin_is_valid() -> None:
    form = PluginActivationForm(data={'active': 'on'}, deprecated=False)

    assert form.is_valid()
    assert form.cleaned_data['active'] is True


def test_activating_a_deprecated_plugin_that_was_inactive_is_rejected() -> (
    None
):
    form = PluginActivationForm(
        data={'active': 'on'},
        deprecated=True,
        was_active=False,
    )

    assert not form.is_valid()
    assert 'active' in form.errors


def test_keeping_a_deprecated_plugin_active_is_still_allowed() -> None:
    """Uno ya activo antes de deprecarse no se fuerza a desactivar."""
    form = PluginActivationForm(
        data={'active': 'on'},
        deprecated=True,
        was_active=True,
    )

    assert form.is_valid()


def test_deactivating_a_deprecated_plugin_is_allowed() -> None:
    form = PluginActivationForm(
        data={},
        deprecated=True,
        was_active=True,
    )

    assert form.is_valid()
    assert form.cleaned_data['active'] is False
