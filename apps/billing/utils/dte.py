"""Monto de un documento, siempre en pesos chilenos."""

from __future__ import annotations

from typing import Any

from apps.libredte.services.exceptions import ServiceError


def montos_en_clp(
    encabezado: dict[str, Any],
) -> tuple[int | None, int | None, int, int]:
    """
    `(neto, exento, iva, total)` del documento, siempre en pesos chilenos.

    `Totales` trae los montos en la moneda propia del documento — para
    la generalidad de los DTE esa moneda ya es CLP (`TpoMoneda` ni
    siquiera viene informado, ver `AbstractDocument::getMoneda()` en
    libredte-lib-core, que asume 'PESO CL' por defecto). Solo
    exportación (110/111/112) puede venir en otra moneda; en ese caso
    el equivalente en CLP viene en el nodo `OtraMoneda` (`TpoCambio` +
    montos ya multiplicados), calculado por la API — acá no se hace
    ninguna conversión propia.

    Si el documento viene en otra moneda pero la API no entregó
    `OtraMoneda`, no hay forma de saber el equivalente en CLP: se
    prefiere fallar acá a persistir un monto en la moneda equivocada.
    """
    totales = encabezado['Totales']
    moneda = totales.get('TpoMoneda') or 'PESO CL'

    if moneda == 'PESO CL':
        return (
            totales.get('MntNeto'),
            totales.get('MntExe'),
            totales.get('IVA', 0),
            totales['MntTotal'],
        )

    otra_moneda = encabezado.get('OtraMoneda')
    if not otra_moneda:
        raise ServiceError(
            f'El documento está en {moneda} pero la API no entregó el '
            f'tipo de cambio a pesos chilenos (nodo OtraMoneda).',
        )

    return (
        otra_moneda.get('MntNetoOtrMnda'),
        otra_moneda.get('MntExeOtrMnda'),
        otra_moneda.get('IVAOtrMnda', 0),
        otra_moneda['MntTotOtrMnda'],
    )
