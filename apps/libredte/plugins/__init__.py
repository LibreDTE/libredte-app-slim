"""
Plugins de `libredte`.

Auto-descubierto por `autodiscover_modules('plugins')`
(`apps/core/apps.py::ready()`) — este archivo es el único `.py` suelto
que se importa directo; su único trabajo es registrar cada plugin
concreto, uno por subcarpeta.
"""

from apps.core.plugin.catalog import register

from .apigatewaycl.plugin import ApiGatewayClPlugin
from .libredte_lib_api.plugin import LibredteLibApiPlugin

register(LibredteLibApiPlugin)
register(ApiGatewayClPlugin)
