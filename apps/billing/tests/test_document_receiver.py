"""
Tests para `services.document_receiver._resolver_emisor()`.

El resto de `document_receiver.py` (`load_xml()`) llama a la API real
de LibreDTE Lib — no se prueba acá. Esto solo prueba la resolución del
`Emisor`, que es puramente local (el cálculo de montos en CLP se
prueba en `test_dte.py`).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.billing.models import Emisor
from apps.billing.services.document_receiver import _resolver_emisor
from apps.libredte.models import Comuna, Contribuyente, Pais

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def chile() -> Pais:
    """`Receptor.save()` necesita a Chile disponible (país por defecto)."""
    return Pais.objects.create(codigo=Pais.CHILE, glosa='Chile')


@pytest.fixture
def comuna() -> Comuna:
    return Comuna.objects.create(codigo=13101, glosa='Santiago')


@pytest.fixture
def contribuyente(comuna: Comuna) -> Contribuyente:
    usuario = User.objects.create_user('demo', password='demo12345')
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


def test_crea_un_emisor_nuevo_si_no_existe(
    contribuyente: Contribuyente,
) -> None:
    emisor = _resolver_emisor(
        contribuyente,
        {
            'RUTEmisor': '12345678-5',
            'RznSoc': 'Proveedor de prueba',
            'GiroEmis': 'Comercio',
        },
    )

    assert emisor.rut == 12345678
    assert emisor.dv == '5'
    assert emisor.razon_social == 'Proveedor de prueba'
    assert emisor.giro == 'Comercio'


def test_actualiza_un_emisor_ya_existente_encontrado_por_rut(
    contribuyente: Contribuyente,
) -> None:
    """El emisor se mantiene al día con lo último que envió."""
    Emisor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        razon_social='Nombre antiguo',
        giro='Giro antiguo',
    )

    emisor = _resolver_emisor(
        contribuyente,
        {
            'RUTEmisor': '12345678-5',
            'RznSoc': 'Nombre actualizado',
            'GiroEmis': 'Giro actualizado',
        },
    )

    assert Emisor.objects.filter(contribuyente=contribuyente).count() == 1
    assert emisor.razon_social == 'Nombre actualizado'
    assert emisor.giro == 'Giro actualizado'


def test_datos_ausentes_quedan_en_blanco_no_en_none(
    contribuyente: Contribuyente,
) -> None:
    """Campos de texto opcionales ausentes quedan `''`, no `None`."""
    emisor = _resolver_emisor(
        contribuyente,
        {'RUTEmisor': '12345678-5'},
    )

    assert emisor.razon_social == ''
    assert emisor.giro == ''
    assert emisor.telefono == ''
    assert emisor.correo == ''
    assert emisor.direccion == ''
    assert emisor.ciudad == ''
    assert emisor.comuna is None


def test_resuelve_la_comuna_por_glosa(
    contribuyente: Contribuyente,
    comuna: Comuna,
) -> None:
    emisor = _resolver_emisor(
        contribuyente,
        {
            'RUTEmisor': '12345678-5',
            'RznSoc': 'Proveedor de prueba',
            'CmnaOrigen': 'Santiago',
        },
    )

    assert emisor.comuna == comuna


def test_giro_del_emisor_admite_el_largo_maximo_del_sii(
    contribuyente: Contribuyente,
) -> None:
    """
    `GiroEmis` admite hasta 80 caracteres en el esquema del SII.

    `full_clean()` valida `max_length` también en SQLite, que no lo
    aplica a nivel de base de datos (Postgres sí).
    """
    giro = 'G' * 80
    emisor = _resolver_emisor(
        contribuyente,
        {'RUTEmisor': '12345678-5', 'GiroEmis': giro},
    )

    emisor.full_clean()
    assert emisor.giro == giro
