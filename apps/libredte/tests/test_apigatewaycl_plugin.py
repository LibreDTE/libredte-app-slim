"""Tests para el plugin `apigatewaycl` (capability `sii.backend`)."""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse

from apps.core.plugin.catalog import (
    all_plugins,
    get_capability,
    plugins_for_capability,
)
from apps.libredte import tenancy
from apps.libredte.models import Certificado, Comuna, Contribuyente
from apps.libredte.plugins.apigatewaycl.forms import ApiGatewayClConfigForm
from apps.libredte.plugins.apigatewaycl.plugin import ApiGatewayClPlugin
from apps.libredte.plugins.contracts import (
    SiiBackend,
    SiiBackendAuthError,
    SiiBackendPluginCapabilityDefinition,
)


@pytest.fixture
def contribuyente_sin_guardar() -> Contribuyente:
    """Instancia en memoria, sin BD — alcanza para `rut`/`dv`/`certificado`."""
    return Contribuyente(rut=76192083, dv='9')


def test_it_is_registered_in_the_catalog() -> None:
    """`apps/core/apps.py::ready()` lo registra vía `autodiscover_modules`."""
    assert ApiGatewayClPlugin in all_plugins()


def test_it_implements_the_sii_backend_capability() -> None:
    assert ApiGatewayClPlugin in plugins_for_capability(
        SiiBackendPluginCapabilityDefinition
    )


def test_the_sii_backend_capability_is_registered() -> None:
    """`apps/libredte/platform.py` la registra vía `autodiscover_modules`."""
    capability = get_capability('sii.backend')

    assert capability is not None
    assert capability.label


def test_get_backend_returns_an_instance_of_sii_backend(
    contribuyente_sin_guardar: Contribuyente,
) -> None:
    plugin = ApiGatewayClPlugin(
        {'base_url': 'https://apigateway.example.cl', 'api_token': 'token'},
    )

    capability = plugin.get_capability(SiiBackendPluginCapabilityDefinition)
    assert isinstance(capability, SiiBackendPluginCapabilityDefinition)
    backend = capability.get_backend(contribuyente_sin_guardar)

    assert isinstance(backend, SiiBackend)


@override_settings(PLUGIN_APIGATEWAYCL_API_TOKEN='')
def test_get_backend_returns_none_when_no_token_is_configured(
    contribuyente_sin_guardar: Contribuyente,
) -> None:
    """
    Sin token propio ni global, no hay forma de construir un `SiiBackend`.

    A diferencia de `libredte.backend` (que sí tiene un backend
    público al que caer), `apigatewaycl` siempre necesita un token —
    construirlo sin uno lanzaría `ApiException` en vez de fallar
    limpio, así que `get_backend()` debe cortar antes con `None`.
    """
    plugin = ApiGatewayClPlugin({})

    capability = plugin.get_capability(SiiBackendPluginCapabilityDefinition)
    assert isinstance(capability, SiiBackendPluginCapabilityDefinition)

    assert capability.get_backend(contribuyente_sin_guardar) is None


@mock.patch('apps.libredte.plugins.apigatewaycl.capabilities.Rcv')
def test_sii_rcv_ventas_resumen_uses_the_tenants_own_config(
    rcv_mock: mock.Mock,
    contribuyente_sin_guardar: Contribuyente,
) -> None:
    plugin = ApiGatewayClPlugin(
        {
            'base_url': 'https://tenant.example.cl',
            'api_token': 'tenant-token',
            'sii_auth_clave': 'clave-sii',
        },
    )
    capability = plugin.get_capability(SiiBackendPluginCapabilityDefinition)
    assert isinstance(capability, SiiBackendPluginCapabilityDefinition)
    backend = capability.get_backend(contribuyente_sin_guardar)
    assert backend is not None

    backend.sii_rcv_ventas_resumen(periodo='202501')

    rcv_mock.assert_called_once_with(
        identificador='76192083-9',
        clave='clave-sii',
        api_token='tenant-token',
        api_url='https://tenant.example.cl',
    )
    rcv_mock.return_value.ventas_resumen.assert_called_once_with(
        emisor='76192083-9',
        periodo='202501',
        certificacion='1',
    )


