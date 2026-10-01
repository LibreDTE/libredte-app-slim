"""Administración de Django para los modelos de `billing`."""

from __future__ import annotations

from django.contrib import admin

from apps.core.admin import ReadOnlyModelAdmin, ReadOnlyTabularInline

from .models import (
    AduanaClausulaVenta,
    AduanaFormaPago,
    AduanaModalidadVenta,
    AduanaMoneda,
    AduanaPuerto,
    AduanaTipoBulto,
    AduanaTransporte,
    AduanaUnidad,
    Borrador,
    Caf,
    CafFolio,
    DteEmitido,
    DteEmitidoReferencia,
    DteRecibido,
    DteRecibidoRcvEvento,
    Emisor,
    FormaPago,
    ImpuestoAdicionalRetencion,
    Item,
    ItemCategoria,
    MedioPago,
    Receptor,
    TipoDte,
    Traslado,
)


class CodigoGlosaAdmin(ReadOnlyModelAdmin):
    """Catálogo simple `codigo`/`glosa` (SII o Aduana), sin edición ni baja."""

    list_display = ('codigo', 'glosa')
    search_fields = ('codigo', 'glosa')


@admin.register(Traslado)
class TrasladoAdmin(CodigoGlosaAdmin):
    pass


@admin.register(FormaPago)
class FormaPagoAdmin(CodigoGlosaAdmin):
    pass


@admin.register(AduanaFormaPago)
class AduanaFormaPagoAdmin(CodigoGlosaAdmin):
    pass


@admin.register(MedioPago)
class MedioPagoAdmin(CodigoGlosaAdmin):
    pass


@admin.register(AduanaTransporte)
class AduanaTransporteAdmin(CodigoGlosaAdmin):
    pass


@admin.register(AduanaModalidadVenta)
class AduanaModalidadVentaAdmin(CodigoGlosaAdmin):
    pass


@admin.register(AduanaClausulaVenta)
class AduanaClausulaVentaAdmin(CodigoGlosaAdmin):
    pass


@admin.register(AduanaUnidad)
class AduanaUnidadAdmin(CodigoGlosaAdmin):
    pass


@admin.register(AduanaPuerto)
class AduanaPuertoAdmin(CodigoGlosaAdmin):
    pass


@admin.register(AduanaTipoBulto)
class AduanaTipoBultoAdmin(CodigoGlosaAdmin):
    pass


@admin.register(AduanaMoneda)
class AduanaMonedaAdmin(ReadOnlyModelAdmin):
    list_display = ('codigo', 'glosa', 'codigo_iso')
    search_fields = ('codigo', 'glosa')


@admin.register(ImpuestoAdicionalRetencion)
class ImpuestoAdicionalRetencionAdmin(ReadOnlyModelAdmin):
    list_display = ('codigo', 'glosa', 'tipo', 'tasa')
    list_filter = ('tipo',)
    search_fields = ('codigo', 'glosa')


@admin.register(TipoDte)
class TipoDteAdmin(ReadOnlyModelAdmin):
    list_display = (
        'codigo',
        'glosa',
        'glosa_corta',
        'categoria',
        'operacion',
        'compra',
        'venta',
        'cedible',
    )
    list_filter = ('categoria', 'operacion', 'compra', 'venta', 'cedible')
    search_fields = ('codigo', 'glosa', 'glosa_corta')


@admin.register(ItemCategoria)
class ItemCategoriaAdmin(ReadOnlyModelAdmin):
    list_display = ('nombre', 'contribuyente', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre', 'contribuyente__razon_social')


@admin.register(Item)
class ItemAdmin(ReadOnlyModelAdmin):
    list_display = (
        'nombre',
        'codigo',
        'contribuyente',
        'categoria',
        'precio',
        'bruto',
        'activo',
    )
    list_filter = ('activo', 'bruto', 'categoria')
    search_fields = ('nombre', 'codigo', 'contribuyente__razon_social')


@admin.register(Receptor)
class ReceptorAdmin(ReadOnlyModelAdmin):
    list_display = ('rut', 'dv', 'razon_social', 'contribuyente', 'pais')
    list_filter = ('pais',)
    search_fields = ('rut', 'razon_social', 'contribuyente__razon_social')


@admin.register(Emisor)
class EmisorAdmin(ReadOnlyModelAdmin):
    list_display = ('rut', 'dv', 'razon_social', 'contribuyente', 'pais')
    list_filter = ('pais',)
    search_fields = ('rut', 'razon_social', 'contribuyente__razon_social')


@admin.register(CafFolio)
class CafFolioAdmin(ReadOnlyModelAdmin):
    list_display = (
        'contribuyente',
        'tipo_dte',
        'siguiente',
        'disponibles',
        'alerta',
        'alertado',
    )
    list_filter = ('alertado', 'tipo_dte')
    search_fields = ('contribuyente__razon_social',)


@admin.register(Caf)
class CafAdmin(ReadOnlyModelAdmin):
    list_display = (
        'contribuyente',
        'tipo_dte',
        'desde',
        'hasta',
        'fecha_autorizacion',
        'fecha_vencimiento',
    )
    list_filter = ('tipo_dte',)
    search_fields = ('contribuyente__razon_social',)
    date_hierarchy = 'fecha_autorizacion'


class DteEmitidoReferenciaInline(ReadOnlyTabularInline):
    model = DteEmitidoReferencia
    fk_name = 'emitido'


@admin.register(DteEmitido)
class DteEmitidoAdmin(ReadOnlyModelAdmin):
    list_display = (
        'tipo_dte',
        'folio',
        'contribuyente',
        'receptor',
        'fecha',
        'total',
        'revision_estado',
    )
    list_filter = ('tipo_dte', 'revision_estado')
    search_fields = (
        'folio',
        'contribuyente__razon_social',
        'receptor__razon_social',
        'track_id',
    )
    date_hierarchy = 'fecha'
    ordering = ('-fecha',)
    inlines = (DteEmitidoReferenciaInline,)


class DteRecibidoRcvEventoInline(ReadOnlyTabularInline):
    model = DteRecibidoRcvEvento


@admin.register(DteRecibido)
class DteRecibidoAdmin(ReadOnlyModelAdmin):
    list_display = (
        'tipo_dte',
        'folio',
        'contribuyente',
        'emisor',
        'fecha',
        'total',
    )
    list_filter = ('tipo_dte',)
    search_fields = (
        'folio',
        'contribuyente__razon_social',
        'emisor__razon_social',
    )
    date_hierarchy = 'fecha'
    ordering = ('-fecha',)
    inlines = (DteRecibidoRcvEventoInline,)


@admin.register(Borrador)
class BorradorAdmin(ReadOnlyModelAdmin):
    list_display = (
        'tipo_dte',
        'contribuyente',
        'receptor',
        'fecha',
        'total',
        'fecha_hora_creacion',
    )
    list_filter = ('tipo_dte',)
    search_fields = ('contribuyente__razon_social', 'receptor__razon_social')
    date_hierarchy = 'fecha'
