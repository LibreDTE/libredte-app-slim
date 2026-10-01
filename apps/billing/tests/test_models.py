"""Tests para los modelos de `billing` (constraints, sobre todo)."""

from __future__ import annotations

from datetime import date
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models import ProtectedError
from libredte_lib_sdk.billing.enums import SiiEnvironment

from apps.billing.models import (
    Caf,
    CafFolio,
    DteEmitido,
    DteEmitidoReferencia,
    Item,
    ItemCategoria,
    Receptor,
    TipoDte,
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
def pais_extranjero() -> Pais:
    return Pais.objects.create(codigo=105, glosa='Argentina')


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


@pytest.fixture
def receptor(contribuyente: Contribuyente) -> Receptor:
    return Receptor.objects.create(contribuyente=contribuyente, rut=1, dv='9')


def test_item_categoria_is_unique_per_contribuyente_and_nombre(
    contribuyente: Contribuyente,
) -> None:
    ItemCategoria.objects.create(
        contribuyente=contribuyente,
        nombre='Software',
    )

    with pytest.raises(IntegrityError):
        ItemCategoria.objects.create(
            contribuyente=contribuyente,
            nombre='Software',
        )


def test_item_is_unique_per_contribuyente_tipo_y_codigo(
    contribuyente: Contribuyente,
) -> None:
    Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-001',
        nombre='Licencia software',
        precio=50000,
    )

    with pytest.raises(IntegrityError):
        Item.objects.create(
            contribuyente=contribuyente,
            codigo='SW-001',
            nombre='Otro nombre',
            precio=1000,
        )


def test_item_categoria_is_optional(contribuyente: Contribuyente) -> None:
    """Un ítem se puede cargar sin categoría."""
    item = Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-002',
        nombre='Licencia software',
        precio=50000,
    )

    assert item.categoria is None


def test_item_precio_neto_returns_precio_as_is_when_not_bruto(
    contribuyente: Contribuyente,
) -> None:
    item = Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-003',
        nombre='Licencia software',
        precio=50000,
    )

    assert item.precio_neto == 50000


def test_item_precio_neto_strips_iva_when_bruto(
    contribuyente: Contribuyente,
) -> None:
    item = Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-004',
        nombre='Licencia software',
        precio=119000,
        bruto=True,
    )

    assert item.precio_neto == 100000


def test_item_precio_neto_ignores_bruto_when_exento(
    contribuyente: Contribuyente,
) -> None:
    """Un ítem exento no tiene IVA que quitar — bruto y neto son iguales."""
    item = Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-005',
        nombre='Servicio exento',
        precio=100000,
        bruto=True,
        indicador_exencion=Item.IndicadorExencion.NO_AFECTO,
    )

    assert item.precio_neto == 100000


def test_item_descuento_neto_ignores_bruto_when_percentage(
    contribuyente: Contribuyente,
) -> None:
    """Un descuento en `%` no cambia con `bruto` — solo el de `$`."""
    item = Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-006',
        nombre='Licencia software',
        precio=119000,
        bruto=True,
        descuento=10,
        descuento_tipo=Item.DescuentoTipo.PORCENTAJE,
    )

    assert item.descuento_neto == 10


def test_item_descuento_neto_strips_iva_when_monto_and_bruto(
    contribuyente: Contribuyente,
) -> None:
    item = Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-007',
        nombre='Licencia software',
        precio=119000,
        bruto=True,
        descuento=11900,
        descuento_tipo=Item.DescuentoTipo.MONTO,
    )

    assert item.descuento_neto == 10000


def test_item_categoria_cannot_be_deleted_while_in_use(
    contribuyente: Contribuyente,
) -> None:
    categoria = ItemCategoria.objects.create(
        contribuyente=contribuyente,
        nombre='Software',
    )
    Item.objects.create(
        contribuyente=contribuyente,
        codigo='SW-001',
        nombre='Licencia software',
        precio=50000,
        categoria=categoria,
    )

    with pytest.raises(ProtectedError):
        categoria.delete()


