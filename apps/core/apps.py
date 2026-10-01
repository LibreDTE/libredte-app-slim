from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'apps.core'

    def ready(self) -> None:
        """
        Dispara el auto-registro de cada app en los registries de `core`.

        `autodiscover_modules` es de Django mismo — el mecanismo real
        detrás de `django.contrib.admin.autodiscover()`, reusado tal
        cual: importa `<app>.platform`/`<app>.seeders`/`<app>.plugins`
        de toda app instalada que los tenga, y falla en silencio solo
        si el módulo no existe (un error real *dentro* de uno de esos
        módulos sí se propaga). El `import` ya registra — cada
        `platform.py`/`seeders.py` llama a `core.registry.register()`
        y cada `plugins.py` llama a `core.plugin.catalog.register()`,
        ambos a nivel de módulo — así que acá no hace falta usar el
        resultado.
        """
        from django.utils.module_loading import autodiscover_modules

        from .registrations import MenuItem, MenuSection
        from .registry import register

        autodiscover_modules('platform')
        autodiscover_modules('seeders')
        autodiscover_modules('plugins')

        # "Plugins" es de `core`, no de una app de dominio en
        # particular: no es un concern específico de ninguna, así que
        # `core` se registra a sí mismo en vez de dejarlo en el
        # `platform.py` de otra app.
        register(
            'settings',
            MenuSection(
                label='Plataforma',
                icon='puzzle-piece',
                priority=100,
                items=[
                    MenuItem(
                        'Plugins',
                        'core_settings:plugins',
                        'shapes',
                        '/settings/plugins',
                    ),
                ],
            ),
        )
