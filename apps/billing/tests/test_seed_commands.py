"""
Tests para los comandos `seed`/`seed_demo` (`apps/core`), de punta a punta.

Ambos corren los seeders que `apps/billing/seeders.py` registra (`seed`
para los catálogos, `seed_demo` para emitir los documentos de ejemplo)
— llaman a la API real de LibreDTE Lib, marcados `live` y excluidos de
`pytest`/`make check` por defecto (ver `pyproject.toml`), igual que el
resto de los tests que golpean la API real. Correr con `make test-live`
(requiere `PLUGIN_LIBREDTE_BACKEND_API_URL` apuntando a un servidor real).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.billing.models import DteEmitido, Item, TipoDte
from apps.billing.seeders import DEMO_USERNAME
from apps.libredte.models import Contribuyente

pytestmark = [pytest.mark.django_db, pytest.mark.live]


def test_seed_carga_los_catalogos() -> None:
    call_command('seed')

    assert TipoDte.objects.exists()


def test_seed_demo_crea_el_escenario_de_demostracion() -> None:
    call_command('seed_demo')

    contribuyente = Contribuyente.objects.get()
    assert contribuyente.usuario.username == DEMO_USERNAME
    assert Item.objects.filter(contribuyente=contribuyente).exists()
    assert DteEmitido.objects.filter(contribuyente=contribuyente).exists()


def test_seed_demo_no_hace_nada_si_ya_hay_un_usuario() -> None:
    User.objects.create_user('otro')

    call_command('seed_demo')

    assert not Contribuyente.objects.exists()