def test_receptor_only_requires_rut_and_dv(
    contribuyente: Contribuyente,
) -> None:
    """Todo en `Receptor` es opcional salvo `rut`/`dv`."""
    receptor = Receptor.objects.create(
        contribuyente=contribuyente,
        rut=1,
        dv='9',
    )

    assert receptor.pk is not None
    assert receptor.razon_social == ''
    assert receptor.comuna is None


def test_receptor_auto_assigns_codigo_interno_from_rut_and_dv(
    contribuyente: Contribuyente,
) -> None:
    receptor = Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
    )

    assert receptor.codigo_interno == '0123456785'


def test_receptor_honors_an_explicit_codigo_interno(
    contribuyente: Contribuyente,
) -> None:
    receptor = Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        codigo_interno='CLI-001',
    )

    assert receptor.codigo_interno == 'CLI-001'


def test_receptor_allows_multiple_without_explicit_codigo_interno(
    contribuyente: Contribuyente,
) -> None:
    """Al derivarse de RUT+DV, dos RUT distintos no chocan entre sí."""
    Receptor.objects.create(contribuyente=contribuyente, rut=1, dv='9')
    Receptor.objects.create(contribuyente=contribuyente, rut=2, dv='7')

    assert Receptor.objects.filter(contribuyente=contribuyente).count() == 2


def test_receptor_same_rut_without_explicit_codigo_interno_collides(
    contribuyente: Contribuyente,
) -> None:
    """Mismo RUT+DV sin código explícito deriva el mismo código: choca."""
    Receptor.objects.create(contribuyente=contribuyente, rut=1, dv='9')

    with pytest.raises(IntegrityError):
        Receptor.objects.create(contribuyente=contribuyente, rut=1, dv='9')


def test_receptor_codigo_interno_is_unique_per_contribuyente(
    contribuyente: Contribuyente,
    comuna: Comuna,
) -> None:
    kwargs = {
        'contribuyente': contribuyente,
        'rut': 12345678,
        'dv': '5',
        'codigo_interno': 'CLI-001',
        'razon_social': 'Cliente',
        'giro': 'Comercio',
        'correo': 'cliente@example.com',
        'direccion': 'Dirección',
        'comuna': comuna,
    }
    Receptor.objects.create(**kwargs)

    with pytest.raises(IntegrityError):
        Receptor.objects.create(**{**kwargs, 'rut': 99999999, 'dv': '1'})


def test_receptor_extranjero_uses_ciudad_and_pais_instead_of_comuna(
    contribuyente: Contribuyente,
    pais_extranjero: Pais,
) -> None:
    receptor = Receptor.objects.create(
        contribuyente=contribuyente,
        rut=55555555,
        dv='5',
        codigo_interno='PASSPORT-123',
        razon_social='Cliente Extranjero',
        ciudad='Buenos Aires',
        pais=pais_extranjero,
    )

    assert receptor.comuna is None
    assert receptor.ciudad == 'Buenos Aires'
    assert receptor.pais == pais_extranjero


def test_dte_emitido_folio_is_unique_per_contribuyente_and_tipo(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    receptor: Receptor,
    usuario: User,
) -> None:
    kwargs = {
        'contribuyente': contribuyente,
        'tipo_dte': tipo_factura,
        'receptor': receptor,
        'usuario': usuario,
        'folio': 1,
        'periodo': 202608,
        'fecha': '2026-08-27',
        'neto': 1000,
        'exento': 0,
        'iva': 190,
        'total': 1190,
        'xml_base64': '<DTE/>',
    }
    DteEmitido.objects.create(**kwargs)

    with pytest.raises(IntegrityError):
        DteEmitido.objects.create(**kwargs)


