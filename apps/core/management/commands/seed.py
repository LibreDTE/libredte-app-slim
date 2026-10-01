"""Comando `seed`: corre los seeders de catálogo real que cada app registró."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.core.registry import get_all


class Command(BaseCommand):
    """
    Corre, en orden de `priority`, cada `Seeder` registrado en `'seed'`.

    Pensado para datos de referencia reales (catálogos SII, y lo que
    cada app agregue a futuro) — seguro de correr en producción. Cada
    app aporta los suyos vía `<app>.seeders` (ver
    `apps/billing/seeders.py`), auto-descubierto igual que
    `<app>.platform` (`CoreConfig.ready()`), así que este comando no
    conoce ni depende de ninguna app en particular.
    """

    help = 'Corre los seeders de catálogo real que cada app registró.'

    def handle(self, *_args: Any, **_options: Any) -> None:
        seeders = get_all('seed')
        if not seeders:
            self.stdout.write(
                self.style.WARNING('No hay seeders de catálogo registrados.'),
            )
            return

        for seeder in seeders:
            self.stdout.write(f'→ {seeder.label}')
            seeder.run()
