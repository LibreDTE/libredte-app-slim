"""Tests para `apps.billing.services.dashboard_reporter`."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpRequest
from django.test import RequestFactory
from django.utils import timezone

from apps.billing.models import (
    CafFolio,
    DteEmitido,
    DteRecibido,
    DteRecibidoRcvEvento,
    Emisor,
    Receptor,
    TipoDte,
)
from apps.billing.services.dashboard_reporter import get_dashboard_stats
from apps.billing.utils.period import adjacent_period, current_period
from apps.libredte import tenancy
from apps.libredte.models import Comuna, Contribuyente, Pais

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def chile() -> Pais:
    """`Receptor.save()` necesita a Chile disponible (país por defecto)."""
    return Pais.objects.create(codigo=Pais.CHILE, glosa='Chile')


@pytest.fixture
def comuna() -> Comuna:
    return Comuna.objects.create(codigo='SANTIAGO', glosa='SANTIAGO')


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
    return TipoDte.objects.create(
        codigo=33,
        glosa='Factura Electrónica',
        operacion=TipoDte.Operacion.SUMA,
        venta=True,
    )


@pytest.fixture
def tipo_nota_credito() -> TipoDte:
    return TipoDte.objects.create(
        codigo=61,
        glosa='Nota de Crédito Electrónica',
        operacion=TipoDte.Operacion.RESTA,
        venta=True,
    )


@pytest.fixture
def tipo_factura_exportacion() -> TipoDte:
    return TipoDte.objects.create(
        codigo=110,
        glosa='Factura de Exportación Electrónica',
        operacion=TipoDte.Operacion.SUMA,
        venta=True,
    )


@pytest.fixture
def tipo_factura_compra() -> TipoDte:
    return TipoDte.objects.create(
        codigo=46,
        glosa='Factura de Compra Electrónica',
        operacion=TipoDte.Operacion.SUMA,
        compra=True,
    )


@pytest.fixture
def receptor(contribuyente: Contribuyente) -> Receptor:
    return Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        razon_social='Cliente de prueba',
    )


@pytest.fixture
def emisor(contribuyente: Contribuyente) -> Emisor:
    return Emisor.objects.create(
        contribuyente=contribuyente,
        rut=76111222,
        dv='6',
        razon_social='Proveedor de prueba',
    )


@pytest.fixture
def request_factory(contribuyente: Contribuyente) -> HttpRequest:
    """
    `HttpRequest` con `contribuyente` activo en sesión.

    `RequestFactory` no pasa por el middleware real — sin esto,
    `get_current_contribuyente()` no tendría ni `request.user` ni
    `request.session` disponibles.
    """
    request = RequestFactory().get('/dashboard/')
    request.user = contribuyente.usuario
    request.session = SessionStore()
    request.session[tenancy._SESSION_KEY] = contribuyente.pk
    request.session.save()
    return request


def _create_documento(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    receptor: Receptor,
    folio: int,
    periodo: int,
    total: int,
    iva: int = 0,
    revision_estado: str = '',
) -> DteEmitido:
    return DteEmitido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        receptor=receptor,
        usuario=contribuyente.usuario,
        folio=folio,
        periodo=periodo,
        fecha=f'{periodo // 100}-{periodo % 100:02d}-05',
        iva=iva,
        total=total,
        xml_base64='',
        revision_estado=revision_estado,
    )


def _create_recibido(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    emisor: Emisor,
    folio: int,
    periodo: int,
    total: int,
    iva: int = 0,
    fecha_registro_rcv: datetime | None = None,
) -> DteRecibido:
    return DteRecibido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        emisor=emisor,
        usuario=contribuyente.usuario,
        folio=folio,
        periodo=periodo,
        fecha=f'{periodo // 100}-{periodo % 100:02d}-05',
        iva=iva,
        total=total,
        xml_base64='',
        fecha_registro_rcv=fecha_registro_rcv,
    )


def test_stats_defaults_to_the_current_period(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
) -> None:
    stats = get_dashboard_stats(request_factory)

    assert stats.periodo == current_period()
    assert stats.periodo_siguiente is None


def test_stats_for_a_past_period_allows_navigating_forward(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
) -> None:
    periodo_pasado = adjacent_period(current_period(), -2)

    stats = get_dashboard_stats(request_factory, periodo=periodo_pasado)

    assert stats.periodo == periodo_pasado
    assert stats.periodo_siguiente == adjacent_period(periodo_pasado, 1)


def test_nota_de_credito_subtracts_from_the_period_totals(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    tipo_nota_credito: TipoDte,
    receptor: Receptor,
) -> None:
    periodo = current_period()
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        1,
        periodo,
        total=10_000,
        iva=1_900,
    )
    _create_documento(
        contribuyente,
        tipo_nota_credito,
        receptor,
        1,
        periodo,
        total=4_000,
        iva=760,
    )

    stats = get_dashboard_stats(request_factory, periodo=periodo)

    assert stats.documentos == 2
    assert stats.total_neto == 10_000 - 4_000
    assert stats.iva_neto == 1_900 - 760


def test_export_documents_are_included_in_money_totals(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    tipo_factura_exportacion: TipoDte,
    receptor: Receptor,
) -> None:
    periodo = current_period()
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        1,
        periodo,
        total=10_000,
        iva=1_900,
    )
    _create_documento(
        contribuyente,
        tipo_factura_exportacion,
        receptor,
        1,
        periodo,
        total=100,
        iva=0,
    )

    stats = get_dashboard_stats(request_factory, periodo=periodo)

    # `DteEmitido.total` siempre está en pesos chilenos (ver
    # `utils.dte.montos_en_clp()`), así que un documento de exportación
    # suma junto al resto sin caso especial.
    assert stats.documentos == 2
    assert stats.total_neto == 10_100


def test_rechazado_is_not_counted_as_con_reparos(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    receptor: Receptor,
) -> None:
    periodo = current_period()
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        1,
        periodo,
        total=1_000,
        revision_estado='RLV - DTE Aceptado con Reparos Leves',
    )
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        2,
        periodo,
        total=1_000,
        revision_estado='RFR - Rechazado por Error en Firma',
    )

    stats = get_dashboard_stats(request_factory, periodo=periodo)

    assert stats.con_reparos == 1
    assert stats.rechazados == 1
    assert stats.rechazados_pendientes == 1


def test_folios_por_tipo_are_not_scoped_to_the_period(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    CafFolio.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        siguiente=1,
        disponibles=50,
        alerta=10,
    )

    stats_actual = get_dashboard_stats(request_factory)
    stats_pasado = get_dashboard_stats(
        request_factory,
        periodo=adjacent_period(current_period(), -3),
    )

    assert len(stats_actual.folios_por_tipo) == 1
    assert stats_actual.folios_por_tipo == stats_pasado.folios_por_tipo


def test_factura_de_compra_is_excluded_from_ventas_but_counted_as_compra(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    tipo_factura_compra: TipoDte,
    receptor: Receptor,
) -> None:
    periodo = current_period()
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        1,
        periodo,
        total=10_000,
        iva=1_900,
    )
    _create_documento(
        contribuyente,
        tipo_factura_compra,
        receptor,
        1,
        periodo,
        total=5_000,
        iva=950,
    )

    stats = get_dashboard_stats(request_factory, periodo=periodo)

    # Una Factura de Compra no es una venta (`DteEmitido.libro()`) —
    # antes de filtrar por eso, se sumaba igual acá.
    assert stats.documentos == 1
    assert stats.total_neto == 10_000
    # Pero sí es una compra (`services/purchases_reporter.py`).
    assert stats.compras_documentos == 1
    assert stats.compras_total == 5_000
    assert stats.margen_operativo == 10_000 - 5_000


def test_ventas_variacion_pct_compares_against_previous_period(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    receptor: Receptor,
) -> None:
    periodo = current_period()
    periodo_anterior = adjacent_period(periodo, -1)
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        1,
        periodo_anterior,
        total=10_000,
    )
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        2,
        periodo,
        total=15_000,
    )

    stats = get_dashboard_stats(request_factory, periodo=periodo)

    assert stats.ventas_variacion_pct == 50.0


def test_ventas_variacion_pct_is_none_without_a_previous_period(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    receptor: Receptor,
) -> None:
    periodo = current_period()
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        1,
        periodo,
        total=10_000,
    )

    stats = get_dashboard_stats(request_factory, periodo=periodo)

    assert stats.ventas_variacion_pct is None


def test_concentracion_pct_reflects_the_share_of_the_top_receptor(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    periodo = current_period()
    receptor_a = Receptor.objects.create(
        contribuyente=contribuyente,
        rut=22222222,
        dv='2',
        razon_social='Cliente A',
    )
    receptor_b = Receptor.objects.create(
        contribuyente=contribuyente,
        rut=33333333,
        dv='3',
        razon_social='Cliente B',
    )
    _create_documento(
        contribuyente, tipo_factura, receptor_a, 1, periodo, total=8_000
    )
    _create_documento(
        contribuyente, tipo_factura, receptor_b, 2, periodo, total=2_000
    )

    stats = get_dashboard_stats(request_factory, periodo=periodo)

    assert stats.concentracion_top1_pct == 80.0
    assert stats.concentracion_top3_pct == 100.0


def test_recibidos_pendientes_and_por_vencer_rcv(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura_compra: TipoDte,
    emisor: Emisor,
) -> None:
    ahora = timezone.now()
    # Pendiente, recién registrado — no por vencer todavía.
    _create_recibido(
        contribuyente,
        tipo_factura_compra,
        emisor,
        1,
        current_period(),
        total=1_000,
        fecha_registro_rcv=ahora - timedelta(days=1),
    )
    # Pendiente, y ya pasaron 5+ días — por vencer.
    _create_recibido(
        contribuyente,
        tipo_factura_compra,
        emisor,
        2,
        current_period(),
        total=1_000,
        fecha_registro_rcv=ahora - timedelta(days=6),
    )

    stats = get_dashboard_stats(request_factory)

    assert stats.recibidos_pendientes_rcv == 2
    assert stats.recibidos_por_vencer_rcv == 1


def test_recibidos_rechazados_rcv(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura_compra: TipoDte,
    emisor: Emisor,
) -> None:
    recibido = _create_recibido(
        contribuyente,
        tipo_factura_compra,
        emisor,
        1,
        current_period(),
        total=1_000,
        fecha_registro_rcv=timezone.now() - timedelta(days=1),
    )
    DteRecibidoRcvEvento.objects.create(
        dte_recibido=recibido,
        codigo=DteRecibidoRcvEvento.Codigo.RCD,
        responsable='11111111-1',
        fecha=timezone.now(),
    )

    stats = get_dashboard_stats(request_factory)

    assert stats.recibidos_rechazados_rcv == 1
    assert stats.recibidos_pendientes_rcv == 0


def test_emitidos_sin_enviar_is_not_scoped_to_the_period(
    request_factory: HttpRequest,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    receptor: Receptor,
) -> None:
    periodo_pasado = adjacent_period(current_period(), -5)
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        1,
        periodo_pasado,
        total=1_000,
    )

    stats = get_dashboard_stats(request_factory)

    assert stats.emitidos_sin_enviar == 1