def test_caf_folio_is_unique_per_contribuyente_and_tipo_dte(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    kwargs = {
        'contribuyente': contribuyente,
        'tipo_dte': tipo_factura,
        'siguiente': 1,
        'disponibles': 100,
        'alerta': 10,
    }
    CafFolio.objects.create(**kwargs)

    with pytest.raises(IntegrityError):
        CafFolio.objects.create(**kwargs)


def test_caf_is_unique_per_contribuyente_tipo_dte_and_desde(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    kwargs = {
        'contribuyente': contribuyente,
        'tipo_dte': tipo_factura,
        'desde': 1,
        'hasta': 100,
        'xml_base64': '<AUTORIZACION/>',
        'fecha_autorizacion': date(2026, 1, 1),
        'idk': 300,
    }
    Caf.objects.create(**kwargs)

    with pytest.raises(IntegrityError):
        Caf.objects.create(**kwargs)


def test_caf_codigo_matches_caf_getid_format(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """Mismo formato que `Caf::getId()` en libredte-lib-core."""
    caf = Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        desde=1,
        hasta=100,
        xml_base64='<AUTORIZACION/>',
        fecha_autorizacion=date(2026, 1, 1),
        idk=300,
    )

    assert caf.codigo == 'CAF33D1H100'


def test_caf_vigente_is_true_without_a_fecha_vencimiento(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """Sin `fecha_vencimiento` (tipo que no vence), siempre vigente."""
    caf = Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        desde=1,
        hasta=100,
        xml_base64='<AUTORIZACION/>',
        fecha_autorizacion=date(2020, 1, 1),
        idk=300,
    )

    assert caf.vigente is True


def test_caf_vigente_compares_fecha_vencimiento_against_today(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    caf_vencido = Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        desde=1,
        hasta=100,
        xml_base64='<AUTORIZACION/>',
        fecha_autorizacion=date(2020, 1, 1),
        fecha_vencimiento=date(2020, 6, 30),
        idk=300,
    )
    caf_vigente = Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        desde=101,
        hasta=200,
        xml_base64='<AUTORIZACION/>',
        fecha_autorizacion=date(2020, 1, 1),
        fecha_vencimiento=date(2999, 1, 1),
        idk=300,
    )

    assert caf_vencido.vigente is False
    assert caf_vigente.vigente is True


def test_caf_meses_autorizacion_uses_calendar_months_not_fixed_30_days(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """
    Igual que `Caf::getMesesAutorizacion()` en libredte-lib-core: meses
    de calendario, no bloques fijos de 30 días — de 2026-01-15 a
    2026-03-20 son 2 meses y 5 días (2 + round(5/30, 2) = 2.17), no un
    cálculo por bloques fijos de 30 días.
    """
    caf = Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        desde=1,
        hasta=100,
        xml_base64='<AUTORIZACION/>',
        fecha_autorizacion=date(2026, 1, 15),
        idk=300,
    )

    with mock.patch(
        'apps.billing.models.timezone.localdate',
        return_value=date(2026, 3, 20),
    ):
        assert caf.meses_autorizacion == 2.17


def test_caf_ambiente_and_certificacion_are_none_for_a_fake_idk(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """`CafFaker::IDK` (666) en libredte-lib-core no es un ambiente real."""
    caf = Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        desde=1,
        hasta=100,
        xml_base64='<AUTORIZACION/>',
        fecha_autorizacion=date(2026, 1, 1),
        idk=666,
    )

    assert caf.ambiente is None
    assert caf.certificacion is None


def test_caf_ambiente_and_certificacion_resolve_from_a_real_idk(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    produccion = Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        desde=1,
        hasta=100,
        xml_base64='<AUTORIZACION/>',
        fecha_autorizacion=date(2026, 1, 1),
        idk=300,
    )
    certificacion = Caf.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        desde=101,
        hasta=200,
        xml_base64='<AUTORIZACION/>',
        fecha_autorizacion=date(2026, 1, 1),
        idk=100,
    )

    assert produccion.ambiente is SiiEnvironment.PRODUCTION
    assert produccion.certificacion == 0
    assert certificacion.ambiente is SiiEnvironment.CERTIFICATION
    assert certificacion.certificacion == 1


@pytest.fixture
def tipo_compra() -> TipoDte:
    """Solo participa del libro de compras (ej. Factura de Compra, 46)."""
    return TipoDte.objects.create(
        codigo=46,
        glosa='Factura de Compra Electrónica',
        compra=True,
        venta=False,
    )


