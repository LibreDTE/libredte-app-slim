"""
Servicio: intercambio de documentos — carga un sobre `EnvioDTE` recibido.

Modela el flujo real de recepción del SII: un proveedor envía por
correo el XML del sobre `EnvioDTE` (no un DTE suelto), y ese sobre
puede agrupar más de un documento. `load_xml()` recibe únicamente ese
XML y hace todo lo demás puertas adentro: lo procesa como sobre
(`dispatcher.load_xml()`, que ya descompone el sobre en una bolsa por
documento), resuelve (o crea) el `Emisor` de cada uno y genera un
`DteRecibido` por documento.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import TYPE_CHECKING, Any

from libredte_lib_sdk.exceptions import LibreDteSdkError

from apps.libredte.models import Comuna, Contribuyente
from apps.libredte.services.exceptions import wrap
from apps.libredte.services.libredte_backend import get_backend

from ..models import DteRecibido, Emisor, TipoDte
from ..utils.dte import montos_en_clp

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.contrib.auth.models import User
    from libredte_lib_sdk.billing.trading_parties import Certificate


def load_xml(
    contribuyente: Contribuyente,
    xml_base64: str,
    usuario: User,
) -> list[DteRecibido]:
    """
    Carga un sobre `EnvioDTE` y persiste un `DteRecibido` por documento.

    El emisor de cada documento se resuelve por RUT (`_resolver_emisor()`)
    y se actualiza con los datos de este envío — nunca se busca por
    `codigo_interno`, ese campo no tiene representación en el XML del
    DTE.
    """
    try:
        with get_backend(contribuyente) as backend:
            sobre = backend.billing.document.dispatcher.load_xml(xml_base64)
    except LibreDteSdkError as error:
        raise wrap(error) from error

    recibidos = []
    for bag in sobre.documents:
        encabezado = bag.require_document()['Encabezado']
        emisor = _resolver_emisor(contribuyente, encabezado['Emisor'])
        tipo_dte = TipoDte.objects.get(codigo=encabezado['IdDoc']['TipoDTE'])
        fecha = date.fromisoformat(encabezado['IdDoc']['FchEmis'])
        neto, exento, iva, total = montos_en_clp(encabezado)

        recibidos.append(
            DteRecibido.objects.create(
                contribuyente=contribuyente,
                tipo_dte=tipo_dte,
                emisor=emisor,
                usuario=usuario,
                folio=encabezado['IdDoc']['Folio'],
                periodo=fecha.year * 100 + fecha.month,
                fecha=fecha,
                neto=neto,
                exento=exento,
                iva=iva,
                total=total,
                xml_base64=bag.xml_base64,
            ),
        )
    return recibidos


def build_fake_sobre(
    documentos_data: Sequence[tuple[dict[str, Any], str]],
    *,
    autorizacion_dte_resolucion_fecha: date,
    autorizacion_dte_resolucion_numero: int,
    certificate: Certificate,
) -> str:
    """
    Arma, timbra y envuelve 1+ documentos en un único sobre `EnvioDTE`.

    No requiere un `Contribuyente` propio — el emisor puede ser
    cualquiera. Solo para generar datos de prueba: el flujo real de
    recepción nunca arma un sobre, siempre lo recibe ya armado
    (`load_xml()`). Devuelve el XML del sobre en base64, listo para
    pasarle a `load_xml()`.

    `documentos_data` es una lista de `(document_data, caf_xml)` — un
    documento puede necesitar un CAF distinto al de otro (folio/tipo
    DTE distinto), pero todos comparten emisor/certificado/
    autorización: es el mismo proveedor enviando su propio sobre.
    Siempre se despacha con `create_many()`, incluso para un solo
    documento — no hay dos caminos de código para 1 vs 2+ documentos.

    `autorizacion_dte` no es un dato del DTE (`DocumentBuilderService
    .build_signed()` no lo pide, y `Emisor.toArray()` lo entrega
    `None`) — es un dato de la relación SII-emisor, propio de la
    carátula del sobre. Se agrega recién acá, sobre cada bolsa ya
    construida, sin tocar el XML ya firmado del documento.
    """
    autorizacion_dte = {
        'fecha_resolucion': autorizacion_dte_resolucion_fecha.isoformat(),
        'numero_resolucion': autorizacion_dte_resolucion_numero,
    }
    try:
        with get_backend() as backend:
            bags = []
            for document_data, caf_xml in documentos_data:
                bag = backend.billing.document.builder.build_signed(
                    document_data,
                    caf_xml=caf_xml,
                    certificate=certificate,
                )
                # `emisor` siempre viene poblado tras un build exitoso
                # (ver docstring de `DocumentBag`) — el tipo es
                # `Optional` solo porque la bolsa también puede
                # representar un documento todavía sin construir.
                assert bag.emisor is not None
                bags.append(
                    dataclasses.replace(
                        bag,
                        emisor={
                            **bag.emisor,
                            'autorizacion_dte': autorizacion_dte,
                        },
                    ),
                )
            sobre = backend.billing.document.dispatcher.create_many(bags)
    except LibreDteSdkError as error:
        raise wrap(error) from error
    return sobre.xml_base64


def _resolver_emisor(
    contribuyente: Contribuyente,
    emisor_data: dict[str, Any],
) -> Emisor:
    """
    Busca el `Emisor` de `contribuyente` por RUT y actualiza sus datos.

    Siempre sobrescribe los datos de un `Emisor` ya existente con los
    de este documento (ver docstring de `Emisor`: quien manda estos
    datos en cada envío es el propio emisor, no algo que el
    contribuyente mantenga fijo) — mismo criterio que
    `biller._resolver_receptor()`, salvo que acá no hay `CdgIntRecep`
    equivalente: el RUT es la única llave de búsqueda.
    """
    rut, dv = _rut_dv(emisor_data['RUTEmisor'])

    comuna = None
    if emisor_data.get('CmnaOrigen'):
        comuna = Comuna.objects.filter(
            glosa__iexact=emisor_data['CmnaOrigen'],
        ).first()

    datos = {
        'razon_social': emisor_data.get('RznSoc') or '',
        'giro': emisor_data.get('GiroEmis') or '',
        'telefono': emisor_data.get('Telefono') or '',
        'correo': emisor_data.get('CorreoEmisor') or '',
        'direccion': emisor_data.get('DirOrigen') or '',
        'comuna': comuna,
        'ciudad': emisor_data.get('CiudadOrigen') or '',
    }

    emisor, creado = Emisor.objects.get_or_create(
        contribuyente=contribuyente,
        rut=rut,
        dv=dv,
        defaults=datos,
    )
    if not creado:
        for campo, valor in datos.items():
            setattr(emisor, campo, valor)
        emisor.save()
    return emisor


def _rut_dv(rut_con_dv: str) -> tuple[int, str]:
    """`(rut, dv)` desde un RUT con el formato `NNNNNNNN-D` del DTE."""
    rut, dv = rut_con_dv.split('-')
    return int(rut), dv
