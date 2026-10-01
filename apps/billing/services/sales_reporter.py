"""
Servicio: reporte de ventas — resumen de DTE emitidos por período.

Lectura pura sobre `DteEmitido` ya persistido, nada de SDK — a
diferencia de `biller`/`document_renderer`/`document_dispatcher`, este
servicio no llama a la API de LibreDTE Lib en absoluto. El "libro
oficial" que se envía al SII (`book.builder` del SDK, ver
`BookBuilderService`) es una acción distinta, todavía sin cablear acá
(sería un botón sobre estos mismos datos, no una URL/modelo aparte).

Solo cuenta documentos cuyo `DteEmitido.libro()` resuelve a `'ventas'`
— una Factura de Compra (código 46) nunca entra acá, y una Nota de
Crédito/Débito que anula una factura de compra tampoco, aunque su tipo
de documento en sí no distinga por sí solo entre ambos libros (ver
`DteEmitido.libro()`). Por eso la agregación es en Python, no una
consulta SQL directa: la clasificación de una Nota de Crédito/Débito
depende de sus referencias, no de una columna filtrable.

Reutiliza `utils.period.adjacent_period`/`period_label` (no están
duplicados acá). El signo (`_sign()`) es el mismo criterio que
`dashboard_reporter._sign()`: una nota de crédito/débito resta o suma
sobre el período al que hace referencia — sin esto, el total de un
período con notas de crédito quedaría sobreestimado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import QuerySet

from apps.libredte.models import Contribuyente

from ..models import DteEmitido, TipoDte
from ..utils.period import adjacent_period, period_label


def _sign(tipo_dte: TipoDte) -> int:
    """Mismo criterio que `dashboard_reporter._sign()`, para uso en Python."""
    return -1 if tipo_dte.operacion == TipoDte.Operacion.RESTA else 1


def _documentos_de_ventas(
    queryset: QuerySet[DteEmitido],
) -> list[DteEmitido]:
    """Filtra `queryset` a los documentos cuyo libro es `'ventas'`."""
    documentos = queryset.select_related('tipo_dte').prefetch_related(
        'referencias__referencia__tipo_dte',
    )
    return [dte for dte in documentos if dte.libro() == 'ventas']


@dataclass(frozen=True, slots=True)
class PeriodoVentas:
    """Una fila del índice de `/billing/ventas/` — un período con datos."""

    periodo: int
    periodo_glosa: str
    documentos: int
    total: int


def periodos(contribuyente: Contribuyente) -> list[PeriodoVentas]:
    """Un `PeriodoVentas` por cada período con documentos de venta."""
    acumulado: dict[int, list[int]] = {}
    for dte in _documentos_de_ventas(
        DteEmitido.objects.filter(contribuyente=contribuyente),
    ):
        fila = acumulado.setdefault(dte.periodo, [0, 0])
        fila[0] += 1
        fila[1] += dte.total * _sign(dte.tipo_dte)

    return [
        PeriodoVentas(
            periodo=periodo,
            periodo_glosa=period_label(periodo),
            documentos=documentos,
            total=total,
        )
        for periodo, (documentos, total) in sorted(
            acumulado.items(),
            reverse=True,
        )
    ]


@dataclass(frozen=True, slots=True)
class ResumenTipo:
    """Una fila del resumen de un período, para un tipo de documento."""

    tipo_dte: TipoDte
    documentos: int
    neto: int
    exento: int
    iva: int
    total: int


@dataclass(frozen=True, slots=True)
class ResumenPeriodo:
    """Resumen completo de un período: por tipo de documento, y el total."""

    periodo: int
    periodo_glosa: str
    periodo_anterior: int
    periodo_siguiente: int
    por_tipo: list[ResumenTipo]
    documentos: int
    neto: int
    exento: int
    iva: int
    total: int


def resumen_periodo(
    contribuyente: Contribuyente,
    periodo: int,
) -> ResumenPeriodo | None:
    """
    Resumen de `periodo`, agrupado por tipo de documento y en total.

    `None` si el contribuyente no tiene documentos en ese período —
    la vista lo trata como "no existe" (404), no como una lista vacía.
    """
    acumulado_por_tipo: dict[int, dict[str, Any]] = {}
    for dte in _documentos_de_ventas(
        DteEmitido.objects.filter(
            contribuyente=contribuyente, periodo=periodo
        ),
    ):
        signo = _sign(dte.tipo_dte)
        fila = acumulado_por_tipo.setdefault(
            dte.tipo_dte_id,
            {
                'tipo_dte': dte.tipo_dte,
                'documentos': 0,
                'neto': 0,
                'exento': 0,
                'iva': 0,
                'total': 0,
            },
        )
        fila['documentos'] += 1
        fila['neto'] += (dte.neto or 0) * signo
        fila['exento'] += (dte.exento or 0) * signo
        fila['iva'] += (dte.iva or 0) * signo
        fila['total'] += dte.total * signo

    if not acumulado_por_tipo:
        return None

    por_tipo = [
        ResumenTipo(**fila)
        for fila in sorted(
            acumulado_por_tipo.values(),
            key=lambda fila: fila['tipo_dte'].codigo,
        )
    ]
    return ResumenPeriodo(
        periodo=periodo,
        periodo_glosa=period_label(periodo),
        periodo_anterior=adjacent_period(periodo, -1),
        periodo_siguiente=adjacent_period(periodo, 1),
        por_tipo=por_tipo,
        documentos=sum(fila.documentos for fila in por_tipo),
        neto=sum(fila.neto for fila in por_tipo),
        exento=sum(fila.exento for fila in por_tipo),
        iva=sum(fila.iva for fila in por_tipo),
        total=sum(fila.total for fila in por_tipo),
    )
