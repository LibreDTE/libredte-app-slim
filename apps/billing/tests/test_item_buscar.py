"""
Tests para `billing_api:item_buscar` (autocompletar un ítem al emitir).

Este endpoint no llama a la API de LibreDTE Lib, es puramente local
(`Item`/`ItemCategoria`).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.billing.models import Item
from apps.libredte import tenancy
from apps.libredte.models import Comuna, Contribuyente

pytestmark = pytest.mark.django_db


def _autenticar(client: Client, contribuyente: Contribuyente) -> None:
    """Login + deja `contribuyente` activo en la sesión del cliente."""
    client.force_login(contribuyente.usuario)
    session = client.session
    session[tenancy._SESSION_KEY] = contribuyente.pk
    session.save()


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


def test_sin_codigo_devuelve_la_lista_de_items_activos(
    client: Client, contribuyente: Contribuyente
) -> None:
    Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-001',
        nombre='Licencia software',
        precio=50000,
    )
    Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-002',
        nombre='Otra licencia',
        precio=1000,
        activo=False,
    )
    _autenticar(client, contribuyente)

    response = client.get(reverse('billing_api:item_buscar'))

    assert response.status_code == 200
    codigos = [item['codigo'] for item in response.json()]
    assert codigos == ['SW-001']


def test_busca_por_codigo_sin_codigo_tipo(
    client: Client, contribuyente: Contribuyente
) -> None:
    """`codigo_tipo` es opcional — sin él, se busca por `codigo` a secas."""
    Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-001',
        nombre='Licencia software',
        precio=50000,
    )
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:item_buscar'),
        {'codigo': 'SW-001'},
    )

    assert response.status_code == 200
    assert response.json()['NmbItem'] == 'Licencia software'


def test_busca_por_codigo_y_codigo_tipo(
    client: Client, contribuyente: Contribuyente
) -> None:
    Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-001',
        codigo_tipo='EAN13',
        nombre='Licencia software',
        precio=50000,
    )
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:item_buscar'),
        {'codigo': 'SW-001', 'codigo_tipo': 'EAN13'},
    )

    assert response.status_code == 200
    assert response.json()['TpoCodigo'] == 'EAN13'


def test_404_si_no_existe_o_esta_inactivo(
    client: Client, contribuyente: Contribuyente
) -> None:
    Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-002',
        nombre='Otra licencia',
        precio=1000,
        activo=False,
    )
    _autenticar(client, contribuyente)

    inexistente = client.get(
        reverse('billing_api:item_buscar'),
        {'codigo': 'NO-EXISTE'},
    )
    inactivo = client.get(
        reverse('billing_api:item_buscar'),
        {'codigo': 'SW-002'},
    )

    assert inexistente.status_code == 404
    assert inactivo.status_code == 404


def test_respuesta_trae_el_shape_que_espera_itemform(
    client: Client, contribuyente: Contribuyente
) -> None:
    Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-001',
        nombre='Licencia software',
        descripcion='Licencia anual',
        unidad='UN',
        precio=50000,
    )
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:item_buscar'),
        {'codigo': 'SW-001'},
    )

    assert response.json() == {
        'TpoCodigo': 'INT1',
        'VlrCodigo': 'SW-001',
        'NmbItem': 'Licencia software',
        'DscItem': 'Licencia anual',
        'IndExe': '0',
        'UnmdItem': 'UN',
        'PrcItem': 50000,
        'CodImpAdic': '',
        'ValorDR': '0.00',
        'TpoValor': '%',
    }


def test_prcitem_siempre_va_en_neto(
    client: Client, contribuyente: Contribuyente
) -> None:
    """Un ítem `bruto` responde `PrcItem` ya convertido a neto."""
    Item.objects.create(
        contribuyente=contribuyente,
        codigo='HW-001',
        nombre='Monitor',
        precio=119000,
        bruto=True,
    )
    _autenticar(client, contribuyente)

    response = client.get(
        reverse('billing_api:item_buscar'),
        {'codigo': 'HW-001'},
    )

    assert response.json()['PrcItem'] == 100000