@override_settings(
    PLUGIN_APIGATEWAYCL_API_URL='https://global.example.cl',
    PLUGIN_APIGATEWAYCL_API_TOKEN='global-token',
)
@mock.patch('apps.libredte.plugins.apigatewaycl.capabilities.Rcv')
def test_sii_rcv_ventas_resumen_falls_back_to_the_global_settings(
    rcv_mock: mock.Mock,
    contribuyente_sin_guardar: Contribuyente,
) -> None:
    """`sii_auth_clave` no tiene reserva global — siempre es del tenant."""
    plugin = ApiGatewayClPlugin({'sii_auth_clave': 'clave-sii'})
    capability = plugin.get_capability(SiiBackendPluginCapabilityDefinition)
    assert isinstance(capability, SiiBackendPluginCapabilityDefinition)
    backend = capability.get_backend(contribuyente_sin_guardar)
    assert backend is not None

    backend.sii_rcv_ventas_resumen(periodo='202501')

    rcv_mock.assert_called_once_with(
        identificador='76192083-9',
        clave='clave-sii',
        api_token='global-token',
        api_url='https://global.example.cl',
    )


def test_sii_rcv_ventas_resumen_raises_without_sii_auth_clave(
    contribuyente_sin_guardar: Contribuyente,
) -> None:
    plugin = ApiGatewayClPlugin({'api_token': 'token'})
    capability = plugin.get_capability(SiiBackendPluginCapabilityDefinition)
    assert isinstance(capability, SiiBackendPluginCapabilityDefinition)
    backend = capability.get_backend(contribuyente_sin_guardar)
    assert backend is not None

    with pytest.raises(SiiBackendAuthError):
        backend.sii_rcv_ventas_resumen(periodo='202501')


@mock.patch(
    'apps.libredte.plugins.apigatewaycl.capabilities.DteContribuyentes'
)
def test_sii_dte_contribuyentes_usuarios_uses_the_linked_certificado(
    dte_contribuyentes_mock: mock.Mock,
    contribuyente_sin_guardar: Contribuyente,
) -> None:
    contribuyente_sin_guardar.certificado = Certificado(
        x509='---CERT---',
        clave_privada='---LLAVE---',
    )
    plugin = ApiGatewayClPlugin({'api_token': 'token'})
    capability = plugin.get_capability(SiiBackendPluginCapabilityDefinition)
    assert isinstance(capability, SiiBackendPluginCapabilityDefinition)
    backend = capability.get_backend(contribuyente_sin_guardar)
    assert backend is not None

    backend.sii_dte_contribuyentes_usuarios()

    dte_contribuyentes_mock.assert_called_once_with(
        identificador='---CERT---',
        clave='---LLAVE---',
        api_token='token',
        api_url=mock.ANY,
    )
    dte_contribuyentes_mock.return_value.usuarios.assert_called_once_with(
        rut='76192083-9',
        certificacion='1',
    )


def test_sii_dte_contribuyentes_usuarios_raises_without_certificado(
    contribuyente_sin_guardar: Contribuyente,
) -> None:
    plugin = ApiGatewayClPlugin({'api_token': 'token'})
    capability = plugin.get_capability(SiiBackendPluginCapabilityDefinition)
    assert isinstance(capability, SiiBackendPluginCapabilityDefinition)
    backend = capability.get_backend(contribuyente_sin_guardar)
    assert backend is not None

    with pytest.raises(SiiBackendAuthError):
        backend.sii_dte_contribuyentes_usuarios()


@override_settings(PLUGIN_APIGATEWAYCL_API_TOKEN='')
def test_get_extra_context_reports_no_global_token_when_unset() -> None:
    assert ApiGatewayClPlugin({}).get_extra_context() == {
        'has_global_token': False,
    }


@override_settings(PLUGIN_APIGATEWAYCL_API_TOKEN='global-token')
def test_get_extra_context_reports_a_global_token_when_set() -> None:
    assert ApiGatewayClPlugin({}).get_extra_context() == {
        'has_global_token': True,
    }


def test_config_form_does_not_require_base_url_or_token() -> None:
    """Ambos son opcionales: vacíos, `get_backend()` usa los globales."""
    form = ApiGatewayClConfigForm(data={})

    assert form.is_valid()


