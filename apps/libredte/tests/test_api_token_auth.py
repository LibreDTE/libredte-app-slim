"""
El token de API autentica de verdad contra un endpoint real.

Vive en `libredte` y no en `core` (donde está el resto del token, ver
`apps/core/tests/test_api_token.py`) porque necesita un `Contribuyente`
para pasar `RequireContribuyenteMiddleware` y para que el endpoint
tenga algo que devolver — y `core` no importa modelos de dominio.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from rest_framework.authtoken.models import Token

from apps.libredte.models import Comuna, Contribuyente, Sucursal

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario() -> User:
    user = User.objects.create_user('demo', password='demo12345')
    comuna = Comuna.objects.create(codigo=13101, glosa='Santiago')
    contribuyente = Contribuyente.objects.create(
        usuario=user,
        rut=76192083,
        dv='9',
        razon_social='SASCO SpA',
        giro='Servicios',
        direccion='Av. Siempre Viva 123',
        comuna=comuna,
        autorizacion_dte_resolucion_fecha='2014-08-22',
        autorizacion_dte_resolucion_numero=0,
    )
    Sucursal.objects.create(
        contribuyente=contribuyente,
        es_matriz=True,
        nombre='Casa matriz',
        direccion=contribuyente.direccion,
        comuna=comuna,
    )
    return user


def test_the_token_authenticates_an_external_client(
    client: Client,
    usuario: User,
) -> None:
    token = Token.objects.create(user=usuario)

    response = client.get(
        reverse('libredte_api:sucursales'),
        headers={'authorization': f'Token {token.key}'},
    )

    assert response.status_code == 200


def test_without_a_token_the_endpoint_is_closed(
    client: Client,
    usuario: User,
) -> None:
    response = client.get(reverse('libredte_api:sucursales'))

    assert response.status_code == 401


def test_an_invalid_token_is_rejected(
    client: Client,
    usuario: User,
) -> None:
    response = client.get(
        reverse('libredte_api:sucursales'),
        headers={'authorization': 'Token no-existe'},
    )

    assert response.status_code == 401
