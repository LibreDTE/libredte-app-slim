"""
Tests para `billing_api:receptor_buscar` (autocompletar el receptor al
emitir).

Puramente local (`Receptor`/`Comuna`/`Pais`) — no llama a la API de
LibreDTE Lib. Ver `services/biller.py::_resolver_receptor()` para el
mismo criterio de prioridad (`codigo_interno` > `rut` > `razon_social`).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.billing.models import Receptor
from apps.libredte import tenancy
from apps.libredte.models import Comuna, Contribuyente, Pais

pytestmark = pytest.mark.django_db


def _autenticar(client: Client, contribuyente: Contribuyente) -> None:
    """Login + deja `contribuyente` activo en la sesión del cliente."""
    client.force_login(contribuyente.usuario)
    session = client.session
    session[tenancy._SESSION_KEY] = contribuyente.pk
    session.save()


@pytest.fixture(autouse=True)
def chile() -> Pais:
    """`Receptor.save()` necesita a Chile disponible (país por defecto)."""
    return Pais.objects.create(codigo=Pais.CHILE, glosa='Chile')


@pytest.fixture
def comuna() -> Comuna:
    return Comuna.objects.create(codigo=13101, glosa='Santiago')


@pytest.fixture
def usuario() -> User:
    return User.objects.create_user('demo', password='demo12345')


@pytest.fixture
def contribuyente(comuna: Comuna, usuario: User) -> Contribuyente:
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


def test_sin_parametros_devuelve_la_lista_de_receptores(
    client: Client,
    contribuyente: Contribuyente,
) -> None:
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        codigo_interno='amazon',
        razon_social='Amazon Inc.',
    )
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=76543210,
        dv='1',
        razon_social='Otro Cliente Ltda.',
    )
    _autenticar(client, contribuyente)

    response = client.get(reverse('billing_api:receptor_buscar'))

    assert response.status_code == 200
    assert response.json() == [
        {
            'rut': '12345678-5',
            'codigo_interno': 'amazon',
            'razon_social': 'Amazon Inc.',
        },
        {
            # Sin `codigo_interno` explícito, `Receptor.save()` lo
            # autoasigna como RUT+DV (ver `Receptor.save()`).
            'rut': '76543210-1',
            'codigo_interno': '0765432101',
            'razon_social': 'Otro Cliente Ltda.',
        },
    ]


def test_busca_por_rut(client: Client, contribuyente: Contribuyente) -> None:
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        razon_social='Cliente de prueba',
    )
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:receptor_buscar'),
        {'rut': '12345678-5'},
    )

    assert response.status_code == 200
    assert response.json()['RznSocRecep'] == 'Cliente de prueba'


def test_busca_por_codigo_interno(
    client: Client,
    contribuyente: Contribuyente,
) -> None:
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        codigo_interno='amazon',
        razon_social='Amazon Inc.',
    )
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:receptor_buscar'),
        {'codigo_interno': 'amazon'},
    )

    assert response.status_code == 200
    assert response.json()['RUTRecep'] == '12345678-5'


def test_busca_por_razon_social(
    client: Client,
    contribuyente: Contribuyente,
) -> None:
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        razon_social='Cliente de prueba',
    )
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:receptor_buscar'),
        {'razon_social': 'Cliente de prueba'},
    )

    assert response.status_code == 200
    assert response.json()['RUTRecep'] == '12345678-5'


def test_codigo_interno_tiene_prioridad_sobre_rut(
    client: Client,
    contribuyente: Contribuyente,
) -> None:
    """Mismo criterio de prioridad que `biller._resolver_receptor()`."""
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        codigo_interno='amazon',
        razon_social='Amazon Inc.',
    )
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=99999999,
        dv='9',
        razon_social='Otro Cliente',
    )
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:receptor_buscar'),
        {'codigo_interno': 'amazon', 'rut': '99999999-9'},
    )

    assert response.status_code == 200
    assert response.json()['RznSocRecep'] == 'Amazon Inc.'


def test_404_si_no_hay_match(
    client: Client,
    contribuyente: Contribuyente,
) -> None:
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:receptor_buscar'),
        {'rut': '11111111-1'},
    )

    assert response.status_code == 404


def test_respuesta_trae_el_shape_que_espera_documentoform(
    client: Client,
    contribuyente: Contribuyente,
    comuna: Comuna,
    chile: Pais,
) -> None:
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        codigo_interno='amazon',
        razon_social='Amazon Inc.',
        giro='Comercio',
        telefono='+56912345678',
        correo='contacto@amazon.cl',
        direccion='Av. Siempre Viva 123',
        comuna=comuna,
        ciudad='Santiago',
        pais=chile,
        numero_identificacion='',
    )
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:receptor_buscar'),
        {'rut': '12345678-5'},
    )

    assert response.json() == {
        'RUTRecep': '12345678-5',
        'RznSocRecep': 'Amazon Inc.',
        'GiroRecep': 'Comercio',
        'CdgIntRecep': 'amazon',
        'Contacto': '+56912345678',
        'CorreoRecep': 'contacto@amazon.cl',
        'DirRecep': 'Av. Siempre Viva 123',
        'CmnaRecep': 'Santiago',
        'CiudadRecep': 'Santiago',
        'Nacionalidad': str(Pais.CHILE),
        'NumId': '',
    }
