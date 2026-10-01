"""
Tests para `services.biller._resolver_receptor()`/`_receptor_payload()`.

El resto de `biller.py` (`draft()`/`draft_from_form()`/`bill_draft()`)
llama a la API real de LibreDTE Lib — no se prueba acá (ver
`test_emitir.py`, que mockea `draft_from_form()` completo). Esto solo
prueba la resolución del `Receptor`, que es puramente local (el
cálculo de montos en CLP se prueba en `test_dte.py`).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.billing.models import Receptor
from apps.billing.services.biller import (
    _receptor_payload,
    _resolver_receptor,
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
def usuario() -> User:
    return User.objects.create_user('demo', password='demo12345')


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


def test_crea_un_receptor_nuevo_si_no_existe(
    contribuyente: Contribuyente,
) -> None:
    receptor = _resolver_receptor(
        contribuyente,
        {
            'RUTRecep': '12345678-5',
            'RznSocRecep': 'Cliente de prueba',
            'GiroRecep': 'Comercio',
        },
    )

    assert receptor.rut == 12345678
    assert receptor.dv == '5'
    assert receptor.razon_social == 'Cliente de prueba'
    assert receptor.giro == 'Comercio'


def test_actualiza_un_receptor_ya_existente_encontrado_por_rut(
    contribuyente: Contribuyente,
) -> None:
    """El receptor se mantiene al día con lo último usado para facturar."""
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        razon_social='Nombre antiguo',
        giro='Giro antiguo',
    )

    receptor = _resolver_receptor(
        contribuyente,
        {
            'RUTRecep': '12345678-5',
            'RznSocRecep': 'Nombre actualizado',
            'GiroRecep': 'Giro actualizado',
        },
    )

    assert Receptor.objects.filter(contribuyente=contribuyente).count() == 1
    assert receptor.razon_social == 'Nombre actualizado'
    assert receptor.giro == 'Giro actualizado'


def test_actualiza_un_receptor_encontrado_por_codigo_interno(
    contribuyente: Contribuyente,
) -> None:
    """`CdgIntRecep` tiene prioridad sobre el RUT para encontrarlo."""
    Receptor.objects.create(
        contribuyente=contribuyente,
        rut=12345678,
        dv='5',
        codigo_interno='amazon',
        razon_social='Nombre antiguo',
    )

    receptor = _resolver_receptor(
        contribuyente,
        {
            'RUTRecep': '99999999-9',
            'CdgIntRecep': 'amazon',
            'RznSocRecep': 'Amazon Inc.',
        },
    )

    assert Receptor.objects.filter(contribuyente=contribuyente).count() == 1
    assert receptor.razon_social == 'Amazon Inc.'
    # El RUT también se actualiza — el código interno manda por sobre
    # cualquier otro dato ya guardado, incluido el RUT.
    assert receptor.rut == 99999999
    assert receptor.dv == '9'


def test_resuelve_la_comuna_por_glosa(
    contribuyente: Contribuyente,
    comuna: Comuna,
) -> None:
    receptor = _resolver_receptor(
        contribuyente,
        {
            'RUTRecep': '12345678-5',
            'RznSocRecep': 'Cliente de prueba',
            'CmnaRecep': 'Santiago',
        },
    )

    assert receptor.comuna == comuna


@pytest.mark.parametrize(
    'receptor_data',
    [
        # Plano, como en `form.estandar` (`draft_from_form()`).
        {'RUTRecep': '55555555-5', 'NumId': 'US-123'},
        # Anidado, como en el formato del SII (`draft()`).
        {'RUTRecep': '55555555-5', 'Extranjero': {'NumId': 'US-123'}},
    ],
)
def test_guarda_el_numero_de_identificacion_en_cualquiera_de_las_dos_formas(
    contribuyente: Contribuyente,
    receptor_data: dict[str, object],
) -> None:
    receptor = _resolver_receptor(contribuyente, receptor_data)

    assert receptor.numero_identificacion == 'US-123'


def test_el_numero_de_identificacion_vuelve_al_documento(
    contribuyente: Contribuyente,
) -> None:
    """
    `draft()` reemplaza el receptor del documento por el guardado: sin
    esto, el `NumId` que traía el documento se perdería, aunque el
    receptor no tenga nacionalidad (una exportación cargada por
    planilla no trae esa columna).
    """
    receptor = _resolver_receptor(
        contribuyente,
        {'RUTRecep': '55555555-5', 'Extranjero': {'NumId': 'US-123'}},
    )

    assert _receptor_payload(receptor)['Extranjero'] == {'NumId': 'US-123'}
