"""Administración de Django para los modelos de `libredte`."""

from __future__ import annotations

from django.contrib import admin

from apps.core.admin import ReadOnlyModelAdmin

from .models import (
    ActividadEconomica,
    Certificado,
    Comuna,
    Contribuyente,
    ContribuyenteActividadEconomica,
    Pais,
    Sucursal,
)


@admin.register(Pais)
class PaisAdmin(ReadOnlyModelAdmin):
    list_display = ('codigo', 'glosa')
    search_fields = ('codigo', 'glosa')


@admin.register(Comuna)
class ComunaAdmin(ReadOnlyModelAdmin):
    list_display = ('codigo', 'glosa')
    search_fields = ('codigo', 'glosa')


@admin.register(ActividadEconomica)
class ActividadEconomicaAdmin(ReadOnlyModelAdmin):
    list_display = ('codigo', 'glosa', 'afecta_iva')
    list_filter = ('afecta_iva',)
    search_fields = ('codigo', 'glosa')


@admin.register(Certificado)
class CertificadoAdmin(ReadOnlyModelAdmin):
    """
    `x509`/`clave_privada` nunca se muestran, ni siquiera de solo lectura.

    La llave privada es sensible aunque esté cifrada en reposo — el
    único flujo correcto para verla/reemplazarla es `certificate
    _manager.py` (vía la API real, que valida el `.p12`).
    """

    list_display = (
        'certificado_id',
        'nombre',
        'usuario',
        'email',
        'issuer',
        'valido_desde',
        'valido_hasta',
    )
    list_filter = ('issuer',)
    search_fields = ('certificado_id', 'nombre', 'email', 'usuario__username')
    date_hierarchy = 'valido_hasta'
    exclude = ('x509', 'clave_privada')


@admin.register(Contribuyente)
class ContribuyenteAdmin(ReadOnlyModelAdmin):
    list_display = (
        'rut',
        'dv',
        'razon_social',
        'usuario',
        'ambiente',
        'comuna',
    )
    search_fields = ('rut', 'razon_social', 'usuario__username')


@admin.register(ContribuyenteActividadEconomica)
class ContribuyenteActividadEconomicaAdmin(ReadOnlyModelAdmin):
    list_display = ('contribuyente', 'actividad_economica', 'es_principal')
    list_filter = ('es_principal',)
    search_fields = (
        'contribuyente__razon_social',
        'actividad_economica__glosa',
    )


@admin.register(Sucursal)
class SucursalAdmin(ReadOnlyModelAdmin):
    list_display = (
        'contribuyente',
        'nombre',
        'es_matriz',
        'codigo_sii',
        'comuna',
    )
    list_filter = ('es_matriz', 'comuna')
    search_fields = ('contribuyente__razon_social', 'nombre')
