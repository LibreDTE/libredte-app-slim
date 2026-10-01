"""
Servicio: render de un documento a HTML/PDF.

Único módulo que llama a `document.renderer` del SDK — nada fuera de
`services/*.py` debe tocarlo directamente.
"""

from __future__ import annotations

import base64
import mimetypes
from typing import Any

from libredte_lib_sdk.billing.document import RenderedDocument
from libredte_lib_sdk.exceptions import LibreDteSdkError

from apps.libredte.models import Contribuyente
from apps.libredte.services.exceptions import wrap
from apps.libredte.services.libredte_backend import get_backend

from ..models import Borrador, DteEmitido, DteRecibido


def render_html(documento: DteEmitido | Borrador | DteRecibido) -> bytes:
    """
    HTML del documento, listo para mostrar (UTF-8).

    Sirve para un `DteEmitido`/`Borrador`/`DteRecibido` — los tres
    tienen `xml_base64`, y el renderizador solo necesita eso (más el
    logo, si corresponde — ver `_libredte_data()`).
    """
    try:
        with get_backend(documento.contribuyente) as backend:
            resultado = backend.billing.document.renderer.render(
                documento.xml_base64,
                format='html',
                libredte_data=_libredte_data(documento),
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error
    return resultado.first.content_bytes


def render_pdf(
    documento: DteEmitido | Borrador | DteRecibido,
) -> RenderedDocument:
    """PDF del documento — trae `content_bytes`/`mime_type`/`filename`."""
    try:
        with get_backend(documento.contribuyente) as backend:
            resultado = backend.billing.document.renderer.render(
                documento.xml_base64,
                format='pdf',
                libredte_data=_libredte_data(documento),
            )
    except LibreDteSdkError as error:
        raise wrap(error) from error
    return resultado.first


def _libredte_data(
    documento: DteEmitido | Borrador | DteRecibido,
) -> dict[str, Any] | None:
    """
    `logo` del emisor para la plantilla, si corresponde.

    No es un dato del XML del SII, la librería lo agrega vía
    `libredte_data['extra']['dte']` (ver `Emisor::setLogo()`/
    `estandar.html.twig` en `libredte-lib-core`). Un `DteEmitido`/
    `Borrador` usa el logo de `contribuyente` (el emisor real, somos
    nosotros). Un `DteRecibido` no: el emisor real es un tercero
    (`Emisor`), que no guarda logo — se renderiza sin logo, la
    plantilla ya maneja la ausencia (`{% if document.logo is not
    empty %}`).
    """
    if isinstance(documento, DteRecibido):
        return None
    logo = _logo_data_uri(documento.contribuyente)
    if logo is None:
        return None
    return {'extra': {'dte': {'logo': logo}}}


def _logo_data_uri(contribuyente: Contribuyente) -> str | None:
    """
    Logo del contribuyente como `data:` URI (`data:<mime>;base64,...`).

    Un data URI, no una URL: el renderizado ocurre del lado de la API,
    que no tiene forma de alcanzar `MEDIA_URL` de este servidor — el
    logo tiene que viajar autocontenido en la llamada.
    """
    if not contribuyente.logo:
        return None
    nombre_archivo = contribuyente.logo.name
    assert nombre_archivo is not None  # `logo` ya truthy arriba.
    mime_type, _ = mimetypes.guess_type(nombre_archivo)
    with contribuyente.logo.open('rb') as archivo:
        contenido = base64.b64encode(archivo.read()).decode('ascii')
    return f'data:{mime_type or "image/png"};base64,{contenido}'
