"""
Tests para `services.purchases_reporter` — `periodos()`/
`resumen_periodo()`/`documentos_periodo()`.

`documentos_periodo()` es el caso más delicado del módulo: mezcla
`DteEmitido` (Factura de Compra) y `DteRecibido` en una sola lista
ordenada, con `contraparte`/`estado` normalizados desde dos modelos
distintos.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.billing.models import (
    DteEmitido,
    DteRecibido,
    Emisor,
    Receptor,
    TipoDte,
)
from apps.billing.services.purchases_reporter import (
    documentos_periodo,
    periodos,
    resumen_periodo,
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
def tipo_factura_compra() -> TipoDte:
    return TipoDte.objects.create(
        codigo=46,
        glosa='Factura de Compra Electrónica',
        operacion=TipoDte.Operacion.SUMA,
        compra=True,
    )


@pytest.fixture
def tipo_nota_credito_compra() -> TipoDte:
    return TipoDte.objects.create(
        codigo=61,
        glosa='Nota de Crédito Electrónica',
        operacion=TipoDte.Operacion.RESTA,
        compra=True,
    )


@pytest.fixture
def tipo_factura_recibida() -> TipoDte:
    return TipoDte.objects.create(
        codigo=33,
        glosa='Factura Electrónica',
        operacion=TipoDte.Operacion.SUMA,
        venta=True,
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


def _create_emitido(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    receptor: Receptor,
    folio: int,
    periodo: int,
    total: int,
    fecha: str | None = None,
    revision_estado: str = '',
) -> DteEmitido:
    return DteEmitido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        receptor=receptor,
        usuario=contribuyente.usuario,
        folio=folio,
        periodo=periodo,
        fecha=fecha or f'{periodo // 100}-{periodo % 100:02d}-05',
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
    fecha: str | None = None,
) -> DteRecibido:
    return DteRecibido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        emisor=emisor,
        usuario=contribuyente.usuario,
        folio=folio,
        periodo=periodo,
        fecha=fecha or f'{periodo // 100}-{periodo % 100:02d}-05',
        total=total,
        xml_base64='',
    )


def test_periodos_suma_emitidos_de_compra_y_recibidos_juntos(
    contribuyente: Contribuyente,
    tipo_factura_compra: TipoDte,
    tipo_factura_recibida: TipoDte,
    receptor: Receptor,
    emisor: Emisor,
) -> None:
    _create_emitido(
        contribuyente, tipo_factura_compra, receptor, 1, 202609, total=5_000
    )
    _create_recibido(
        contribuyente, tipo_factura_recibida, emisor, 1, 202609, total=3_000
    )

    resultado = periodos(contribuyente)

    assert len(resultado) == 1
    assert resultado[0].documentos == 2
    assert resultado[0].total == 8_000


def test_resumen_periodo_es_none_sin_documentos_de_compra(
    contribuyente: Contribuyente,
) -> None:
    assert resumen_periodo(contribuyente, 202609) is None


def test_resumen_periodo_aplica_signo_a_una_nota_de_credito(
    contribuyente: Contribuyente,
    tipo_factura_compra: TipoDte,
    tipo_nota_credito_compra: TipoDte,
    receptor: Receptor,
) -> None:
    _create_emitido(
        contribuyente, tipo_factura_compra, receptor, 1, 202609, total=10_000
    )
    _create_emitido(
        contribuyente,
        tipo_nota_credito_compra,
        receptor,
        2,
        202609,
        total=1_000,
    )

    resumen = resumen_periodo(contribuyente, 202609)

    assert resumen is not None
    assert resumen.documentos == 2
    assert resumen.total == 10_000 - 1_000


def test_documentos_periodo_mezcla_emitidos_y_recibidos_ordenado_por_fecha(
    contribuyente: Contribuyente,
    tipo_factura_compra: TipoDte,
    tipo_factura_recibida: TipoDte,
    receptor: Receptor,
    emisor: Emisor,
) -> None:
    _create_emitido(
        contribuyente,
        tipo_factura_compra,
        receptor,
        1,
        202609,
        total=5_000,
        fecha='2026-09-05',
    )
    _create_recibido(
        contribuyente,
        tipo_factura_recibida,
        emisor,
        1,
        202609,
        total=3_000,
        fecha='2026-09-10',
    )

    documentos = documentos_periodo(contribuyente, 202609)

    assert [doc.origen for doc in documentos] == ['recibido', 'emitido']
    assert documentos[0].contraparte == 'Proveedor de prueba'
    assert documentos[1].contraparte == 'Cliente de prueba'


def test_documentos_periodo_usa_rut_dv_si_no_hay_razon_social(
    contribuyente: Contribuyente,
    tipo_factura_recibida: TipoDte,
) -> None:
    emisor_sin_nombre = Emisor.objects.create(
        contribuyente=contribuyente,
        rut=76111222,
        dv='6',
    )
    _create_recibido(
        contribuyente, tipo_factura_recibida, emisor_sin_nombre, 1, 202609, 1
    )

    documentos = documentos_periodo(contribuyente, 202609)

    assert documentos[0].contraparte == '76111222-6'


def test_documentos_periodo_estado_por_defecto(
    contribuyente: Contribuyente,
    tipo_factura_compra: TipoDte,
    tipo_factura_recibida: TipoDte,
    receptor: Receptor,
    emisor: Emisor,
) -> None:
    """Sin `revision_estado`/eventos RCV, ambos orígenes caen a `'—'`."""
    _create_emitido(
        contribuyente, tipo_factura_compra, receptor, 1, 202609, total=5_000
    )
    _create_recibido(
        contribuyente, tipo_factura_recibida, emisor, 1, 202609, total=3_000
    )

    documentos = documentos_periodo(contribuyente, 202609)

    assert all(doc.estado == '—' for doc in documentos)
