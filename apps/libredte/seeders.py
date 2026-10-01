"""
Registro de `libredte` en los seeders de `core` (comando `seed`).

Importado por `core.apps.CoreConfig.ready()` vía
`autodiscover_modules('seeders')` — el `import` en sí ya registra, nada
de esto se llama a mano. Ver `apps/billing/seeders.py` para el mismo
patrón, aplicado a los catálogos propios de facturación.
"""

from __future__ import annotations

from django.core.management.color import color_style

from apps.core.registrations import Seeder
from apps.core.registry import register

from .models import ActividadEconomica, Comuna, Pais
from .services import repository_provider

_style = color_style()

# La API todavía no expone un repositorio de actividades económicas (a
# diferencia de comuna/país) — se cargan a mano mientras
# tanto, con los códigos que la app haya necesitado hasta ahora
# (agregar acá cualquier otro que haga falta). El día que exista el
# repositorio en la API, esto se reemplaza por una llamada real a
# `repository_provider`, igual que comuna/país.
ACTIVIDADES_ECONOMICAS = [
    {
        'codigo': 619090,
        'glosa': 'OTRAS ACTIVIDADES DE TELECOMUNICACIONES N.C.P.',
        'afecta_iva': True,
    },
    {
        'codigo': 620200,
        'glosa': (
            'ACTIVIDADES DE CONSULTORIA DE INFORMATICA Y DE GESTION DE '
            'INSTALACIONES INFORMATICAS'
        ),
        'afecta_iva': True,
    },
]


def seed() -> None:
    """
    Carga comuna, país y actividad económica.

    `libredte-lib-core` es la única fuente de verdad de comuna/país —
    nada acá se reinterpreta ni se guarda distinto a como lo entrega el
    repositorio (ver `Comuna.codigo`). Actividad económica es la
    excepción: no tiene repositorio en la API todavía, así que se carga
    a mano (ver `ACTIVIDADES_ECONOMICAS`). Corre antes que el `seed()`
    de `billing` (menor `priority`, ver `register()` más abajo) — sus
    catálogos (`TipoDte`, etc.) no dependen de comuna/actividad
    económica, pero el escenario de demostración (`seed_demo`) sí.
    """
    if Comuna.objects.exists():
        print(
            _style.ERROR(
                'libredte: ya hay comunas cargadas, no se hizo nada.',
            ),
        )
        return

    comunas = repository_provider.load_comunas()
    Comuna.objects.bulk_create(
        Comuna(codigo=comuna['codigo'], glosa=comuna['nombre'])
        for comuna in comunas
    )

    paises = repository_provider.load_paises()
    Pais.objects.bulk_create(
        Pais(codigo=pais['codigo'], glosa=pais['glosa']) for pais in paises
    )

    ActividadEconomica.objects.bulk_create(
        ActividadEconomica(**actividad) for actividad in ACTIVIDADES_ECONOMICAS
    )

    print(
        _style.SUCCESS(
            f'libredte: {len(comunas)} comunas, {len(paises)} países, '
            f'{len(ACTIVIDADES_ECONOMICAS)} actividades económicas.',
        ),
    )


register(
    'seed',
    Seeder(label='Comuna, país y actividad económica', run=seed, priority=5),
)
