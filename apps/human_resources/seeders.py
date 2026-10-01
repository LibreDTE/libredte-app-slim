"""
Registro de `human_resources` en los seeders de `core` (`seed`/`seed_demo`).

Importado por `core.apps.CoreConfig.ready()` vía
`autodiscover_modules('seeders')` — el `import` en sí ya registra, nada
de esto se llama a mano. Ver `apps/billing/platform.py` para el mismo
patrón, y `apps/billing/seeders.py` para el mismo mecanismo con datos
reales — acá todavía no hay catálogos ni escenario de demostración
propios, así que ambos seeders son un placeholder.
"""

from __future__ import annotations

from apps.core.registrations import Seeder
from apps.core.registry import register


def seed() -> None:
    """Placeholder — `human_resources` todavía no tiene catálogos propios."""
    print('human_resources: nada que cargar todavía.')


def seed_demo() -> None:
    """Placeholder — `human_resources` todavía no tiene demo propio."""
    print('human_resources: nada que sembrar todavía.')


register(
    'seed',
    Seeder(label='human_resources (placeholder)', run=seed, priority=20),
)
register(
    'seed_demo',
    Seeder(label='human_resources (placeholder)', run=seed_demo, priority=20),
)
