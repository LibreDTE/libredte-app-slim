"""
Tests para `services.document_renderer._libredte_data()`/`_logo_data_uri()`.

`render_html()`/`render_pdf()` llaman a la API real de LibreDTE Lib —
no se prueban acá (mismo criterio que `test_biller.py`). Esto solo
prueba el armado del logo como `data:` URI, que es puramente local.
"""

from __future__ import annotations

import base64

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from apps.billing.models import (
    DteEmitido,
    DteRecibido,
    Emisor,
    Receptor,
    TipoDte,
)
from apps.billing.services.document_renderer import _libredte_data
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
def dte_emitido(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    receptor: Receptor,
) -> DteEmitido:
    return DteEmitido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        receptor=receptor,
        usuario=contribuyente.usuario,
        folio=1,
        periodo=202609,
        fecha='2026-09-05',
        total=11_900,
        xml_base64='',
    )


@pytest.fixture
def dte_recibido(
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    emisor: Emisor,
) -> DteRecibido:
    return DteRecibido.objects.create(
        contribuyente=contribuyente,
        tipo_dte=tipo_factura,
        emisor=emisor,
        usuario=contribuyente.usuario,
        folio=1,
        periodo=202609,
        fecha='2026-09-05',
        total=11_900,
        xml_base64='',
    )


def test_un_recibido_nunca_lleva_logo(dte_recibido: DteRecibido) -> None:
    """El emisor real de un recibido es un tercero, sin logo guardado."""
    assert _libredte_data(dte_recibido) is None


def test_un_emitido_sin_logo_no_lleva_data(dte_emitido: DteEmitido) -> None:
    assert _libredte_data(dte_emitido) is None


def test_un_emitido_con_logo_lleva_su_data_uri(
    contribuyente: Contribuyente,
    dte_emitido: DteEmitido,
) -> None:
    contenido = b'contenido-de-prueba-no-es-un-png-real'
    contribuyente.logo.save(
        'logo.png',
        ContentFile(contenido),
        save=True,
    )

    data = _libredte_data(dte_emitido)

    assert data is not None
    logo_uri = data['extra']['dte']['logo']
    assert logo_uri.startswith('data:image/png;base64,')
    codificado = logo_uri.removeprefix('data:image/png;base64,')
    assert base64.b64decode(codificado) == contenido
