"""Tests para `utils.period`."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.billing.utils.period import adjacent_period, current_period


@pytest.mark.parametrize(
    ('period', 'delta', 'esperado'),
    [
        (202609, 1, 202610),
        (202609, -1, 202608),
        (202612, 1, 202701),  # cambio de año hacia adelante
        (202601, -1, 202512),  # cambio de año hacia atrás
    ],
)
def test_adjacent_period(period: int, delta: int, esperado: int) -> None:
    assert adjacent_period(period, delta) == esperado


def test_current_period_matches_today() -> None:
    hoy = timezone.localdate()
    assert current_period() == hoy.year * 100 + hoy.month
