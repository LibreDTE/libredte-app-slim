"""Tests para los modelos de `libredte` (constraints, sobre todo)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError

from apps.libredte.models import (
    ActividadEconomica,
    Certificado,
    Comuna,
    Contribuyente,
    ContribuyenteActividadEconomica,
    Sucursal,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def comuna() -> Comuna:
    return Comuna.objects.create(codigo=13101, glosa='Santiago')


@pytest.fixture
def actividad_economica() -> ActividadEconomica:
    return ActividadEconomica.objects.create(
        codigo=620200,
        glosa='Consultoría de informática',
        afecta_iva=True,
    )


@pytest.fixture
def usuario() -> User:
    return User.objects.create_user('demo')


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


def test_contribuyente_rut_is_unique(
    contribuyente: Contribuyente,
    comuna: Comuna,
    usuario: User,
) -> None:
    with pytest.raises(IntegrityError):
        Contribuyente.objects.create(
            usuario=usuario,
            rut=contribuyente.rut,
            dv='0',
            razon_social='Otra empresa',
            giro='Otro giro',
            direccion='Otra dirección',
            comuna=comuna,
            autorizacion_dte_resolucion_fecha='2014-08-22',
        )


def test_contribuyente_actividad_economica_principal_is_unique(
    contribuyente: Contribuyente,
    actividad_economica: ActividadEconomica,
) -> None:
    otra = ActividadEconomica.objects.create(
        codigo='620100',
        glosa='Programación informática',
    )
    ContribuyenteActividadEconomica.objects.create(
        contribuyente=contribuyente,
        actividad_economica=actividad_economica,
        es_principal=True,
    )

    with pytest.raises(IntegrityError):
        ContribuyenteActividadEconomica.objects.create(
            contribuyente=contribuyente,
            actividad_economica=otra,
            es_principal=True,
        )


def test_sucursal_matriz_is_unique_per_contribuyente(
    contribuyente: Contribuyente,
    comuna: Comuna,
) -> None:
    Sucursal.objects.create(
        contribuyente=contribuyente,
        es_matriz=True,
        direccion='Av. Siempre Viva 123',
        comuna=comuna,
    )

    with pytest.raises(IntegrityError):
        Sucursal.objects.create(
            contribuyente=contribuyente,
            es_matriz=True,
            direccion='Otra sucursal',
            comuna=comuna,
        )


def test_certificado_is_unique_per_usuario(usuario: User) -> None:
    kwargs = {
        'usuario': usuario,
        'certificado_id': '12345678-5',
        'x509': '-----BEGIN CERTIFICATE-----',
        'clave_privada': '-----BEGIN PRIVATE KEY-----',
    }
    Certificado.objects.create(**kwargs)

    with pytest.raises(IntegrityError):
        Certificado.objects.create(**kwargs)


def test_certificado_id_can_repeat_across_usuarios(usuario: User) -> None:
    otro_usuario = User.objects.create_user('otro')
    kwargs = {
        'certificado_id': '12345678-5',
        'x509': '-----BEGIN CERTIFICATE-----',
        'clave_privada': '-----BEGIN PRIVATE KEY-----',
    }
    Certificado.objects.create(usuario=usuario, **kwargs)

    # No debería lanzar — cada usuario puede tener su propio
    # certificado con el mismo `certificado_id` (el RUT del titular).
    Certificado.objects.create(usuario=otro_usuario, **kwargs)
