"""
Test de la emisión masiva contra la API real.

El resto de la suite (`test_bulk_biller.py`) mockea el SDK y `biller`, así
que nunca prueba que la biblioteca parsee de verdad las planillas ni que
la API acepte los documentos que salen de ellas. Esto cubre justamente eso,
con las dos planillas de ejemplo del proyecto (`apps/billing/files/`, las
mismas de los tests de Core y Pro).

Los documentos de exportación de las planillas de ejemplo traen moneda
extranjera y la planilla no trae tipo de cambio, así que fallan al armar el
borrador: aquí se emiten solo los demás.

Marcado `live` y excluido de `pytest`/`make check` por defecto (ver
`pyproject.toml`), igual que el resto de lo que golpea la API real.
Correr con `make test-live` (requiere `PLUGIN_LIBREDTE_BACKEND_API_URL`
apuntando a un servidor real).

Solo borradores (`dte_real=False`): no hace falta CAF ni certificado, y
no consume folios.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command

from apps.billing.models import Borrador
from apps.billing.services import bulk_biller
from apps.libredte.models import (
    ActividadEconomica,
    Comuna,
    Contribuyente,
    ContribuyenteActividadEconomica,
)

pytestmark = [pytest.mark.django_db, pytest.mark.live]


@pytest.fixture
def contribuyente() -> Contribuyente:
    """Emisor mínimo que la API acepta, con catálogos cargados."""
    call_command('seed')

    contribuyente = Contribuyente.objects.create(
        usuario=User.objects.create_user(
            'demo', email='demo@example.com', password='demo12345'
        ),
        rut=76192083,
        dv='9',
        razon_social='SASCO SpA',
        giro='Servicios informáticos',
        direccion='Av. Siempre Viva 123',
        # `iexact`: el catálogo del SII trae las comunas en mayúsculas
        # (`SANTIAGO`), pero el nombre se escribe como se lee.
        comuna=Comuna.objects.get(glosa__iexact='Santiago'),
        autorizacion_dte_resolucion_fecha='2014-08-22',
        autorizacion_dte_resolucion_numero=0,
    )
    # `Acteco` es uno de los datos mínimos del emisor, y sale de la
    # actividad principal (ver `biller._emisor_payload()`).
    actividad = ActividadEconomica.objects.first()
    assert actividad is not None, 'El seed no cargó actividades económicas.'
    ContribuyenteActividadEconomica.objects.create(
        contribuyente=contribuyente,
        actividad_economica=actividad,
        es_principal=True,
    )
    return contribuyente


_EJEMPLOS = Path(bulk_biller.__file__).resolve().parent.parent / 'files'

# Exportación: la planilla no trae tipo de cambio (nodo `OtraMoneda`).
_EXPORTACION = (110, 111, 112)


def _parsear_ejemplo(contribuyente: Contribuyente, extension: str) -> Any:
    """Los documentos de la planilla de ejemplo, parseados por la API."""
    archivo = (_EJEMPLOS / f'emision_masiva.{extension}').read_bytes()
    return bulk_biller.parse(contribuyente, archivo, extension)


@pytest.mark.parametrize('extension', ['csv', 'xlsx'])
def test_la_biblioteca_parsea_las_planillas_de_ejemplo(
    contribuyente: Contribuyente,
    extension: str,
) -> None:
    documentos = _parsear_ejemplo(contribuyente, extension)

    assert len(documentos) == 63
    assert {d['Encabezado']['IdDoc']['TipoDTE'] for d in documentos} == {
        33, 34, 39, 41, 46, 52, 56, 61, 110, 111, 112,
    }  # fmt: skip


def test_la_api_acepta_los_documentos_de_la_planilla(
    contribuyente: Contribuyente,
) -> None:
    documentos = [
        documento
        for documento in _parsear_ejemplo(contribuyente, 'csv')
        if documento['Encabezado']['IdDoc']['TipoDTE'] not in _EXPORTACION
    ]

    resultados = bulk_biller.process(
        contribuyente,
        documentos,
        contribuyente.usuario,
        dte_real=False,
        pdf=False,
    ).resultados

    fallidos = [
        f'documento {resultado.numero}: [{resultado.codigo}] {resultado.glosa}'
        for resultado in resultados
        if not resultado.ok
    ]
    assert not fallidos, '\n'.join(fallidos)
    assert Borrador.objects.count() == len(resultados) == len(documentos)


def test_el_correo_lleva_el_resultado_y_los_pdf_reales(
    contribuyente: Contribuyente,
    settings: Any,
    tmp_path: Path,
) -> None:
    """
    Lo que los tests offline no pueden probar: que la API renderice el
    PDF de cada borrador recién creado, y que el ZIP al que apunta el
    enlace del correo tenga contenido de verdad.
    """
    settings.EMISION_MASIVA_PDF_DIR = tmp_path
    documentos = _parsear_ejemplo(contribuyente, 'xlsx')[:2]

    bulk_biller.process(
        contribuyente,
        documentos,
        contribuyente.usuario,
        dte_real=False,
        pdf=True,
    )

    (mensaje,) = mail.outbox
    assert 'Documentos: 2 (0 con error)' in mensaje.body
    assert 'no se pudieron generar' not in mensaje.body
    # El ZIP no va adjunto: el correo lleva el enlace de descarga.
    encontrado = re.search(r'/emitir/masivo/pdf/([^/\s]+)/', str(mensaje.body))
    assert encontrado is not None, 'El correo no trae el enlace de los PDF'
    zip_encontrado = bulk_biller.find_pdf_zip(encontrado.group(1))
    assert zip_encontrado is not None, 'El enlace de los PDF no sirve'
    ruta, _ = zip_encontrado
    with zipfile.ZipFile(ruta) as zip_pdf:
        pdfs = [zip_pdf.read(nombre) for nombre in zip_pdf.namelist()]
    assert len(pdfs) == 2
    assert all(pdf.startswith(b'%PDF') for pdf in pdfs)
