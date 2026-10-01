"""Test: el listado de Configuración > Plugins avisa de deprecados activos."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from apps.core.models import PluginConfig
from apps.core.plugin import catalog
from apps.core.plugin.base import BasePlugin
from apps.libredte import tenancy
from apps.libredte.models import Comuna, Contribuyente

pytestmark = pytest.mark.django_db


class _DeprecatedDummyPlugin(BasePlugin):
    """Plugin de mentira, deprecado, solo para probar el aviso del listado."""

    id = 'deprecated_dummy'
    label = 'Deprecated Dummy'
    deprecated_at = date(2020, 1, 1)


@pytest.fixture(autouse=True)
def _registered_dummy_plugin() -> Generator[None]:
    original = dict(catalog._plugins)
    catalog._plugins.clear()
    catalog.register(_DeprecatedDummyPlugin)
    yield
    catalog._plugins.clear()
    catalog._plugins.update(original)


@pytest.fixture
def contribuyente() -> Contribuyente:
    comuna = Comuna.objects.create(codigo=13101, glosa='Santiago')
    usuario = User.objects.create_user('demo')
    return Contribuyente.objects.create(
        usuario=usuario,
        rut=76192083,
        dv='9',
        razon_social='SASCO SpA',
        giro='Servicios',
        direccion='Av. Siempre Viva 123',
        comuna=comuna,
        autorizacion_dte_resolucion_fecha='2014-08-22',
        autorizacion_dte_resolucion_numero=0,
    )


@pytest.fixture
def client_autenticado(contribuyente: Contribuyente) -> Client:
    client = Client()
    client.force_login(contribuyente.usuario)
    session = client.session
    session[tenancy._SESSION_KEY] = contribuyente.pk
    session.save()
    return client


def test_plugins_list_warns_about_a_deprecated_active_plugin(
    client_autenticado: Client,
    contribuyente: Contribuyente,
) -> None:
    PluginConfig.objects.create(
        content_type=ContentType.objects.get_for_model(contribuyente),
        object_id=contribuyente.pk,
        plugin_id='deprecated_dummy',
        active=True,
    )

    response = client_autenticado.get(reverse('core_settings:plugins'))

    assert 'Deprecated Dummy' in response.content.decode()


def test_plugins_list_has_no_warning_without_an_active_deprecated_plugin(
    client_autenticado: Client,
) -> None:
    response = client_autenticado.get(reverse('core_settings:plugins'))

    assert 'deprecados activos' not in response.content.decode()


def test_plugins_list_shows_the_deprecated_column_with_a_deprecated_plugin(
    client_autenticado: Client,
) -> None:
    """La columna solo aparece si hay algo que mostrar en ella."""
    response = client_autenticado.get(reverse('core_settings:plugins'))

    assert '"title": "Deprecado"' in response.content.decode()


def test_plugins_list_hides_the_deprecated_column_without_a_deprecated_plugin(
    client_autenticado: Client,
) -> None:
    catalog._plugins.pop('deprecated_dummy')

    response = client_autenticado.get(reverse('core_settings:plugins'))

    assert '"title": "Deprecado"' not in response.content.decode()
