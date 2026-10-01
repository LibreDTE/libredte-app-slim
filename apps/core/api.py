"""
Clases base de la API pensada para clientes externos.

Heredar de acá es lo único que abre una vista a un cliente externo: el
default del proyecto es solo sesión (ver `REST_FRAMEWORK` en
`config/settings.py`). Hoy lo heredan todas las vistas de
`apps/*/api/views.py`, pero sigue siendo explícito a propósito — una
vista nueva nace cerrada, y publicarla se lee en su propia declaración.

`SessionAuthentication` va además de `TokenAuthentication` porque esas
mismas vistas son las que consume el JS de la app (Tabulator) con la
sesión ya iniciada.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework.authentication import (
    BaseAuthentication,
    SessionAuthentication,
    TokenAuthentication,
)
from rest_framework.permissions import IsAuthenticated

if TYPE_CHECKING:
    # Solo existe en los stubs (`rest_framework-stubs/permissions.pyi`),
    # no en el paquete real. Es el tipo con el que `APIView` declara el
    # atributo: anotarlo igual acá es lo que evita el choque de
    # definiciones entre las dos bases al mezclar el mixin.
    from rest_framework.permissions import _PermissionClass


class PublicApiMixin:
    """Autenticación y permisos de toda vista de la API pública."""

    authentication_classes: Sequence[type[BaseAuthentication]] = [
        TokenAuthentication,
        SessionAuthentication,
    ]
    permission_classes: Sequence[_PermissionClass] = [IsAuthenticated]


def tabulator_parameters(campos: Sequence[str]) -> list[OpenApiParameter]:
    """
    Parámetros de consulta de un listado paginado con Tabulator.

    `campos` son los nombres que ESE endpoint acepta en `filter`/`sort`
    — varios no son campos del modelo sino calculados del serializer
    (ver el mapeo de cada vista). Se documenta el índice `0`; Tabulator
    encadena varios subiéndolo (`filter[1][field]`, ...), que OpenAPI
    no sabe expresar como familia de parámetros.
    """
    campos_texto = '`' + '`, `'.join(campos) + '`'
    return [
        OpenApiParameter(
            'page',
            OpenApiTypes.INT,
            description='Página pedida, empezando en 1.',
        ),
        OpenApiParameter(
            'size',
            OpenApiTypes.INT,
            description='Filas por página.',
        ),
        OpenApiParameter(
            'filter[0][field]',
            OpenApiTypes.STR,
            enum=list(campos),
            description=f'Campo a filtrar: {campos_texto}.',
        ),
        OpenApiParameter(
            'filter[0][value]',
            OpenApiTypes.STR,
            description='Texto buscado en el campo filtrado.',
        ),
        OpenApiParameter(
            'sort[0][field]',
            OpenApiTypes.STR,
            enum=list(campos),
            description=f'Campo por el que ordenar: {campos_texto}.',
        ),
        OpenApiParameter(
            'sort[0][dir]',
            OpenApiTypes.STR,
            enum=['asc', 'desc'],
            description='Sentido del orden.',
        ),
    ]