def test_config_form_accepts_a_sii_auth_clave() -> None:
    """Sin reserva global — si el tenant la necesita, la pone acá."""
    form = ApiGatewayClConfigForm(data={'sii_auth_clave': 'clave-sii'})

    assert form.is_valid()
    assert form.cleaned_data['sii_auth_clave'] == 'clave-sii'


def test_config_form_does_not_require_a_sii_auth_clave() -> None:
    """Sin ella, solo quedan indisponibles las operaciones que la piden."""
    form = ApiGatewayClConfigForm(data={})

    assert form.is_valid()


@override_settings(PLUGIN_APIGATEWAYCL_API_URL='https://global.example.cl')
def test_config_form_shows_the_global_url_as_a_placeholder() -> None:
    form = ApiGatewayClConfigForm(data={})

    placeholder = form.fields['base_url'].widget.attrs['placeholder']
    assert placeholder == 'https://global.example.cl'


@override_settings(PLUGIN_APIGATEWAYCL_API_TOKEN='global-token')
def test_config_form_mentions_the_global_token_when_one_is_set() -> None:
    form = ApiGatewayClConfigForm(data={})

    assert form.fields['api_token'].help_text


@override_settings(
    PLUGIN_APIGATEWAYCL_API_URL='https://global.example.cl',
    PLUGIN_APIGATEWAYCL_API_TOKEN='global-token',
)
def test_config_form_rejects_a_custom_url_without_a_custom_token() -> None:
    """
    Sin esto, `get_backend()` mandaría el token global a una URL ajena.

    Dejar `api_token` vacío resuelve al token global (ver
    `config_resolver.py`) — combinado con una `base_url` propia,
    filtraría ese token a un servidor que el tenant controla.
    """
    form = ApiGatewayClConfigForm(
        data={'base_url': 'https://tenant.example.cl'},
    )

    assert not form.is_valid()


@override_settings(
    PLUGIN_APIGATEWAYCL_API_URL='https://global.example.cl',
    PLUGIN_APIGATEWAYCL_API_TOKEN='global-token',
)
def test_config_form_accepts_a_custom_url_with_a_custom_token() -> None:
    """Con token propio, no hay ningún secreto de la plataforma en juego."""
    form = ApiGatewayClConfigForm(
        data={
            'base_url': 'https://tenant.example.cl',
            'api_token': 'tenant-token',
        },
    )

    assert form.is_valid()


@override_settings(
    PLUGIN_APIGATEWAYCL_API_URL='https://global.example.cl',
    PLUGIN_APIGATEWAYCL_API_TOKEN='global-token',
)
def test_config_form_accepts_leaving_both_empty() -> None:
    """Vacíos ambos, resuelve a la URL global — sin URL ajena, sin riesgo."""
    form = ApiGatewayClConfigForm(data={})

    assert form.is_valid()


@override_settings(PLUGIN_APIGATEWAYCL_API_TOKEN='')
def test_config_form_accepts_a_custom_url_without_any_global_token() -> None:
    """Sin token global configurado, no hay nada que filtrar — no aplica."""
    form = ApiGatewayClConfigForm(
        data={'base_url': 'https://tenant.example.cl'},
    )

    assert form.is_valid()


@pytest.fixture
def contribuyente(db: None) -> Contribuyente:
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


def test_configure_page_renders(client_autenticado: Client) -> None:
    """Cubre `apigatewaycl_configure.html` de punta a punta."""
    response = client_autenticado.get(
        reverse('core_settings:plugin_configure', args=['apigatewaycl'])
    )

    assert response.status_code == 200


@override_settings(PLUGIN_APIGATEWAYCL_API_TOKEN='global-token')
def test_configure_page_shows_the_global_token_notice(
    client_autenticado: Client,
) -> None:
    response = client_autenticado.get(
        reverse('core_settings:plugin_configure', args=['apigatewaycl'])
    )

    assert 'token de API configurado a nivel de plataforma' in (
        response.content.decode()
    )


@override_settings(PLUGIN_APIGATEWAYCL_API_TOKEN='')
def test_configure_page_hides_the_global_token_notice_when_unset(
    client_autenticado: Client,
) -> None:
    response = client_autenticado.get(
        reverse('core_settings:plugin_configure', args=['apigatewaycl'])
    )

    assert 'token de API configurado a nivel de plataforma' not in (
        response.content.decode()
    )
