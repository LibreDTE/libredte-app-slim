"""
El esquema OpenAPI de la API pública se genera y está documentado.

No importa ningún modelo de dominio: recorre el `urlconf` y el esquema
ya generado, así que sigue viviendo en `core` pese a cubrir endpoints
de `billing` y `libredte`.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import resolve, reverse

pytestmark = pytest.mark.django_db


@pytest.fixture
def schema(client: Client) -> dict[str, Any]:
    """
    El esquema tal como se sirve, no uno generado aparte.

    Necesita un `User` en la base —cualquiera— porque
    `RequireInitialUserMiddleware` desvía cualquier página al alta del
    primer usuario mientras no exista ninguno.
    """
    User.objects.create_user('demo', password='demo12345')
    respuesta = client.get(reverse('api_schema'), {'format': 'json'})

    assert respuesta.status_code == 200

    parseado: dict[str, Any] = json.loads(respuesta.content)
    return parseado


def _operaciones(schema: dict[str, Any]) -> list[tuple[str, Any]]:
    return [
        (ruta, operacion)
        for ruta, metodos in schema['paths'].items()
        for operacion in metodos.values()
    ]


def _campos_documentados(operacion: Any) -> list[str] | None:
    """El `enum` de `filter[0][field]`, o `None` si no es un listado."""
    for parametro in operacion.get('parameters', []):
        if parametro['name'] == 'filter[0][field]':
            enum: list[str] | None = parametro.get('schema', {}).get('enum')
            return enum
    return None


def _campos_reales(ruta: str) -> list[str] | None:
    """`filterset_fields` de la vista que atiende `ruta`, si los tiene."""
    cls = getattr(resolve(ruta).func, 'cls', None)
    campos = getattr(cls, 'filterset_fields', None)
    return list(campos) if campos else None


def test_every_endpoint_is_documented(schema: dict[str, Any]) -> None:
    """Ninguna vista queda publicada sin resumen, descripción ni tag."""
    sin_documentar = [
        ruta
        for ruta, op in _operaciones(schema)
        if not op.get('summary')
        or not op.get('description')
        or not op.get('tags')
    ]

    assert not sin_documentar


def test_the_token_is_the_only_documented_scheme(
    schema: dict[str, Any],
) -> None:
    """
    Quien lea la doc ve una sola forma de autenticarse: el token.

    `SessionAuthentication` sigue activa en las vistas (la usa el JS de
    la app), pero documentarla agregaba un `cookieAuth` inservible para
    un cliente externo — se excluye con `AUTHENTICATION_WHITELIST`.
    """
    esquemas = schema['components']['securitySchemes']

    assert list(esquemas) == ['tokenAuth']
    assert esquemas['tokenAuth']['type'] == 'apiKey'
    assert esquemas['tokenAuth']['in'] == 'header'
    assert esquemas['tokenAuth']['name'] == 'Authorization'

    for _ruta, operacion in _operaciones(schema):
        assert operacion.get('security') == [{'tokenAuth': []}]


def test_no_filterable_field_is_left_undocumented(
    schema: dict[str, Any],
) -> None:
    """
    Todo campo de `filterset_fields` aparece en la documentación.

    Es lo único que impide que `@extend_schema` y `filterset_fields` se
    separen con el tiempo: la lista de campos está escrita dos veces
    (cuando corre el decorador, la clase todavía no existe).

    La comprobación es de inclusión y no de igualdad porque un listado
    puede aceptar un filtro que no sale de `filterset_fields`: en
    `/api/borradores/`, `codigo` es un `@property` de `Borrador` y se
    filtra a mano (ver `BorradorListView._filtrar_por_codigo`).
    """
    faltantes = []
    for ruta, operacion in _operaciones(schema):
        documentados = _campos_documentados(operacion)
        reales = _campos_reales(ruta)
        if documentados is None or reales is None:
            continue
        sin_documentar = set(reales) - set(documentados)
        if sin_documentar:
            faltantes.append((ruta, sorted(sin_documentar)))

    assert not faltantes


def test_the_documentation_pages_are_served(client: Client) -> None:
    """Esquema, Swagger y ReDoc responden sin sesión iniciada."""
    User.objects.create_user('demo', password='demo12345')

    for nombre in ('api_schema', 'api_docs', 'api_redoc'):
        respuesta = client.get(reverse(nombre))

        assert respuesta.status_code == 200, nombre
