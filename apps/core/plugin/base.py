"""
Bases genéricas del mecanismo de plugins (ver `catalog.py`/`resolver.py`).

Ninguna de las dos es ABC: no fuerzan métodos con `abstractmethod` a
este nivel, así que ninguna lleva `Abstract` en el nombre — son bases
para extender, no contratos con garantía de Python detrás. El contrato
real de una capability específica (con sus propios `abstractmethod`)
lo declara la app dueña de esa capability, no `core`.
"""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar


class BasePlugin:
    """
    Lo que cualquier plugin necesita para registrarse/activarse en Slim.

    Cada subclase concreta trae su propio `capabilities` (qué
    implementaciones de qué `BasePluginCapability` provee — ver
    `get_capability()`), además de los metadatos declarados acá.
    `config_form` es la clase de un `forms.Form` real de Django —
    tipado `type[Any]` a propósito, para no importar `django.forms`
    acá.
    """

    # Django intenta LLAMAR cualquier valor "callable" que resuelve en
    # un template (toda clase lo es) — sin esto, `{{ plugin.label }}`
    # con `plugin` = la clase (no una instancia, ej. en un listado que
    # no necesita activar nada) intentaría `LibredteLibApiPlugin()`
    # sin el `config` requerido, fallaría, y Django lo silenciaría
    # como variable inválida (string vacío, sin excepción visible).
    do_not_call_in_templates: ClassVar[bool] = True

    id: ClassVar[str]
    label: ClassVar[str]
    # Qué hace este plugin, para quien lo esté activando (ver
    # `core/plugin_configure.html`) — distinto de
    # `BasePluginCapability.description`, que documenta el
    # comportamiento por defecto de la capability SIN ningún plugin.
    description: ClassVar[str] = ''
    config_form: ClassVar[type[Any]]
    # Ordena el catálogo estático (`catalog.py::all_plugins()`, lo que
    # ve el listado de Configuración > Plugins) — no tiene relación
    # con el orden de una cascada real (`resolver.resolve_all()`), que
    # es `PluginConfig.priority`, por tenant.
    priority: ClassVar[int] = 0
    # Si es False, no debe listarse en catálogos/UI (pero puede seguir
    # activo para tenants que ya lo tengan configurado) — ej. un
    # plugin interno de pruebas, o uno reemplazado que aún no se
    # desactiva de raíz.
    listable: ClassVar[bool] = True
    # None = no está deprecado. Con fecha (pasada o futura) el plugin
    # sigue activo/usable igual — es solo la señal para que la UI
    # muestre el aviso; nada del mecanismo (`resolver.resolve()`) la
    # revisa.
    deprecated_at: ClassVar[date | None] = None
    # Plantilla que renderiza `core_settings:plugin_configure`. El
    # default (`core/plugin_configure.html`) es un fallback trivial —
    # alcanza para un plugin sin nada propio que mostrar. Uno que
    # necesite layout propio (tabs, cards, orden de campos distinto,
    # contenido propio) apunta acá a SU PROPIA plantilla, que extiende
    # `layouts/settings.html` directo (no el fallback — control total
    # del `settings_content`, `core` no impone ninguna estructura).
    template_name: ClassVar[str] = 'core/plugin_configure.html'
    # `{definición: implementación}` — qué `BasePluginCapability` provee
    # este plugin y con qué clase concreta. Listar lo que un plugin
    # implementa es leer estas llaves, sin instanciar nada (ver
    # `catalog.plugins_for_capability()`).
    capabilities: ClassVar[
        dict[type[BasePluginCapability], type[BasePluginCapability]]
    ] = {}

    def __init__(self, config: dict[str, Any]) -> None:
        """Guarda `config` (ya validado por `config_form`)."""
        self.config = config

    def get_extra_context(self) -> dict[str, Any]:
        """
        Contexto extra para `template_name` — nada por defecto.

        Mismo rol que `get_context()` en `DashboardWidget`/
        `ProfileSection` (`apps/core/registrations.py`): cada plugin
        calcula lo que su propia plantilla necesita (ej. un valor por
        defecto a mostrar como placeholder), sin que `core` tenga que
        saber qué es.
        """
        return {}

    def get_capability(
        self, definition_class: type[BasePluginCapability]
    ) -> BasePluginCapability:
        """
        La implementación que este plugin provee para `definition_class`.

        Default: instancia la implementación pasándole `self.config` tal
        cual — alcanza mientras su constructor acepte `config` como único
        argumento (como hoy). Una capability que necesite construirse
        distinto obliga a que SU plugin sobreescriba este método, en vez
        de forzar una forma única en `BasePluginCapability`.
        """
        implementation_class = self.capabilities[definition_class]
        # `BasePluginCapability` no declara `__init__` (no toda capability
        # necesita `config`) — mypy no puede saber que la implementación
        # concreta sí lo acepta. Es el trade-off documentado arriba: un
        # plugin cuya capability necesite algo distinto sobreescribe este
        # método entero, no solo esta línea.
        return implementation_class(self.config)  # type: ignore[call-arg]


class BasePluginCapability:
    """
    Un punto de extensión con nombre fijo (ej. `libredte.backend`).

    Declarada por la app dueña del concepto, nunca por quien la
    implementa: dueño e implementador pueden ser apps distintas (un
    plugin de terceros puede implementar una capability que declaró
    otra app). Un `BasePlugin` la provee agregándola a su propio
    `capabilities` (`{esta_clase: su_implementación_concreta}`), no
    heredándola — un plugin puede proveer varias sin que eso lo
    obligue a mezclar los métodos de todas en su propio namespace.
    """

    # Mismo motivo que en `BasePlugin` — se pasa la CLASE tal cual a
    # `plugin_configure.html` (`capabilities = list(plugin_class.capabilities)`
    # en `apps/core/views/settings.py`), nunca una instancia.
    do_not_call_in_templates: ClassVar[bool] = True

    id: ClassVar[str]
    label: ClassVar[str]
    # Comportamiento por defecto de la capability SIN ningún plugin
    # activo.
    description: ClassVar[str] = ''
    # Ordena el catálogo cuando se agrupa por capability (ver
    # `catalog.py`), igual criterio que `BasePlugin.priority`.
    priority: ClassVar[int] = 0
