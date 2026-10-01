"""Tests para `services.caf_manager` (reserva de folios, sobre todo)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.billing.models import Caf, CafFolio, TipoDte
from apps.billing.services import caf_manager
from apps.billing.services.caf_manager import (
    CafVencidoError,
    NoFolioDisponibleError,
)
from apps.libredte.models import Comuna, Contribuyente, Pais

pytestmark = pytest.mark.django_db


@pytest.fixture
def comuna() -> Comuna:
    return Comuna.objects.create(codigo=13101, glosa='Santiago')


@pytest.fixture(autouse=True)
def chile() -> Pais:
    """`Receptor.save()` necesita a Chile disponible (país por defecto)."""
    return Pais.objects.create(codigo=Pais.CHILE, glosa='Chile')


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


@pytest.fixture
def tipo_factura() -> TipoDte:
    return TipoDte.objects.create(codigo=33, glosa='Factura Electrónica')


def _crear_caf(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    *,
    fecha_vencimiento: date | None = None,
) -> None:
    Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        desde=1,
        hasta=100,
        xml_base64='<AUTORIZACION/>',
        fecha_autorizacion=date(2026, 1, 1),
        fecha_vencimiento=fecha_vencimiento,
        idk=300,
    )
    CafFolio.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        siguiente=1,
        disponibles=100,
        alerta=10,
    )


def test_reserve_next_folio_raises_when_the_covering_caf_is_vencido(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    _crear_caf(
        contribuyente,
        tipo_factura,
        fecha_vencimiento=timezone.localdate() - timedelta(days=1),
    )

    with pytest.raises(CafVencidoError):
        caf_manager.reserve_next_folio(contribuyente, tipo_factura)


def test_reserve_next_folio_succeeds_without_a_fecha_vencimiento(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    _crear_caf(contribuyente, tipo_factura, fecha_vencimiento=None)

    folio, caf_xml = caf_manager.reserve_next_folio(
        contribuyente,
        tipo_factura,
    )

    assert folio == 1
    assert caf_xml == '<AUTORIZACION/>'


def test_reserve_next_folio_succeeds_when_the_covering_caf_is_vigente(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    _crear_caf(
        contribuyente,
        tipo_factura,
        fecha_vencimiento=timezone.localdate() + timedelta(days=1),
    )

    folio, _caf_xml = caf_manager.reserve_next_folio(
        contribuyente,
        tipo_factura,
    )

    assert folio == 1


def test_reserve_folio_also_raises_when_the_covering_caf_is_vencido(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """
    La única diferencia con `reserve_next_folio()` es quién decide el
    folio (el contador o quien llama) — el resultado se puede usar
    igual para firmar un documento real, así que valida lo mismo.
    """
    _crear_caf(
        contribuyente,
        tipo_factura,
        fecha_vencimiento=timezone.localdate() - timedelta(days=1),
    )

    with pytest.raises(CafVencidoError):
        caf_manager.reserve_folio(contribuyente, tipo_factura, 1)


def test_reserve_folio_succeeds_when_the_covering_caf_is_vigente(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    _crear_caf(
        contribuyente,
        tipo_factura,
        fecha_vencimiento=timezone.localdate() + timedelta(days=1),
    )

    caf_xml = caf_manager.reserve_folio(contribuyente, tipo_factura, 1)

    assert caf_xml == '<AUTORIZACION/>'


def test_reserve_next_folio_raises_without_any_caf(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    with pytest.raises(NoFolioDisponibleError):
        caf_manager.reserve_next_folio(contribuyente, tipo_factura)
