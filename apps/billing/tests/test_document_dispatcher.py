"""
Tests para `services.document_dispatcher._environment()`/
`_autorizacion_dte_extra()`.

`send()`/`check_status()` llaman a la API real de LibreDTE Lib — no se
prueban acá (mismo criterio que `test_biller.py`/
`test_document_receiver.py`). Esto solo prueba los dos helpers
puramente locales.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import User
from libredte_lib_sdk.billing.enums import SiiEnvironment

from apps.billing.services.document_dispatcher import (
    _autorizacion_dte_extra,
    _environment,
)
from apps.libredte.models import Comuna, Contribuyente, Pais

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def chile() -> Pais:
    """`Receptor.save()` necesita a Chile disponible (país por defecto)."""
    return Pais.objects.create(codigo=Pais.CHILE, glosa='Chile')


@pytest.fixture
def comuna() -> Comuna:
    return Comuna.objects.create(codigo=13101, glosa='Santiago')


def _create_contribuyente(
    comuna: Comuna,
    *,
    autorizacion_dte_resolucion_numero: int,
    autorizacion_dte_resolucion_fecha: date | None = date(2014, 8, 22),
) -> Contribuyente:
    usuario = User.objects.create_user('demo', password='demo12345')
    return Contribuyente.objects.create(
        usuario=usuario,
        rut=76192083,
        dv='9',
        razon_social='SASCO SpA',
        giro='Servicios',
        direccion='Av. Siempre Viva 123',
        comuna=comuna,
        autorizacion_dte_resolucion_fecha=(autorizacion_dte_resolucion_fecha),
        autorizacion_dte_resolucion_numero=(
            autorizacion_dte_resolucion_numero
        ),
    )


def test_environment_es_certificacion_con_resolucion_numero_cero(
    comuna: Comuna,
) -> None:
    contribuyente = _create_contribuyente(
        comuna, autorizacion_dte_resolucion_numero=0
    )

    assert _environment(contribuyente) == SiiEnvironment.CERTIFICATION


def test_environment_es_produccion_con_cualquier_otro_numero(
    comuna: Comuna,
) -> None:
    contribuyente = _create_contribuyente(
        comuna, autorizacion_dte_resolucion_numero=1234
    )

    assert _environment(contribuyente) == SiiEnvironment.PRODUCTION


def test_autorizacion_dte_extra_vacio_sin_fecha_de_resolucion(
    comuna: Comuna,
) -> None:
    contribuyente = _create_contribuyente(
        comuna,
        autorizacion_dte_resolucion_numero=0,
        autorizacion_dte_resolucion_fecha=None,
    )

    assert _autorizacion_dte_extra(contribuyente) == {}


def test_autorizacion_dte_extra_incluye_la_resolucion_numero_cero(
    comuna: Comuna,
) -> None:
    """
    `numero_resolucion=0` es un valor SII válido (certificación).

    No se puede chequear con `and`/truthy — un `0` real no debe
    tratarse como "sin resolución" y omitirse.
    """
    contribuyente = _create_contribuyente(
        comuna, autorizacion_dte_resolucion_numero=0
    )

    extra = _autorizacion_dte_extra(contribuyente)

    assert extra == {
        'autorizacion_dte': {
            'fecha_resolucion': '2014-08-22',
            'numero_resolucion': 0,
        },
    }
