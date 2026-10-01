"""
Value objects que las apps usan para registrarse en `core` (ver `registry.py`).

Sin nada de Django acá a propósito (nada de `reverse`/`request`) — son
datos puros, para que este archivo (y el mecanismo de registro que lo
usa) se pueda mover tal cual a un paquete aparte el día que corresponda,
sin arrastrar nada específico de este proyecto.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MenuItem:
    """
    Un destino navegable — una entrada del menú principal o de Configuración.

    `active_prefix` es el prefijo de `request.path` que lo marca activo
    (ej. `/receptores`) — por prefijo, no por nombre de vista exacto,
    para que una página de detalle bajo esa misma ruta cuente como
    parte de la misma sección sin tener que enumerarla.
    """

    label: str
    url_name: str
    icon: str
    active_prefix: str


@dataclass(frozen=True)
class MenuSection:
    """
    Un grupo de `MenuItem` — una sección del menú principal o de Configuración.

    Mismo tipo para ambos casos: la diferencia entre "menú principal" y
    "menú de Configuración" es solo a qué registro (`kind`) se registra
    la sección (ver `registry.py`), no el dato en sí — en ambos casos
    es "un menú de páginas distintas, agrupadas".
    """

    label: str
    icon: str
    items: list[MenuItem] = field(default_factory=list)
    priority: int = 0


@dataclass(frozen=True)
class DashboardWidget:
    """
    Un trozo de template que una app aporta al dashboard.

    `get_context` recibe el `request` y devuelve el contexto con el que
    se renderiza `template` — así cada app calcula sus propios datos
    (ej. llamando a su propio servicio de estadísticas) sin que `core`
    necesite saber nada de eso. `template` se renderiza
    aparte (`django.template.loader.render_to_string`), no vía
    `{% extends %}`: es un fragmento HTML opaco para `core`, que solo
    lo junta con los de las demás apps y los concatena en orden.
    """

    template: str
    get_context: Callable[[Any], dict[str, Any]]
    priority: int = 0


@dataclass(frozen=True)
class ProfileSection:
    """
    Una pestaña que una app aporta al perfil del usuario.

    Mismo mecanismo que `DashboardWidget` (`template`/`get_context`
    opacos para `core`) — `tab_id` es el id HTML de la pestaña (usado
    por `Tabs` de `derafu-js`), y `label` el texto que se muestra en
    el trigger.
    """

    label: str
    tab_id: str
    template: str
    get_context: Callable[[Any], dict[str, Any]]
    priority: int = 0


@dataclass(frozen=True)
class Seeder:
    """
    Un cargador de datos que una app aporta a los comandos `seed`/`seed_demo`.

    `run` no recibe nada ni devuelve nada: cada seeder resuelve por su
    cuenta lo que necesita (ej. el contribuyente activo, o sus propios
    modelos) y es responsable de su propio mensaje de progreso/resultado
    y de ser idempotente (ej. no volver a cargar catálogos que ya
    existen). `label` identifica al seeder en el output del comando —
    no tiene relación con `kind` (`'seed'` vs `'seed_demo'`, ver
    `registry.py`), que es lo que distingue en cuál de los dos corre.
    """

    label: str
    run: Callable[[], None]
    priority: int = 0
