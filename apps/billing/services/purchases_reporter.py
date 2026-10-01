"""
Servicio: reporte de compras — `DteEmitido` (tipo 46) + `DteRecibido`.

Es la unión con lo que `services/sales_reporter.py` omite: un
`DteEmitido` cuyo `libro()` resuelve a `'compras'` (una Factura de
Compra, código 46, o una Nota de Crédito/Débito que anula una de esas)
nunca aparece en el reporte de ventas — acá se agrega, junto a todo
`DteRecibido` (que siempre es compra, nunca hay un `DteRecibido` de
venta).

Reutiliza `ResumenTipo`/`ResumenPeriodo` de `services/sales_reporter.py`
— son DTO genéricos (no atados a `DteEmitido`), sirven igual para una
fila que mezcla ambos orígenes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import QuerySet

from apps.libredte.models import Contribuyente

from ..models import DteEmitido, DteRecibido, TipoDte
from ..utils.period import adjacent_period, period_label
from .sales_reporter import ResumenPeriodo, ResumenTipo


def _sign(tipo_dte: TipoDte) -> int:
    """Mismo criterio que `sales_reporter._sign()`, para un recibido."""
    return -1 if tipo_dte.operacion == TipoDte.Operacion.RESTA else 1


def _emitidos_de_compras(
    queryset: QuerySet[DteEmitido],
) -> list[DteEmitido]:
    """Filtra `queryset` a los documentos cuyo libro es `'compras'`."""
    documentos = queryset.select_related('tipo_dte').prefetch_related(
        'referencias__referencia__tipo_dte',
    )
    return [dte for dte in documentos if dte.libro() == 'compras']


@dataclass(frozen=True, slots=True)
class PeriodoCompras:
    """Una fila del índice de `/billing/compras/` — un período con datos."""

    periodo: int
    periodo_glosa: str
    documentos: int
    total: int


def periodos(contribuyente: Contribuyente) -> list[PeriodoCompras]:
    """Un `PeriodoCompras` por cada período con documentos de compra."""
    acumulado: dict[int, list[int]] = {}

    for dte in _emitidos_de_compras(
        DteEmitido.objects.filter(contribuyente=contribuyente),
    ):
        fila = acumulado.setdefault(dte.periodo, [0, 0])
        fila[0] += 1
        fila[1] += dte.total * _sign(dte.tipo_dte)

    for recibido in DteRecibido.objects.filter(
        contribuyente=contribuyente,
    ).select_related('tipo_dte'):
        fila = acumulado.setdefault(recibido.periodo, [0, 0])
        fila[0] += 1
        fila[1] += recibido.total * _sign(recibido.tipo_dte)

    return [
        PeriodoCompras(
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


def resumen_periodo(
    contribuyente: Contribuyente,
    periodo: int,
) -> ResumenPeriodo | None:
    """
    Resumen de `periodo`, agrupado por tipo de documento y en total.

    `None` si el contribuyente no tiene documentos de compra en ese
    período — la vista lo trata como "no existe" (404).
    """
    acumulado_por_tipo: dict[int, dict[str, Any]] = {}

    def _acumular(
        tipo_dte: TipoDte,
        total: int,
        neto: int | None,
        exento: int | None,
        iva: int,
    ) -> None:
        signo = _sign(tipo_dte)
        fila = acumulado_por_tipo.setdefault(
            tipo_dte.pk,
            {
                'tipo_dte': tipo_dte,
                'documentos': 0,
                'neto': 0,
                'exento': 0,
                'iva': 0,
                'total': 0,
            },
        )
        fila['documentos'] += 1
        fila['neto'] += (neto or 0) * signo
        fila['exento'] += (exento or 0) * signo
        fila['iva'] += (iva or 0) * signo
        fila['total'] += total * signo

    for dte in _emitidos_de_compras(
        DteEmitido.objects.filter(
            contribuyente=contribuyente,
            periodo=periodo,
        ),
    ):
        _acumular(dte.tipo_dte, dte.total, dte.neto, dte.exento, dte.iva)

    for recibido in DteRecibido.objects.filter(
        contribuyente=contribuyente,
        periodo=periodo,
    ).select_related('tipo_dte'):
        _acumular(
            recibido.tipo_dte,
            recibido.total,
            recibido.neto,
            recibido.exento,
            recibido.iva,
        )

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


@dataclass(frozen=True, slots=True)
class DocumentoCompra:
    """
    Una fila de la tabla de documentos de un período de compras.

    `tipo` ya es el label (`TipoDte.label`, no el objeto `TipoDte`) —
    esta fila no viene de un único `QuerySet` (mezcla `DteEmitido` y
    `DteRecibido`), así que el filtro/orden de la API no puede resolver
    un atributo anidado (`tipo_dte.label`), solo uno plano. Por lo
    mismo, `signo` (`_sign()`) queda guardado aparte — permite sumar el
    gasto por proveedor con el signo correcto (una Nota de Crédito/
    Débito resta) sin necesitar el `TipoDte` completo. No se expone en
    `DocumentoCompraSerializer` — es un dato para agregación
    (`services/dashboard_reporter.py`), no una columna de la tabla en
    pantalla.
    """

    origen: str
    pk: int
    tipo: str
    folio: int
    contraparte: str
    fecha: object
    total: int
    estado: str
    signo: int


def documentos_periodo(
    contribuyente: Contribuyente,
    periodo: int,
) -> list[DocumentoCompra]:
    """
    Documentos de compra de `periodo`, de ambos orígenes.

    Más recientes primero. `origen` (`'emitido'`/`'recibido'`) es lo
    que permite a la vista armar el enlace "Ver" correcto para cada
    fila — un `DteEmitido` tipo 46 y un `DteRecibido` no comparten
    detalle.
    """
    documentos = []

    for dte in _emitidos_de_compras(
        DteEmitido.objects.filter(
            contribuyente=contribuyente,
            periodo=periodo,
        ).select_related('receptor'),
    ):
        documentos.append(
            DocumentoCompra(
                origen='emitido',
                pk=dte.pk,
                tipo=dte.tipo_dte.label,
                folio=dte.folio,
                contraparte=(
                    dte.receptor.razon_social
                    or f'{dte.receptor.rut}-{dte.receptor.dv}'
                ),
                fecha=dte.fecha,
                total=dte.total,
                estado=dte.revision_estado or '—',
                signo=_sign(dte.tipo_dte),
            ),
        )

    for recibido in (
        DteRecibido.objects.filter(
            contribuyente=contribuyente,
            periodo=periodo,
        )
        .select_related('tipo_dte', 'emisor')
        .prefetch_related('rcv_eventos')
    ):
        documentos.append(
            DocumentoCompra(
                origen='recibido',
                pk=recibido.pk,
                tipo=recibido.tipo_dte.label,
                folio=recibido.folio,
                contraparte=(
                    recibido.emisor.razon_social
                    or f'{recibido.emisor.rut}-{recibido.emisor.dv}'
                ),
                fecha=recibido.fecha,
                total=recibido.total,
                estado=recibido.estado_rcv() or '—',
                signo=_sign(recibido.tipo_dte),
            ),
        )

    documentos.sort(key=lambda doc: (doc.fecha, doc.folio), reverse=True)
    return documentos
