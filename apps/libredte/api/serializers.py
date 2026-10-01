"""Serializers de la API (JSON) de `libredte`."""

from __future__ import annotations

from django.urls import reverse
from rest_framework import serializers

from apps.core.utils import action_buttons

from ..models import Sucursal


class SucursalSerializer(serializers.ModelSerializer[Sucursal]):
    """Fila de "Sucursales", para el listado de Tabulator."""

    nombre = serializers.SerializerMethodField()
    codigo_sii = serializers.SerializerMethodField()
    es_matriz = serializers.SerializerMethodField()
    comuna = serializers.CharField(source='comuna.glosa', read_only=True)
    acciones = serializers.SerializerMethodField()

    class Meta:
        model = Sucursal
        fields = [
            'id',
            'nombre',
            'codigo_sii',
            'es_matriz',
            'direccion',
            'comuna',
            'acciones',
        ]

    def get_nombre(self, sucursal: Sucursal) -> str:
        """Nombre, o un guion si no tiene (ej. la casa matriz)."""
        return sucursal.nombre or '—'

    def get_codigo_sii(self, sucursal: Sucursal) -> str:
        """Código SII, o un guion si todavía no se le asignó uno."""
        return str(sucursal.codigo_sii) if sucursal.codigo_sii else '—'

    def get_es_matriz(self, sucursal: Sucursal) -> str:
        """Sí/No — mismo criterio que la UI anterior."""
        return 'Sí' if sucursal.es_matriz else 'No'

    def get_acciones(self, sucursal: Sucursal) -> str:
        """Editar / eliminar."""
        return action_buttons(
            (
                'Editar',
                'pen',
                reverse(
                    'libredte_settings:sucursal_editar',
                    args=[sucursal.pk],
                ),
                'primary',
            ),
            (
                'Eliminar',
                'trash',
                reverse(
                    'libredte_settings:sucursal_eliminar',
                    args=[sucursal.pk],
                ),
                'danger',
            ),
        )
