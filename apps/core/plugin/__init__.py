"""
Mecanismo de plugins de Slim.

Nombre singular a propósito: `<app>.plugins` (plural) es la convención
de auto-descubrimiento reservada para que una app declare SUS `BasePlugin`
concretos (igual que `<app>.platform`/`<app>.seeders`) — este paquete
es la maquinaria que lo hace posible, no una app declarando plugins
propios, así que no puede compartir ese nombre sin volverlo ambiguo.

El descubrimiento es `autodiscover_modules('plugins')`
(`apps/core/apps.py::ready()`), no `importlib.metadata.entry_points()`
(el mecanismo que usan `pytest`/`flake8` para plugins instalados por
separado con `pip`): acá todo plugin vive dentro de este mismo repo
(en `apps/<dominio>/plugins/<nombre>/`), agregado a mano a
`INSTALLED_APPS` cuando corresponde — no hay ningún paquete de
terceros que descubrir. Entry points tampoco alcanzaría solo si lo
hubiera: un plugin con templates/estáticos propios (como
`libredte_lib_api`) los necesita buscables por Django
(`APP_DIRS=True`), y eso depende de `INSTALLED_APPS`, no de que el
código Python se pueda importar — migrar a entry points requeriría
además un template/static loader propio que busque en paquetes
descubiertos así.
"""
