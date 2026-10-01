"""Vistas de la API (JSON) de `libredte`."""

from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView
from rest_framework_tabulator import (
    TabulatorFilterBackend,
    TabulatorPagination,
)

from apps.core.api import PublicApiMixin, tabulator_parameters

from ..models import Sucursal
from ..tenancy import get_current_contribuyente
from .serializers import SucursalSerializer

_SUCURSAL_CAMPOS = ['nombre', 'codigo_sii', 'direccion', 'comuna']


@extend_schema(
    tags=['Sucursales'],
    summary='Listar sucursales',
    description=(
        'Sucursales del contribuyente activo, incluida la casa matriz.'
    ),
    parameters=tabulator_parameters(_SUCURSAL_CAMPOS),
)
class SucursalListView(PublicApiMixin, ListAPIView[Sucursal]):
    """Sucursales del contribuyente activo, para Tabulator."""

    serializer_class = SucursalSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    # `comuna`/`acciones` son calculados del serializer (glosa de la
    # FK, botones); `es_matriz` no es filtrable: es un `BooleanField`,
    # el header filter de texto de las demás columnas no tiene ningún
    # valor de texto que le calce bien.
    _LOOKUP_MAP = {
        'nombre': 'nombre',
        'codigo_sii': 'codigo_sii',
        'direccion': 'direccion',
        'comuna': 'comuna__glosa',
    }
    filterset_fields = _LOOKUP_MAP
    ordering_fields = {**_LOOKUP_MAP, 'es_matriz': 'es_matriz'}

    def get_queryset(self) -> QuerySet[Sucursal]:
        """Sucursales del contribuyente activo."""
        contribuyente = get_current_contribuyente(self.request)
        return (
            Sucursal.objects.filter(contribuyente=contribuyente)
            .select_related('comuna')
            .order_by('-es_matriz', 'nombre')
        )