@pytest.fixture
def tipo_venta() -> TipoDte:
    """Solo participa del libro de ventas (ej. Boleta, 39)."""
    return TipoDte.objects.create(
        codigo=39,
        glosa='Boleta Electrónica',
        compra=False,
        venta=True,
    )


@pytest.fixture
def tipo_nota_credito() -> TipoDte:
    """Ambiguo: puede anular tanto una venta como una compra (ej. NC, 61)."""
    return TipoDte.objects.create(
        codigo=61,
        glosa='Nota de Crédito Electrónica',
        compra=True,
        venta=True,
    )


def _crear_dte(
    contribuyente: Contribuyente,
    tipo_dte: TipoDte,
    receptor: Receptor,
    usuario: User,
    folio: int,
) -> DteEmitido:
    return DteEmitido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
        receptor=receptor,
        usuario=usuario,
        folio=folio,
        periodo=202609,
        fecha='2026-09-05',
        iva=0,
        total=1000,
        xml_base64='<DTE/>',
    )


def test_libro_de_tipo_solo_compra_es_compras(
    contribuyente: Contribuyente,
    tipo_compra: TipoDte,
    receptor: Receptor,
    usuario: User,
) -> None:
    dte = _crear_dte(contribuyente, tipo_compra, receptor, usuario, folio=1)
    assert dte.libro() == 'compras'


def test_libro_de_tipo_solo_venta_es_ventas(
    contribuyente: Contribuyente,
    tipo_venta: TipoDte,
    receptor: Receptor,
    usuario: User,
) -> None:
    dte = _crear_dte(contribuyente, tipo_venta, receptor, usuario, folio=1)
    assert dte.libro() == 'ventas'


def test_libro_de_tipo_ambiguo_sin_referencias_es_ventas_por_defecto(
    contribuyente: Contribuyente,
    tipo_nota_credito: TipoDte,
    receptor: Receptor,
    usuario: User,
) -> None:
    nc = _crear_dte(
        contribuyente,
        tipo_nota_credito,
        receptor,
        usuario,
        folio=1,
    )
    assert nc.libro() == 'ventas'


def test_libro_de_tipo_ambiguo_que_referencia_una_compra_es_compras(
    contribuyente: Contribuyente,
    tipo_compra: TipoDte,
    tipo_nota_credito: TipoDte,
    receptor: Receptor,
    usuario: User,
) -> None:
    """Una NC que anula una Factura de Compra hereda el libro de compras."""
    factura_compra = _crear_dte(
        contribuyente,
        tipo_compra,
        receptor,
        usuario,
        folio=1,
    )
    nc = _crear_dte(
        contribuyente,
        tipo_nota_credito,
        receptor,
        usuario,
        folio=2,
    )
    DteEmitidoReferencia.objects.create(emitido=nc, referencia=factura_compra)

    assert nc.libro() == 'compras'


def test_libro_de_tipo_ambiguo_hereda_compras_transitivamente(
    contribuyente: Contribuyente,
    tipo_compra: TipoDte,
    tipo_nota_credito: TipoDte,
    receptor: Receptor,
    usuario: User,
) -> None:
    """Una ND que anula una NC que a su vez anula una Factura de Compra
    también es de compras — la recursión no se detiene en el primer salto."""
    factura_compra = _crear_dte(
        contribuyente,
        tipo_compra,
        receptor,
        usuario,
        folio=1,
    )
    nc = _crear_dte(
        contribuyente,
        tipo_nota_credito,
        receptor,
        usuario,
        folio=2,
    )
    DteEmitidoReferencia.objects.create(emitido=nc, referencia=factura_compra)

    nd = _crear_dte(
        contribuyente,
        tipo_nota_credito,
        receptor,
        usuario,
        folio=3,
    )
    DteEmitidoReferencia.objects.create(emitido=nd, referencia=nc)

    assert nd.libro() == 'compras'
