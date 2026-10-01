"""
Aritmética de período (`YYYYMM`) compartida por los reportes de facturación.

Vive en su propio módulo (no en `dashboard_reporter.py`, donde estaban
antes) porque `sales_reporter.py`/`purchases_reporter.py` ya las
necesitaban, y `dashboard_reporter.py` ahora también necesita
reutilizar `sales_reporter.py`/`purchases_reporter.py` — dejarlas en
`dashboard_reporter.py` habría formado un import circular.

Sin especificidad de dominio SII (es aritmética genérica de un entero
`YYYYMM`) — por eso va en inglés, a diferencia de `dte.py`, cuyo
contenido sí es vocabulario SII real.
"""

from __future__ import annotations

from django.utils import timezone

MONTHS = [
    'Enero',
    'Febrero',
    'Marzo',
    'Abril',
    'Mayo',
    'Junio',
    'Julio',
    'Agosto',
    'Septiembre',
    'Octubre',
    'Noviembre',
    'Diciembre',
]
MONTHS_ABBREVIATED = [
    'Ene',
    'Feb',
    'Mar',
    'Abr',
    'May',
    'Jun',
    'Jul',
    'Ago',
    'Sep',
    'Oct',
    'Nov',
    'Dic',
]


def current_period() -> int:
    """Período (`YYYYMM`) del mes en curso."""
    today = timezone.localdate()
    return today.year * 100 + today.month


def adjacent_period(period: int, delta_months: int) -> int:
    """`period` (`YYYYMM`) desplazado `delta_months` meses (+1/-1)."""
    year, month = divmod(period, 100)
    total_months = year * 12 + (month - 1) + delta_months
    year, month = divmod(total_months, 12)
    return year * 100 + month + 1


def period_label(period: int) -> str:
    """`period` (`YYYYMM`) como texto legible (ej. `"Septiembre 2026"`)."""
    year, month = divmod(period, 100)
    return f'{MONTHS[month - 1]} {year}'
