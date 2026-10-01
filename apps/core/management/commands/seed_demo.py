"""Comando `seed_demo`: puebla una base vacía con datos de demostración."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.registry import get_all


class Command(BaseCommand):
    """
    Corre, en orden de `priority`, cada `Seeder` registrado en `'seed_demo'`.

    "Vacía" significa sin usuarios — mismo criterio que usa
    `RequireInitialUserMiddleware` para saber si es una instalación
    nueva; si ya existe cualquier usuario, no se hace nada (no está
    pensado para reconciliar una base con datos, solo para no tener
    que rellenar todo a mano después de un reset).

    Corre primero `seed` (los catálogos reales, ver
    `management/commands/seed.py`) — el escenario de demostración de
    cualquier app los necesita cargados. Todos los seeders de demo, de
    todas las apps, corren dentro de una única transacción: si
    cualquiera falla, se revierte todo entero, dejando el comando
    reintentable tal cual. Cada app aporta los suyos vía `<app>.seeders`
    (ver `apps/billing/seeders.py`), así que este comando no conoce ni
    depende de ninguna app en particular — tampoco de sus errores de
    dominio: si un seeder necesita abortar con un mensaje amigable, es
    responsabilidad suya traducir su propia excepción a `CommandError`.
    """

    help = 'Puebla una base vacía con datos de demostración.'

    def handle(self, *_args: Any, **_options: Any) -> None:
        if User.objects.exists():
            self.stdout.write(
                self.style.ERROR(
                    'Ya existe al menos un usuario: la base no está '
                    'vacía. No se creó nada.',
                ),
            )
            return

        seeders = get_all('seed_demo')
        if not seeders:
            self.stdout.write(
                self.style.WARNING('No hay seeders de demo registrados.'),
            )
            return

        call_command('seed')

        with transaction.atomic():
            for seeder in seeders:
                self.stdout.write(f'→ {seeder.label}')
                seeder.run()

        self.stdout.write(self.style.SUCCESS('Listo.'))
