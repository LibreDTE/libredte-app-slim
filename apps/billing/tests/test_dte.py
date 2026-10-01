"""Tests para `utils.dte.montos_en_clp()`."""

from __future__ import annotations

import pytest

from apps.billing.utils.dte import montos_en_clp
from apps.libredte.services.exceptions import ServiceError


def test_montos_en_clp_usa_los_campos_planos_si_la_moneda_es_clp() -> None:
    neto, exento, iva, total = montos_en_clp(
        {
            'Totales': {
                'MntNeto': 10_000,
                'MntExe': 0,
                'IVA': 1_900,
                'MntTotal': 11_900,
            },
        },
    )

    assert (neto, exento, iva, total) == (10_000, 0, 1_900, 11_900)


def test_montos_en_clp_usa_otra_moneda_en_una_exportacion() -> None:
    """Una exportación viene en su propia moneda; CLP viene en `OtraMoneda`."""
    neto, exento, iva, total = montos_en_clp(
        {
            'Totales': {
                'TpoMoneda': 'DOLAR USA',
                'MntNeto': 100,
                'MntTotal': 100,
            },
            'OtraMoneda': {
                'MntNetoOtrMnda': 95_000,
                'MntExeOtrMnda': 0,
                'IVAOtrMnda': 0,
                'MntTotOtrMnda': 95_000,
            },
        },
    )

    assert (neto, exento, iva, total) == (95_000, 0, 0, 95_000)


def test_montos_en_clp_falla_si_falta_otra_moneda_en_una_exportacion() -> None:
    """
    Sin `OtraMoneda` no hay forma de saber el equivalente en CLP.

    Preferimos fallar acá a persistir un monto en la moneda equivocada.
    """
    with pytest.raises(ServiceError):
        montos_en_clp(
            {
                'Totales': {
                    'TpoMoneda': 'DOLAR USA',
                    'MntNeto': 100,
                    'MntTotal': 100,
                },
            },
        )
