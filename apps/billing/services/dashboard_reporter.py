"""
Servicio: estadísticas del dashboard.

Encapsula toda la lógica de negocio del dashboard (qué cuenta como "con
reparos", qué se excluye de los montos agregados, cómo se arman los
gráficos) separada de la vista — `pages.views.dashboard` solo debe
llamar a `get_dashboard_stats()` y renderizar lo que devuelve, no
decidir nada de negocio por su cuenta.

Todo lo de "ventas" (documentos, montos, gráfico por tipo, top
receptores) solo cuenta documentos cuyo `DteEmitido.libro()` resuelve a
`'ventas'` — igual que `services/sales_reporter.py`, y por el mismo
motivo: una Factura de Compra (código 46) o una Nota de Crédito/Débito
que anula una no son ventas, aunque estén en la tabla de emitidos.
Reutiliza `services/sales_reporter.py`/`services/purchases_reporter.py`
en vez de reimplementar esa clasificación acá.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.libredte.models import Contribuyente
from apps.libredte.tenancy import get_current_contribuyente

from ..models import CafFolio, DteEmitido, DteRecibido, TipoDte
from ..utils.period import (
    MONTHS_ABBREVIATED,
    adjacent_period,
    current_period,
    period_label,
)
from . import purchases_reporter as purchases_service
from . import sales_reporter as sales_service

if TYPE_CHECKING:
    from django.http import HttpRequest


def _sign(tipo_dte: TipoDte) -> int:
    """Mismo criterio que `sales_reporter._sign()`, para uso en Python."""
    return -1 if tipo_dte.operacion == TipoDte.Operacion.RESTA else 1


def _documentos_de_ventas(
    queryset: QuerySet[DteEmitido],
) -> list[DteEmitido]:
    """Mismo criterio que `sales_reporter._documentos_de_ventas()`."""
    documentos = queryset.prefetch_related('referencias__referencia__tipo_dte')
    return [dte for dte in documentos if dte.libro() == 'ventas']


# Mismo criterio que usa la UI de "Documentos emitidos"/`documento_
# detalle` para decidir el color del badge de estado SII — un documento
# con esta glosa quedó con reparos, no aceptado sin más.
_CODIGOS_REPARO = ('RLV', 'RPR')

# Códigos SII de rechazo definitivo de un envío, tal como los mapea
# `EstadoEnvioSii::RECHAZADOS` en `libredte-lib-core` (`Package/Billing
# /Component/Integration/Enum`) — un documento rechazado no es lo mismo
# que uno con reparos leves (`_CODIGOS_REPARO`): un reparo se acepta
# igual, un rechazo no se timbró ante el SII y necesita corregirse y
# reemitirse.
_CODIGOS_RECHAZO = ('RSC', 'RCH', 'RPT', 'RFR', 'VOF', 'RCT')

# `Q` equivalente a `_esta_rechazado()`, para la alerta global
# (`rechazados_pendientes`): esa sí sigue siendo un `QuerySet` sin
# filtrar por `libro()` (un rechazo hay que corregirlo sea venta o
# compra), así que se resuelve en SQL, no iterando en Python.
_RECHAZADO = Q(
    *(Q(revision_estado__contains=codigo) for codigo in _CODIGOS_RECHAZO),
    _connector=Q.OR,
)

# Umbral de días para avisar que el certificado digital está por vencer.
_DIAS_ALERTA_CERTIFICADO = 20

# Plazo de la Ley 19.983 para reclamar un DTE recibido (ver
# `DteRecibido.estado_rcv()`) — "por vencer" acá es una alerta previa,
# no la regla en sí: avisa cuando quedan pocos días para que el
# documento se acepte tácitamente sin que nadie lo haya revisado.
_DIAS_PLAZO_RCV = 8
_DIAS_ALERTA_RCV_RESTANTES = 3

# Ventana de historial usada para estimar el consumo diario de folios
# (`_folios_resumen()`) y para acotar el gráfico "Ventas vs Compras" a
# un tramo legible — ninguno de los dos es "todo el historial" (a
# diferencia de `grafico_periodo`, que si lo es).
_DIAS_CONSUMO_FOLIOS = 30
_MESES_TENDENCIA_VENTAS_COMPRAS = 12

# Estados posibles de `DteRecibido.estado_rcv()`, más "Sin registrar en
# RCV" (su `None`) — orden fijo para que `grafico_rcv` sea siempre el
# mismo eje, tenga o no datos cada período.
_ESTADOS_RCV = (
    'Con acuse de recibo',
    'Pendiente',
    'Recibido automáticamente',
    'Rechazado',
    'Sin registrar en RCV',
)


def _tiene_reparo(revision_estado: str) -> bool:
    """Mismo criterio que `_CODIGOS_REPARO`, para un `DteEmitido` en Python."""
    return any(codigo in revision_estado for codigo in _CODIGOS_REPARO)


def _esta_rechazado(revision_estado: str) -> bool:
    """Mismo criterio que `_CODIGOS_RECHAZO`, para uso en Python."""
    return any(codigo in revision_estado for codigo in _CODIGOS_RECHAZO)


@dataclass(frozen=True, slots=True)
class FolioResumen:
    """
    Folios disponibles de un tipo de documento, más una estimación de uso.

    `dias_restantes` viene del consumo real de los últimos
    `_DIAS_CONSUMO_FOLIOS` días (`disponibles / consumo_diario`) —
    `None` si no hubo ningún documento de ese tipo en esa ventana (no
    hay ritmo con qué estimar, no significa "nunca se agotan").
    """

    tipo_dte: TipoDte
    disponibles: int
    siguiente: int
    alerta: int
    dias_restantes: int | None


@dataclass(frozen=True, slots=True)
class DashboardStats:
    """
    Estadísticas del dashboard para un `Contribuyente` y período dados.

    La mayoría de los datos son del período seleccionado (`periodo`) —
    documentos, montos, estado SII/RCV, top receptores/proveedores,
    últimos documentos. Quedan fuera de ese alcance a propósito, porque
    no son "del período" sino del estado actual/operativo de la app:
    `grafico_periodo` (tendencia de todo el historial, por eso no
    limitada a `_MESES_TENDENCIA_VENTAS_COMPRAS` como `grafico_ventas
    _compras`), `folios_por_tipo` (contador en vivo) y las alertas
    (`rechazados_pendientes`/`dias_vencimiento_certificado`/
    `emitidos_sin_enviar`/`recibidos_pendientes_rcv`/`recibidos_por
    _vencer_rcv`/`recibidos_rechazados_rcv`, cosas que necesitan
    atención ahora, sin importar qué período se esté mirando).
    """

    periodo: int
    periodo_glosa: str
    periodo_anterior: int
    periodo_siguiente: int | None

    documentos: int
    total_neto: int
    iva_neto: int
    con_reparos: int
    rechazados: int

    ventas_variacion_pct: float | None
    compras_total: int
    compras_documentos: int
    margen_operativo: int
    concentracion_top1_pct: float | None
    concentracion_top3_pct: float | None

    rechazados_pendientes: int
    dias_vencimiento_certificado: int | None
    emitidos_sin_enviar: int
    recibidos_pendientes_rcv: int
    recibidos_por_vencer_rcv: int
    recibidos_rechazados_rcv: int

    grafico_periodo: dict[str, Any]
    grafico_ventas_compras: dict[str, Any]
    grafico_estado: dict[str, Any]
    grafico_rcv: dict[str, Any]
    grafico_receptores: dict[str, Any]
    grafico_proveedores: dict[str, Any]
    folios_por_tipo: list[FolioResumen]
    ultimos_documentos: list[dict[str, Any]]
    ultimos_recibidos: list[dict[str, Any]]


def get_dashboard_stats(
    request: HttpRequest,
    periodo: int | None = None,
) -> DashboardStats:
    """
    Calcula las estadísticas del dashboard para el contribuyente activo.

    `periodo` es `YYYYMM`; si no se da, se usa el mes en curso. Resuelve
    el contribuyente activo internamente (`get_current_contribuyente`) —
    quien llama no necesita saber cómo se determina el tenant actual.
    """
    contribuyente = get_current_contribuyente(request)
    # `RequireContribuyenteMiddleware` ya redirigió al wizard de alta
    # antes de llegar acá si no hubiera uno — nunca es `None` en este
    # punto para una vista autenticada real.
    assert contribuyente is not None
    periodo_actual = current_period()
    periodo = periodo or periodo_actual
    periodo_anterior = adjacent_period(periodo, -1)

    documentos_todos = DteEmitido.objects.filter(contribuyente=contribuyente)

    documentos_periodo_ventas = _documentos_de_ventas(
        documentos_todos.filter(periodo=periodo).select_related(
            'tipo_dte',
            'receptor',
        ),
    )

    total_neto = sum(
        dte.total * _sign(dte.tipo_dte) for dte in documentos_periodo_ventas
    )
    iva_neto = sum(
        dte.iva * _sign(dte.tipo_dte) for dte in documentos_periodo_ventas
    )
    con_reparos = sum(
        1
        for dte in documentos_periodo_ventas
        if _tiene_reparo(dte.revision_estado)
    )
    rechazados = sum(
        1
        for dte in documentos_periodo_ventas
        if _esta_rechazado(dte.revision_estado)
    )
    sin_envio = sum(
        1 for dte in documentos_periodo_ventas if not dte.revision_estado
    )

    # Ventas del período anterior — solo el total, para la variación
    # (`ventas_variacion_pct`). No hace falta más que eso, así que no se
    # arma la lista completa de documentos como para el período actual.
    documentos_periodo_anterior = _documentos_de_ventas(
        documentos_todos.filter(periodo=periodo_anterior).select_related(
            'tipo_dte',
        ),
    )
    total_neto_anterior = sum(
        dte.total * _sign(dte.tipo_dte) for dte in documentos_periodo_anterior
    )
    ventas_variacion_pct = (
        round(
            (total_neto - total_neto_anterior) / total_neto_anterior * 100, 1
        )
        if total_neto_anterior > 0
        else None
    )

    # Compras del período (`DteEmitido` tipo 46 y derivados + `DteRecibido`
    # — ver `services/purchases_reporter.py`) y el margen operativo
    # resultante.
    resumen_compras = purchases_service.resumen_periodo(contribuyente, periodo)
    compras_total = resumen_compras.total if resumen_compras else 0
    compras_documentos = resumen_compras.documentos if resumen_compras else 0
    margen_operativo = total_neto - compras_total

    # Documentos por mes, desglosados por tipo de DTE (gráfico apilado,
    # tendencia de todo el historial — no depende del período
    # seleccionado). Se agrupa por código (no por glosa/label, que no es
    # un campo real de la BD) y se traduce a `TipoDte.label` recién al
    # armar la serie. El monto total por período (línea superpuesta)
    # reutiliza `sales_service.periodos()` en vez de volver a sumar acá.
    documentos_venta_historico = _documentos_de_ventas(
        documentos_todos.select_related('tipo_dte'),
    )
    conteo_por_periodo_y_tipo: dict[int, dict[int, int]] = defaultdict(
        lambda: defaultdict(int),
    )
    for dte in documentos_venta_historico:
        conteo_por_periodo_y_tipo[dte.periodo][dte.tipo_dte.codigo] += 1
    tipos_dte = {tipo.codigo: tipo for tipo in TipoDte.objects.all()}
    periodos_grafico = sorted(conteo_por_periodo_y_tipo)
    codigos = sorted(
        {
            codigo
            for por_tipo in conteo_por_periodo_y_tipo.values()
            for codigo in por_tipo
        },
    )
    montos_por_periodo = {
        fila.periodo: fila.total
        for fila in sales_service.periodos(contribuyente)
    }
    grafico_periodo = {
        'etiquetas': [
            MONTHS_ABBREVIATED[p % 100 - 1] for p in periodos_grafico
        ],
        'series': [
            {
                'nombre': tipos_dte[codigo].label,
                'datos': [
                    conteo_por_periodo_y_tipo[p].get(codigo, 0)
                    for p in periodos_grafico
                ],
            }
            for codigo in codigos
        ],
        'montos': [montos_por_periodo.get(p, 0) for p in periodos_grafico],
    }

    # Ventas vs. Compras, tendencia de los últimos
    # `_MESES_TENDENCIA_VENTAS_COMPRAS` períodos con datos (de cualquiera
    # de los dos lados) — a diferencia de `grafico_periodo`, acotado: es
    # una comparación pensada para leerse de un vistazo, no un historial
    # completo.
    ventas_por_periodo = {
        fila.periodo: fila.total
        for fila in sales_service.periodos(contribuyente)
    }
    compras_por_periodo = {
        fila.periodo: fila.total
        for fila in purchases_service.periodos(contribuyente)
    }
    periodos_tendencia = sorted(
        set(ventas_por_periodo) | set(compras_por_periodo),
    )[-_MESES_TENDENCIA_VENTAS_COMPRAS:]
    grafico_ventas_compras = {
        'etiquetas': [period_label(p) for p in periodos_tendencia],
        'ventas': [ventas_por_periodo.get(p, 0) for p in periodos_tendencia],
        'compras': [compras_por_periodo.get(p, 0) for p in periodos_tendencia],
        'margen': [
            ventas_por_periodo.get(p, 0) - compras_por_periodo.get(p, 0)
            for p in periodos_tendencia
        ],
    }

    grafico_estado = {
        'etiquetas': [
            'Aceptados',
            'Con reparos',
            'Rechazados',
            'Sin información del SII',
        ],
        'datos': [
            len(documentos_periodo_ventas)
            - con_reparos
            - rechazados
            - sin_envio,
            con_reparos,
            rechazados,
            sin_envio,
        ],
    }

    # Estado RCV de los recibidos del período (doughnut, análogo a
    # `grafico_estado` pero para `DteRecibido`) — a diferencia de las
    # alertas de más abajo, sí incluye "Sin registrar en RCV" como una
    # porción más: acá interesa el cuadro completo del período, no solo
    # lo urgente.
    recibidos_periodo = DteRecibido.objects.filter(
        contribuyente=contribuyente,
        periodo=periodo,
    ).prefetch_related('rcv_eventos')
    conteo_rcv_periodo: dict[str, int] = defaultdict(int)
    for recibido in recibidos_periodo:
        conteo_rcv_periodo[
            recibido.estado_rcv() or 'Sin registrar en RCV'
        ] += 1
    grafico_rcv = {
        'etiquetas': list(_ESTADOS_RCV),
        'datos': [
            conteo_rcv_periodo.get(estado, 0) for estado in _ESTADOS_RCV
        ],
    }

    # Top 5 receptores/proveedores por monto del período — con signo
    # (una Nota de Crédito/Débito resta del receptor/proveedor al que
    # corresponde, no se suma aparte como si fuera un documento más).
    totales_por_receptor: dict[str, int] = defaultdict(int)
    for dte in documentos_periodo_ventas:
        nombre = (
            dte.receptor.razon_social
            or f'{dte.receptor.rut}-{dte.receptor.dv}'
        )
        totales_por_receptor[nombre] += dte.total * _sign(dte.tipo_dte)
    top_receptores = sorted(
        totales_por_receptor.items(),
        key=lambda fila: fila[1],
        reverse=True,
    )[:5]
    grafico_receptores = {
        'etiquetas': [nombre for nombre, _total in top_receptores],
        'datos': [total for _nombre, total in top_receptores],
    }

    totales_por_proveedor: dict[str, int] = defaultdict(int)
    for documento in purchases_service.documentos_periodo(
        contribuyente, periodo
    ):
        totales_por_proveedor[documento.contraparte] += (
            documento.total * documento.signo
        )
    top_proveedores = sorted(
        totales_por_proveedor.items(),
        key=lambda fila: fila[1],
        reverse=True,
    )[:5]
    grafico_proveedores = {
        'etiquetas': [nombre for nombre, _total in top_proveedores],
        'datos': [total for _nombre, total in top_proveedores],
    }

    # Concentración de clientes — qué tan dependiente es el período de
    # uno o pocos receptores (un cliente que hoy es el 40% de las
    # ventas es un riesgo real si se pierde, no solo una curiosidad).
    # `None` si no hay ventas netas positivas: el % no significa nada
    # sobre una base cero o negativa.
    concentracion_top1_pct = (
        round(top_receptores[0][1] / total_neto * 100, 1)
        if total_neto > 0 and top_receptores
        else None
    )
    concentracion_top3_pct = (
        round(
            sum(total for _nombre, total in top_receptores[:3])
            / total_neto
            * 100,
            1,
        )
        if total_neto > 0 and top_receptores
        else None
    )

    # Folios por tipo de documento — contador en vivo (no hay historial
    # por período), nunca sumados entre sí: folios disponibles de
    # facturas y de boletas son contadores independientes, sumarlos no
    # significa nada. `dias_restantes` estima cuánto dura ese contador al
    # ritmo de emisión reciente.
    folios_por_tipo = _folios_resumen(contribuyente)

    ultimos_documentos = [
        {
            'documento': f'{documento.tipo_dte.label} N.° {documento.folio}',
            'receptor': documento.receptor.razon_social
            or f'{documento.receptor.rut}-{documento.receptor.dv}',
            'total': documento.total,
            'fecha': documento.fecha,
        }
        for documento in documentos_todos.filter(periodo=periodo)
        .select_related('tipo_dte', 'receptor')
        .order_by('-fecha', '-folio')[:10]
    ]
    ultimos_recibidos = [
        {
            'documento': f'{recibido.tipo_dte.label} N.° {recibido.folio}',
            'emisor': recibido.emisor.razon_social
            or f'{recibido.emisor.rut}-{recibido.emisor.dv}',
            'total': recibido.total,
            'fecha': recibido.fecha,
        }
        for recibido in DteRecibido.objects.filter(
            contribuyente=contribuyente,
            periodo=periodo,
        )
        .select_related('tipo_dte', 'emisor')
        .order_by('-fecha', '-folio')[:10]
    ]

    # Alertas operativas — no dependen del período que se esté mirando,
    # son sobre el estado actual de la app.
    rechazados_pendientes = documentos_todos.filter(_RECHAZADO).count()
    dias_vencimiento_certificado = (
        contribuyente.certificado.dias_vencimiento
        if contribuyente.certificado is not None
        else None
    )
    emitidos_sin_enviar = documentos_todos.filter(revision_estado='').count()

    (
        recibidos_pendientes_rcv,
        recibidos_por_vencer_rcv,
        recibidos_rechazados_rcv,
    ) = _alertas_rcv(contribuyente)

    siguiente_candidato = adjacent_period(periodo, 1)

    return DashboardStats(
        periodo=periodo,
        periodo_glosa=period_label(periodo),
        periodo_anterior=periodo_anterior,
        periodo_siguiente=(
            siguiente_candidato
            if siguiente_candidato <= periodo_actual
            else None
        ),
        documentos=len(documentos_periodo_ventas),
        total_neto=total_neto,
        iva_neto=iva_neto,
        con_reparos=con_reparos,
        rechazados=rechazados,
        ventas_variacion_pct=ventas_variacion_pct,
        compras_total=compras_total,
        compras_documentos=compras_documentos,
        margen_operativo=margen_operativo,
        concentracion_top1_pct=concentracion_top1_pct,
        concentracion_top3_pct=concentracion_top3_pct,
        rechazados_pendientes=rechazados_pendientes,
        dias_vencimiento_certificado=dias_vencimiento_certificado,
        emitidos_sin_enviar=emitidos_sin_enviar,
        recibidos_pendientes_rcv=recibidos_pendientes_rcv,
        recibidos_por_vencer_rcv=recibidos_por_vencer_rcv,
        recibidos_rechazados_rcv=recibidos_rechazados_rcv,
        grafico_periodo=grafico_periodo,
        grafico_ventas_compras=grafico_ventas_compras,
        grafico_estado=grafico_estado,
        grafico_rcv=grafico_rcv,
        grafico_receptores=grafico_receptores,
        grafico_proveedores=grafico_proveedores,
        folios_por_tipo=folios_por_tipo,
        ultimos_documentos=ultimos_documentos,
        ultimos_recibidos=ultimos_recibidos,
    )


def _folios_resumen(contribuyente: Contribuyente) -> list[FolioResumen]:
    """
    Un `FolioResumen` por `CafFolio` del contribuyente.

    `dias_restantes` se estima del consumo real de los últimos
    `_DIAS_CONSUMO_FOLIOS` días, sin distinguir venta/compra: un folio
    de Factura de Compra (tipo 46) consume el mismo contador que
    cualquier otra Factura, así que también cuenta acá.
    """
    hace_30_dias = timezone.localdate() - timedelta(days=_DIAS_CONSUMO_FOLIOS)
    consumo_reciente = dict(
        DteEmitido.objects.filter(
            contribuyente=contribuyente,
            fecha__gte=hace_30_dias,
        )
        .values('tipo_dte_id')
        .annotate(cantidad=Count('id'))
        .values_list('tipo_dte_id', 'cantidad'),
    )

    resumen = []
    for caf_folio in (
        CafFolio.objects.filter(contribuyente=contribuyente)
        .select_related('tipo_dte')
        .order_by('tipo_dte__codigo')
    ):
        tasa_diaria = (
            consumo_reciente.get(caf_folio.tipo_dte_id, 0)
            / _DIAS_CONSUMO_FOLIOS
        )
        resumen.append(
            FolioResumen(
                tipo_dte=caf_folio.tipo_dte,
                disponibles=caf_folio.disponibles,
                siguiente=caf_folio.siguiente,
                alerta=caf_folio.alerta,
                dias_restantes=(
                    round(caf_folio.disponibles / tasa_diaria)
                    if tasa_diaria > 0
                    else None
                ),
            ),
        )
    return resumen


def _alertas_rcv(contribuyente: Contribuyente) -> tuple[int, int, int]:
    """
    `(pendientes, por_vencer, rechazados)` de los `DteRecibido` del RUT.

    Global (no depende del período que se esté mirando) — acotado a los
    que ya tienen `fecha_registro_rcv` (sin eso, `estado_rcv()` es
    `None`, no puede ser ninguno de los tres). `por_vencer` es un
    subconjunto de `pendientes`: ya pasaron `_DIAS_PLAZO_RCV -
    _DIAS_ALERTA_RCV_RESTANTES` días desde el registro sin que nadie lo
    haya revisado, a punto de aceptarse tácitamente sin que nadie lo
    haya mirado.
    """
    pendientes = 0
    por_vencer = 0
    rechazados = 0
    ahora = timezone.now()
    umbral_alerta = timedelta(
        days=_DIAS_PLAZO_RCV - _DIAS_ALERTA_RCV_RESTANTES,
    )

    recibidos = DteRecibido.objects.filter(
        contribuyente=contribuyente,
        fecha_registro_rcv__isnull=False,
    ).prefetch_related('rcv_eventos')
    for recibido in recibidos:
        # El filtro `fecha_registro_rcv__isnull=False` de arriba ya lo
        # garantiza — django-stubs no propaga esa garantía al tipo del
        # campo.
        assert recibido.fecha_registro_rcv is not None
        estado = recibido.estado_rcv()
        if estado == 'Pendiente':
            pendientes += 1
            if ahora >= recibido.fecha_registro_rcv + umbral_alerta:
                por_vencer += 1
        elif estado == 'Rechazado':
            rechazados += 1

    return pendientes, por_vencer, rechazados
