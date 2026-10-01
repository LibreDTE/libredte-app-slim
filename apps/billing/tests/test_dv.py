"""Tests del dígito verificador (`DvField`): siempre se guarda en mayúscula."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import connection

from apps.billing.models import Emisor, Receptor
from apps.billing.services import biller
from apps.libredte.models import Comuna, Contribuyente, Pais

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def chile() -> Pais:
    """`Receptor.save()` y `Emisor.save()` necesitan a Chile (por defecto)."""
    return Pais.objects.create(codigo=Pais.CHILE, glosa='Chile')


@pytest.fixture
def contribuyente() -> Contribuyente:
    return Contribuyente.objects.create(
        usuario=User.objects.create_user('demo'),
        rut=76192083,
        dv='9',
        razon_social='SASCO SpA',
        giro='Servicios',
        direccion='Av. Siempre Viva 123',
        comuna=Comuna.objects.create(codigo=13101, glosa='Santiago'),
        autorizacion_dte_resolucion_fecha='2014-08-22',
        autorizacion_dte_resolucion_numero=0,
    )


def _dv_en_la_base(tabla: str, pk: int) -> str:
    """El `dv` tal como quedó en la fila, sin pasar por el modelo."""
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT dv FROM {tabla} WHERE id = %s', [pk])
        return str(cursor.fetchone()[0])


def test_el_dv_del_contribuyente_se_guarda_en_mayuscula() -> None:
    usuario = User.objects.create_user('otro')
    contribuyente = Contribuyente.objects.create(
        usuario=usuario,
        rut=60803000,
        dv='k',
        razon_social='SII',
        giro='Gobierno',
        direccion='Teatinos 120',
        comuna=Comuna.objects.create(codigo=13101, glosa='Santiago'),
        autorizacion_dte_resolucion_fecha='2014-08-22',
        autorizacion_dte_resolucion_numero=0,
    )

    assert contribuyente.dv == 'K'
    assert _dv_en_la_base('libredte_contribuyente', contribuyente.pk) == 'K'


def test_el_dv_del_receptor_se_guarda_en_mayuscula_y_en_su_codigo(
    contribuyente: Contribuyente,
) -> None:
    receptor = Receptor.objects.create(
        contribuyente=contribuyente, rut=60803000, dv='k'
    )

    assert receptor.dv == 'K'
    assert receptor.codigo_interno == '060803000K'
    assert _dv_en_la_base('billing_receptor', receptor.pk) == 'K'


def test_el_dv_del_emisor_se_guarda_en_mayuscula(
    contribuyente: Contribuyente,
) -> None:
    emisor = Emisor.objects.create(
        contribuyente=contribuyente, rut=60803000, dv='k'
    )

    assert emisor.dv == 'K'
    assert emisor.codigo_interno == '060803000K'
    assert _dv_en_la_base('billing_emisor', emisor.pk) == 'K'


def test_una_consulta_por_dv_encuentra_la_fila_con_cualquier_mayuscula(
    contribuyente: Contribuyente,
) -> None:
    receptor = Receptor.objects.create(
        contribuyente=contribuyente, rut=60803000, dv='K'
    )

    for dv in ('k', 'K'):
        encontrado = Receptor.objects.get(
            contribuyente=contribuyente, rut=60803000, dv=dv
        )
        assert encontrado.pk == receptor.pk


def test_el_receptor_de_un_documento_con_dv_en_minuscula_no_se_duplica(
    contribuyente: Contribuyente,
) -> None:
    """
    El mismo RUT llega como `60803000-K` (DTE, biblioteca) o `60803000-k`
    (formulario): es un solo receptor, no un choque con su `codigo_interno`.
    """
    primero = biller._resolver_receptor(
        contribuyente, {'RUTRecep': '60803000-k', 'RznSocRecep': 'SII'}
    )
    segundo = biller._resolver_receptor(
        contribuyente, {'RUTRecep': '60803000-K', 'RznSocRecep': 'SII'}
    )

    assert primero.pk == segundo.pk
    assert Receptor.objects.count() == 1
