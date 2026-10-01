"""Tests para `services.sales_reporter` — `periodos()`/`resumen_periodo()`."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.billing.models import DteEmitido, Receptor, TipoDte
from apps.billing.services.sales_reporter import periodos, resumen_periodo
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


def _create_documento(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    receptor: Receptor,
    folio: int,
    periodo: int,
    total: int,
    neto: int | None = None,
    exento: int | None = None,
    iva: int = 0,
) -> DteEmitido:
    return DteEmitido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        receptor=receptor,
        usuario=contribuyente.usuario,
        folio=folio,
        periodo=periodo,
        fecha=f'{periodo // 100}-{periodo % 100:02d}-05',
        neto=neto,
        exento=exento,
        iva=iva,
        total=total,
        xml_base64='',
    )


def test_periodos_agrupa_y_suma_por_periodo_con_signo(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    tipo_nota_credito: TipoDte,
    receptor: Receptor,
) -> None:
    _create_documento(
        contribuyente, tipo_factura, receptor, 1, 202609, total=10_000
    )
    _create_documento(
        contribuyente, tipo_factura, receptor, 2, 202609, total=5_000
    )
    _create_documento(
        contribuyente, tipo_nota_credito, receptor, 1, 202609, total=2_000
    )
    _create_documento(
        contribuyente, tipo_factura, receptor, 3, 202608, total=1_000
    )

    resultado = periodos(contribuyente)

    assert [p.periodo for p in resultado] == [202609, 202608]
    periodo_actual = resultado[0]
    assert periodo_actual.documentos == 3
    assert periodo_actual.total == 10_000 + 5_000 - 2_000


def test_periodos_excluye_facturas_de_compra(
    contribuyente: Contribuyente,
    tipo_factura_compra: TipoDte,
    receptor: Receptor,
) -> None:
    _create_documento(
        contribuyente, tipo_factura_compra, receptor, 1, 202609, total=5_000
    )

    assert periodos(contribuyente) == []


def test_resumen_periodo_es_none_sin_documentos_de_venta(
    contribuyente: Contribuyente,
) -> None:
    assert resumen_periodo(contribuyente, 202609) is None


def test_resumen_periodo_agrupa_por_tipo_y_aplica_signo_en_cada_campo(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    tipo_nota_credito: TipoDte,
    receptor: Receptor,
) -> None:
    _create_documento(
        contribuyente,
        tipo_factura,
        receptor,
        1,
        202609,
        total=11_900,
        neto=10_000,
        iva=1_900,
    )
    _create_documento(
        contribuyente,
        tipo_nota_credito,
        receptor,
        1,
        202609,
        total=2_380,
        neto=2_000,
        iva=380,
    )

    resumen = resumen_periodo(contribuyente, 202609)

    assert resumen is not None
    assert resumen.documentos == 2
    assert resumen.neto == 10_000 - 2_000
    assert resumen.iva == 1_900 - 380
    assert resumen.total == 11_900 - 2_380
    # Ordenado por código de tipo de documento (33 antes que 61).
    assert [fila.tipo_dte.codigo for fila in resumen.por_tipo] == [33, 61]


def test_resumen_periodo_trae_los_periodos_adyacentes(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    receptor: Receptor,
) -> None:
    _create_documento(
        contribuyente, tipo_factura, receptor, 1, 202609, total=10_000
    )

    resumen = resumen_periodo(contribuyente, 202609)

    assert resumen is not None
    assert resumen.periodo_anterior == 202608
    assert resumen.periodo_siguiente == 202610
