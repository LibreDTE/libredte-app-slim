"""
Listas fijas del formato SII usadas por `/billing/emitir`.

Todo lo que vive acá es un listado cerrado y estable definido por el
propio SII (schema DTE, o el vocabulario que usa `form.estandar` de
`libredte-lib-core`) — nunca un catálogo consultado vía SDK (eso es
`repository_provider.py`/`models.py`, tablas pobladas por
`seeders.seed()`) ni un enum propio de un modelo Django. Es el único
archivo de la app con listas de este tipo: si un campo nuevo necesita
una lista fija así, va acá, no repetido inline en un template.

`IndicadorServicio` es un caso especial: el valor que se manda en
`IndServicio` NO corresponde a ningún schema XSD en particular — es el
vocabulario de entrada que `EstandarParserStrategy::addServiceIndicator()`
espera, y esa misma clase es quien decide server-side qué valor final
es válido según el `TipoDTE` (invierte 1↔2 en boletas, filtra 4/5 fuera
de exportación, etc.). Por eso acá se listan las 5 opciones completas,
sin filtrar por tipo de documento — el filtrado ya lo hace la librería.
"""

from __future__ import annotations

from django.db import models


class IndicadorExencion(models.IntegerChoices):
    """`IndExe` — motivo de exención/no-IVA de un ítem (`Detalle`)."""

    NO_AFECTO = 1, 'No afecto o exento de IVA'
    NO_FACTURABLE = 2, 'No facturable'
    GARANTIA = 3, 'Garantía por depósito o envase'
    NO_CONSTITUYE_VENTA = 4, 'No constituye venta'
    ITEM_A_REBAJAR = 5, 'Ítem a rebajar'
    NO_FACTURABLE_NEGATIVO = 6, 'No facturable negativo'


class IndicadorServicio(models.IntegerChoices):
    """`IndServicio` — ver docstring del módulo."""

    DOMICILIARIO = 1, 'Servicios periódicos domiciliarios'
    NO_DOMICILIARIO = 2, 'Otros servicios periódicos (no domiciliarios)'
    SERVICIOS = 3, 'Servicios, o venta y servicios'
    EXPORTACION_HOTELERIA = (
        4,
        'Exportación de servicios de hotelería o espectáculos por cuenta '
        'de terceros',
    )
    EXPORTACION_TRANSPORTE = (
        5,
        'Exportación de servicios de transporte internacional',
    )


class TipoValor(models.TextChoices):
    """`TpoValor`/`TpoValor_global` — unidad de un descuento o recargo."""

    PORCENTAJE = '%', 'Porcentaje'
    MONTO = '$', 'Monto'


class CodigoReferencia(models.IntegerChoices):
    """`CodRef` — qué relación tiene una referencia con este documento."""

    ANULA = 1, 'Anula documento de referencia'
    CORRIGE_TEXTO = 2, 'Corrige texto documento de referencia'
    CORRIGE_MONTOS = 3, 'Corrige montos'


class TipoCuentaPago(models.TextChoices):
    """`TpoCtaPago` — tipo de cuenta bancaria de un pago programado."""

    CORRIENTE = 'CORRIENTE', 'Cuenta corriente'
    VISTA = 'VISTA', 'Cuenta vista'
    AHORRO = 'AHORRO', 'Cuenta de ahorro'


class TipoTransaccionCompra(models.IntegerChoices):
    """`TpoTranCompra` — clasificación de la compra, según el comprador."""

    DEL_GIRO = 1, 'Compra del giro'
    SUPERMERCADO = 2, 'Compra en supermercados o similares'
    BIEN_RAIZ = 3, 'Compra de bien raíz'
    ACTIVO_FIJO = 4, 'Compra de activo fijo'
    IVA_USO_COMUN = 5, 'Compra con IVA de uso común'
    SIN_DERECHO_CREDITO = 6, 'Compra sin derecho a crédito'
    NO_CORRESPONDE_INCLUIR = 7, 'Compra que no corresponde incluir'


class TipoTransaccionVenta(models.IntegerChoices):
    """`TpoTranVenta` — clasificación de la venta, según quien vende."""

    DEL_GIRO = 1, 'Venta del giro'
    ACTIVO_FIJO = 2, 'Venta de activo fijo'
    BIEN_RAIZ = 3, 'Venta de bien raíz'
