"""Vistas de `billing` fuera de Configuración."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError, QuerySet
from django.forms import BaseFormSet, Form
from django.forms.utils import ErrorDict
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, UpdateView

from apps.core.auth import require_authenticated_user
from apps.core.sudo import RequiresSudoMixin
from apps.libredte.plugins.contracts import SiiBackendError
from apps.libredte.services.exceptions import ServiceError
from apps.libredte.services.sii_backend import get_backend, upsell_context
from apps.libredte.tenancy import (
    get_current_contribuyente,
    require_current_contribuyente,
)

from .. import tasks
from ..forms import (
    DocumentoForm,
    EmisionMasivaForm,
    EmitidoXmlUploadForm,
    ItemForm,
    ItemFormSet,
    PagoForm,
    PagoFormSet,
    RcvCompraPeriodoForm,
    RcvPeriodoForm,
    ReceptorForm,
    RecibidoSobreUploadForm,
    ReferenciaForm,
    ReferenciaFormSet,
)
from ..models import (
    Borrador,
    DteEmitido,
    DteRecibido,
    Emisor,
    Receptor,
    TipoDte,
)
from ..services import (
    biller,
    bulk_biller,
    document_dispatcher,
    document_renderer,
)
from ..services import purchases_reporter as purchases_service
from ..services import sales_reporter as sales_service
from ..utils.period import period_label


@login_required
def emitidos(request: HttpRequest) -> HttpResponse:
    """
    Documentos emitidos por el contribuyente activo.

    A diferencia de `folios` (el único listado que sigue con tabla
    embebida), esta vista no arma `filas`/`columnas`: Tabulator las pide
    directo a `billing_api:emitidos` (paginación/filtro/orden en el
    servidor, ver `billing.api.views.DteEmitidoListView`) — el volumen
    de documentos emitidos crece sin límite, a diferencia de `folios`,
    que rara vez pasa de unas pocas decenas de filas.
    """
    return render(request, 'billing/emitidos.html')


@login_required
def emitido_subir(request: HttpRequest) -> HttpResponse:
    """Registra un DTE ya emitido por otro medio, a partir de su XML."""
    contribuyente = get_current_contribuyente(request)
    form = EmitidoXmlUploadForm(
        request.POST or None,
        request.FILES or None,
        contribuyente=contribuyente,
        usuario=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            documento = form.save()
        except ServiceError as error:
            form.add_error('archivo', str(error))
        else:
            messages.success(request, 'Documento emitido registrado.')
            return redirect('billing:emitido_detalle', pk=documento.pk)

    return render(request, 'billing/emitido_subir.html', {'form': form})


@login_required
def emitido_detalle(request: HttpRequest, pk: int) -> HttpResponse:
    """Detalle de un documento emitido: receptor, totales, XML."""
    contribuyente = get_current_contribuyente(request)
    documento = get_object_or_404(
        DteEmitido.objects.select_related('tipo_dte', 'receptor', 'usuario'),
        pk=pk,
        contribuyente=contribuyente,
    )
    return render(
        request,
        'billing/emitido_detalle.html',
        {
            'documento': documento,
            'detalle_items': _detalle_items_desde_xml(documento.xml),
        },
    )


_XML_NAMESPACES = {'sii': 'http://www.sii.cl/SiiDte'}


def _detalle_items_desde_xml(
    xml_text: str,
) -> list[dict[str, str | int | None]]:
    """
    Ítems del `Detalle` de un DTE, para mostrar en su detalle.

    Parseo liviano y de solo lectura del XML ya guardado (no llama a
    la API ni recalcula nada) — mismo dato que `Borrador.datos
    .Detalle` ya trae parseado de fábrica, pero acá no hay un JSON
    guardado aparte, solo el XML final.
    """
    raiz = ET.fromstring(xml_text)
    items = []
    for detalle in raiz.findall('.//sii:Detalle', _XML_NAMESPACES):
        precio = detalle.findtext('sii:PrcItem', namespaces=_XML_NAMESPACES)
        items.append(
            {
                'nombre': detalle.findtext(
                    'sii:NmbItem',
                    default='',
                    namespaces=_XML_NAMESPACES,
                ),
                'cantidad': detalle.findtext(
                    'sii:QtyItem',
                    namespaces=_XML_NAMESPACES,
                ),
                'precio': int(float(precio)) if precio else None,
            }
        )
    return items


@login_required
def emitido_descargar_xml(request: HttpRequest, pk: int) -> HttpResponse:
    """Descarga el XML real (el que devolvió la API al timbrar/firmar)."""
    contribuyente = require_current_contribuyente(request)
    documento = get_object_or_404(
        DteEmitido.objects.select_related('tipo_dte'),
        pk=pk,
        contribuyente=contribuyente,
    )
    # Mismo padding de folio (10 dígitos) que ya usa el `ID` del propio
    # XML (`LibreDTE_{rut}_T{tipo}F{folio}`, folio a 10 dígitos) —
    # ver el `documento.xml` real.
    nombre_archivo = (
        f'LibreDTE_{contribuyente.rut}-{contribuyente.dv}_'
        f'T{documento.tipo_dte.codigo:03d}F{documento.folio:010d}.xml'
    )
    # `xml_bytes` son los bytes reales del XML (decodificados desde el
    # `xml_base64` guardado) — se sirven tal cual, con el charset que el
    # propio XML declara en su prolog (ISO-8859-1, la que usa el SII).
    # Un `HttpResponse` sin `charset` explícito usa el default de Django
    # (UTF-8), que no coincide con lo declarado en el prolog y corrompe
    # el archivo (y su firma electrónica, calculada sobre esos bytes).
    response = HttpResponse(
        documento.xml_bytes,
        content_type='application/xml; charset=iso-8859-1',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{nombre_archivo}"'
    )
    return response


@login_required
@xframe_options_exempt
def emitido_render_html(request: HttpRequest, pk: int) -> HttpResponse:
    """
    HTML del documento vía `document_renderer`.

    Para el iframe de "Vista previa" de `emitido_detalle` — necesita
    `xframe_options_exempt` porque Django manda `X-Frame-Options: DENY`
    por defecto en toda respuesta, incluso same-origin; acá se permite a
    propósito, es nuestro propio iframe, no contenido de terceros. Llama
    a la API en cada carga (no hay caché): es la misma llamada de
    siempre, solo que server-side. `charset=utf-8` explícito porque la
    API devuelve el HTML en UTF-8 (a diferencia del XML, que es
    ISO-8859-1 por convención del SII) — sin esto el navegador lo
    interpreta mal y las tildes salen como mojibake.
    """
    contribuyente = get_current_contribuyente(request)
    documento = get_object_or_404(
        DteEmitido,
        pk=pk,
        contribuyente=contribuyente,
    )
    try:
        html = document_renderer.render_html(documento)
    except ServiceError as error:
        return HttpResponse(
            f'<p style="font-family: sans-serif; padding: 1rem; '
            f'color: #842029;">No se pudo generar la vista previa: '
            f'{error}</p>',
            content_type='text/html; charset=utf-8',
            status=502,
        )
    return HttpResponse(html, content_type='text/html; charset=utf-8')


@login_required
def emitido_descargar_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    """Descarga el PDF, generado al vuelo vía `document_renderer`."""
    contribuyente = get_current_contribuyente(request)
    documento = get_object_or_404(
        DteEmitido,
        pk=pk,
        contribuyente=contribuyente,
    )
    try:
        rendering = document_renderer.render_pdf(documento)
    except ServiceError:
        messages.error(request, 'No se pudo generar el PDF.')
        return redirect('billing:emitido_detalle', pk=pk)

    response = HttpResponse(
        rendering.content_bytes,
        content_type=rendering.mime_type,
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{rendering.filename}"'
    )
    return response


@login_required
def emitido_enviar_sii(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Envía un documento emitido al SII — real, no se puede deshacer.

    `GET` muestra una página de confirmación de verdad (nunca un
    `confirm()` de JS); solo `POST` ejecuta.
    """
    contribuyente = get_current_contribuyente(request)
    documento = get_object_or_404(
        DteEmitido.objects.select_related(
            'tipo_dte',
            'receptor',
            'contribuyente__certificado',
        ),
        pk=pk,
        contribuyente=contribuyente,
    )
    if request.method != 'POST':
        return render(
            request,
            'billing/emitido_enviar_sii.html',
            {'documento': documento},
        )

    try:
        document_dispatcher.send(documento)
    except ServiceError as error:
        messages.error(request, str(error))
        return redirect('billing:emitido_detalle', pk=pk)

    messages.success(request, 'Documento enviado al SII correctamente.')
    return redirect('billing:emitido_detalle', pk=pk)


@login_required
def emitido_actualizar_estado(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Consulta al SII el estado del envío — solo `POST`.

    No es una acción destructiva (solo lee el estado actual), así que
    no necesita una página de confirmación aparte — un botón que
    manda el `POST` directo es suficiente.
    """
    contribuyente = get_current_contribuyente(request)
    documento = get_object_or_404(
        DteEmitido,
        pk=pk,
        contribuyente=contribuyente,
    )
    if request.method != 'POST':
        return redirect('billing:emitido_detalle', pk=pk)

    try:
        document_dispatcher.check_status(documento)
    except ServiceError as error:
        messages.error(request, str(error))
        return redirect('billing:emitido_detalle', pk=pk)

    messages.success(request, 'Estado actualizado.')
    return redirect('billing:emitido_detalle', pk=pk)


@login_required
def receptores(request: HttpRequest) -> HttpResponse:
    """
    Receptores del contribuyente activo.

    Igual que `documentos`: Tabulator pide los datos directo a
    `billing_api:receptores` (ver `billing.api.views.ReceptorListView`),
    esta vista solo renderiza el template.
    """
    return render(request, 'billing/receptores.html')


@login_required
def receptor_detalle(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Ficha de un receptor: sus datos y los documentos que se le emitieron.

    La pestaña "Documentos" reutiliza `billing_api:emitidos` (mismo
    endpoint que la lista general), acotado a este receptor vía el
    parámetro `receptor_id` — no un endpoint aparte.
    """
    contribuyente = get_current_contribuyente(request)
    receptor = get_object_or_404(
        Receptor.objects.select_related('comuna', 'pais'),
        pk=pk,
        contribuyente=contribuyente,
    )
    return render(
        request,
        'billing/receptor_detalle.html',
        {
            'receptor': receptor,
            # Para la pestaña "Avanzado" — mostrar por qué no se puede
            # eliminar (`ReceptorDeleteView` lo bloquea igual a nivel
            # de BD, `on_delete=PROTECT` en ambos modelos; esto es
            # solo para que la UI lo explique antes de intentarlo).
            'borradores_count': receptor.borradores.count(),
            'dtes_emitidos_count': receptor.dtes_emitidos.count(),
        },
    )


if TYPE_CHECKING:
    _ReceptorCreateBase = CreateView[Receptor, ReceptorForm]
else:
    _ReceptorCreateBase = CreateView


class ReceptorCreateView(
    LoginRequiredMixin,
    _ReceptorCreateBase,
):
    """Alta de un receptor del contribuyente activo."""

    model = Receptor
    form_class = ReceptorForm
    template_name = 'billing/receptor_form.html'
    success_url = reverse_lazy('billing:receptores')

    def form_valid(self, form: ReceptorForm) -> HttpResponse:
        """Asigna el contribuyente activo antes de guardar."""
        form.instance.contribuyente = require_current_contribuyente(
            self.request
        )
        return super().form_valid(form)


if TYPE_CHECKING:
    _ReceptorUpdateBase = UpdateView[Receptor, ReceptorForm]
else:
    _ReceptorUpdateBase = UpdateView


class ReceptorUpdateView(
    LoginRequiredMixin,
    _ReceptorUpdateBase,
):
    """Edición de un receptor del contribuyente activo."""

    form_class = ReceptorForm
    template_name = 'billing/receptor_form.html'
    success_url = reverse_lazy('billing:receptores')

    def get_queryset(self) -> QuerySet[Receptor]:
        """Solo receptores del contribuyente activo — no de otro tenant."""
        return Receptor.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )


if TYPE_CHECKING:
    _ReceptorDeleteBase = DeleteView[Receptor, Form]
else:
    _ReceptorDeleteBase = DeleteView


class ReceptorDeleteView(
    LoginRequiredMixin,
    RequiresSudoMixin,
    _ReceptorDeleteBase,
):
    """Eliminación de un receptor del contribuyente activo."""

    template_name = 'confirm_delete.html'
    success_url = reverse_lazy('billing:receptores')

    def get_queryset(self) -> QuerySet[Receptor]:
        """Solo receptores del contribuyente activo — no de otro tenant."""
        return Receptor.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )

    def form_valid(self, form: Form) -> HttpResponse:
        """
        Bloquea el borrado si el receptor tiene borradores o DTE emitidos.

        `DteEmitido.receptor`/`Borrador.receptor` usan
        `on_delete=PROTECT` — `DeleteView` no atrapa `ProtectedError`
        por su cuenta (a diferencia del admin de Django, que sí
        muestra una página amigable).
        """
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                'No se puede eliminar: este receptor tiene documentos '
                'emitidos o borradores asociados.',
            )
            url = reverse('billing:receptor_detalle', args=[self.object.pk])
            return redirect(f'{url}#avanzado')


# Campos de `Detalle`/`Referencia`/`MntPagos` que `form.estandar`
# espera como arrays paralelos (un valor por fila, ver
# `EstandarParserStrategy::addDetails()`/`addReferences()`/
# `addScheduledPayment()` en libredte-lib-core) — uno por `FormSet` de
# `/billing/emitir` (ver `forms.py`). `_form_data_from_forms()` es el
# único lugar que necesita esta lista.
_CAMPOS_ITEM = [
    'TpoCodigo',
    'VlrCodigo',
    'NmbItem',
    'DscItem',
    'IndExe',
    'QtyItem',
    'UnmdItem',
    'PrcItem',
    'CodImpAdic',
    'ValorDR',
    'TpoValor',
]
_CAMPOS_REFERENCIA = ['TpoDocRef', 'FolioRef', 'FchRef', 'CodRef', 'RazonRef']
_CAMPOS_PAGO = ['FchPago', 'MntPago', 'GlosaPagos']


def _flat_value(value: Any) -> str:
    """
    Un valor ya limpio por un `Form`/`FormSet` de vuelta a texto plano.

    Mismo formato que ya mandaba el HTML crudo que esta vista
    reemplazó (fecha ISO, decimal como texto, `''` para lo que no se
    llenó) — `form.estandar` (la API) espera exactamente ese shape,
    nunca un `date`/`Decimal`/`None` de Python.
    """
    if value is None:
        return ''
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _filled_rows(formset: BaseFormSet[Any]) -> list[dict[str, Any]]:
    """
    `cleaned_data` de las filas que el usuario sí llenó y no quitó.

    Una fila completamente vacía queda como `{}` en `cleaned_data`
    (`empty_permitted` — no hace falta llenar una fila que se agregó
    de más y no se usó). Una fila que el usuario quitó con el botón
    "Quitar" queda como `{'DELETE': True}` (`can_delete=True`, ver
    `forms.py`) — sin sus otros campos, nunca se validaron.
    """
    return [
        row for row in formset.cleaned_data if row and not row.get('DELETE')
    ]


def _filled_row_indexes(formset: BaseFormSet[Any]) -> list[int]:
    """
    Los índices originales (posición en el formset) de `_filled_rows()`.

    El builder devuelve `Detalle` ya filtrado (una entrada por fila
    con datos), sin ese índice — `emitir_calcular()` lo necesita para
    saber a qué fila del DOM corresponde cada subtotal calculado
    (`_filled_rows(formset)[k]` es la fila del índice
    `_filled_row_indexes(formset)[k]`).
    """
    return [
        index
        for index, row in enumerate(formset.cleaned_data)
        if row and not row.get('DELETE')
    ]


def _form_errors(
    documento_form: DocumentoForm,
    items_formset: BaseFormSet[ItemForm],
    referencias_formset: BaseFormSet[ReferenciaForm],
    pagos_formset: BaseFormSet[PagoForm],
) -> dict[str, list[str] | dict[str, list[str]]]:
    """
    Errores de validación de los 4 forms/formsets, listos para JSON.

    `ErrorDict`/`ErrorList` (lo que trae `.errors`) no son
    JSON-serializables tal cual — cada mensaje se pasa por `str()`.
    Los errores de una fila de un `FormSet` quedan bajo la llave
    `<prefijo>-<índice>` (ej. `items-0`), mismo criterio que Django usa
    para nombrar los campos de esa fila.
    """
    errors: dict[str, list[str] | dict[str, list[str]]] = {
        field: [str(message) for message in messages_]
        for field, messages_ in documento_form.errors.items()
    }
    for prefix, formset in (
        ('items', items_formset),
        ('referencias', referencias_formset),
        ('pagos', pagos_formset),
    ):
        for index, row_errors in enumerate(formset.errors):
            if row_errors:
                # `formset.errors` trae un `ErrorDict` por fila (no
                # `ErrorList`, como declara el stub de Django) —
                # `.items()` es real en tiempo de ejecución.
                errors[f'{prefix}-{index}'] = {
                    field: [str(message) for message in messages_]
                    for field, messages_ in cast(ErrorDict, row_errors).items()
                }
    return errors


def _form_data_from_forms(
    documento_form: DocumentoForm,
    items_formset: BaseFormSet[ItemForm],
    referencias_formset: BaseFormSet[ReferenciaForm],
    pagos_formset: BaseFormSet[PagoForm],
) -> dict[str, str | list[str]]:
    """
    `dict` plano con arrays paralelos, listo para `biller.draft_from_form()`.

    Mismo shape exacto que antes armaba `_datos_formulario_desde_post()`
    leyendo `request.POST` directo, ahora a partir de `Form`/`FormSet`
    ya validados (sticky en caso de error, ver `emitir()`). `tipo_dte`
    se excluye a propósito: es un campo propio de Slim para resolver
    `TipoDte`, `form.estandar` no lo conoce (ver `views/app.py::emitir()`).
    """
    data: dict[str, str | list[str]] = {
        field: _flat_value(value)
        for field, value in documento_form.cleaned_data.items()
        if field != 'tipo_dte'
    }

    for formset, fields in (
        (items_formset, _CAMPOS_ITEM),
        (referencias_formset, _CAMPOS_REFERENCIA),
        (pagos_formset, _CAMPOS_PAGO),
    ):
        rows = _filled_rows(formset)
        if not rows:
            continue
        for field in fields:
            data[field] = [_flat_value(row.get(field)) for row in rows]

    return data


@login_required
def emitir(request: HttpRequest) -> HttpResponse:
    """
    Formulario de emisión de un DTE — usa `form.estandar` del SDK.

    `DocumentoForm`/`ItemFormSet`/`ReferenciaFormSet`/`PagoFormSet`
    (`forms.py`) usan los mismos nombres de campo oficiales del SII
    (`RUTRecep`, `NmbItem`, etc.) que espera `form.estandar` — existen
    solo para que el formulario quede "sticky" si la API rechaza el
    envío (Django repuebla cada campo con lo ya tipeado al re-renderizar
    un `Form`/`FormSet` bindeado), no agregan validación de negocio
    nueva. Esta vista no elige un `Receptor` ya existente de una lista,
    ni arma ningún nodo anidado ni calcula nada: solo arma el `dict`
    plano (`_form_data_from_forms()`) y se lo pasa a
    `biller.draft_from_form()`, que resuelve o crea el `Receptor` a
    partir de esos mismos datos (`biller._resolver_receptor()`) — es
    ese servicio quien llama al SDK (ninguna vista debe hacerlo
    directo). No emite el DTE real directamente: arma un `Borrador`,
    que se confirma aparte desde `borrador_detalle` (ver
    `biller.bill_draft()`).
    """
    contribuyente = require_current_contribuyente(request)

    if request.method == 'POST':
        documento_form = DocumentoForm(
            request.POST, contribuyente=contribuyente
        )
        items_formset = ItemFormSet(request.POST, prefix='items')
        referencias_formset = ReferenciaFormSet(
            request.POST, prefix='referencias'
        )
        pagos_formset = PagoFormSet(request.POST, prefix='pagos')

        if (
            documento_form.is_valid()
            and items_formset.is_valid()
            and referencias_formset.is_valid()
            and pagos_formset.is_valid()
        ):
            tipo_dte = documento_form.cleaned_data['tipo_dte']
            form_data = _form_data_from_forms(
                documento_form,
                items_formset,
                referencias_formset,
                pagos_formset,
            )
            try:
                borrador = biller.draft_from_form(
                    contribuyente,
                    tipo_dte,
                    form_data,
                    require_authenticated_user(request),
                )
            except ServiceError as error:
                messages.error(request, str(error))
            else:
                messages.success(request, 'Borrador creado correctamente.')
                return redirect('billing:borrador_detalle', pk=borrador.pk)
    else:
        documento_form = DocumentoForm(
            contribuyente=contribuyente,
            initial={'FchEmis': timezone.localdate()},
        )
        items_formset = ItemFormSet(prefix='items')
        referencias_formset = ReferenciaFormSet(prefix='referencias')
        pagos_formset = PagoFormSet(prefix='pagos')

    return render(
        request,
        'billing/emitir.html',
        {
            'documento_form': documento_form,
            'items_formset': items_formset,
            'referencias_formset': referencias_formset,
            'pagos_formset': pagos_formset,
        },
    )


@login_required
@require_POST
def emitir_calcular(request: HttpRequest) -> JsonResponse:
    """
    Recalcula subtotales por ítem y totales de `/billing/emitir` en vivo.

    Llamado por JS (ver `extra_js` en `emitir.html`) cada vez que
    cambia un campo que afecta los montos (precio/cantidad/descuento/
    exento de una fila, el descuento global, o el tipo de documento) —
    el body es el mismo `<form>` serializado entero
    (`new FormData(...)`), así que se bindea igual que en `emitir()`.
    `require_POST` porque sin él cualquier otro método entra igual y
    bindea un `request.POST` vacío: la respuesta sería un 400 quejándose
    de campos faltantes en vez de decir que el método no corresponde.
    No persiste nada (ver `biller.calculate_totals_from_form()`). Nunca
    responde `null`: si el formulario todavía no es válido (filas a
    medio llenar, es lo esperable mientras se escribe — acá ni siquiera
    se llega a llamar al SDK) responde 400 con `{'detail': ...,
    'errors': {...}}` (los errores de validación de Django, por campo).
    Si el SDK sí se llamó y la API devolvió un error real, responde 500
    con `{'detail': ...}`. En ambos casos el JS lo deja en
    `console.error` — nunca se oculta en silencio.
    """
    contribuyente = require_current_contribuyente(request)
    documento_form = DocumentoForm(request.POST, contribuyente=contribuyente)
    items_formset = ItemFormSet(request.POST, prefix='items')
    referencias_formset = ReferenciaFormSet(request.POST, prefix='referencias')
    pagos_formset = PagoFormSet(request.POST, prefix='pagos')

    if not (
        documento_form.is_valid()
        and items_formset.is_valid()
        and referencias_formset.is_valid()
        and pagos_formset.is_valid()
    ):
        return JsonResponse(
            {
                'detail': 'El formulario todavía no está completo.',
                'errors': _form_errors(
                    documento_form,
                    items_formset,
                    referencias_formset,
                    pagos_formset,
                ),
            },
            status=400,
        )

    tipo_dte = documento_form.cleaned_data['tipo_dte']
    form_data = _form_data_from_forms(
        documento_form,
        items_formset,
        referencias_formset,
        pagos_formset,
    )
    indexes = _filled_row_indexes(items_formset)

    try:
        result = biller.calculate_totals_from_form(
            contribuyente,
            tipo_dte,
            form_data,
        )
    except ServiceError as error:
        return JsonResponse({'detail': str(error)}, status=500)

    return JsonResponse(
        {
            'items': [
                {'index': index, 'MontoItem': item.get('MontoItem')}
                for index, item in zip(
                    indexes,
                    result['detalle'],
                    strict=True,
                )
            ],
            'totales': result['totales'],
        }
    )


# Planillas de ejemplo de la emisión masiva, por extensión.
_EJEMPLOS_EMISION_MASIVA = Path(__file__).resolve().parent.parent / 'files'


@login_required
def emitir_masivo(request: HttpRequest) -> HttpResponse:
    """
    Emisión masiva de DTE a partir de una planilla CSV o XLSX.

    La biblioteca parsea la planilla en la solicitud
    (`bulk_biller.parse()`): ante el primer error se muestra en el
    formulario y no se emite nada. Si sale bien, los documentos se guardan
    y se encola su emisión (`tasks.process_bulk_billing`); el resultado
    llega por correo al usuario (ver `bulk_biller.process()`). Con
    "solo ver los documentos" no se guarda ni se encola nada: se descargan
    los documentos parseados, en YAML. Esta vista no conoce ninguna
    columna.

    :param request: El request.
    :type request: HttpRequest
    :return: La página; tras encolar la planilla, una redirección a ella
        misma.
    :rtype: HttpResponse
    """
    contribuyente = require_current_contribuyente(request)
    usuario = require_authenticated_user(request)
    form = EmisionMasivaForm(
        request.POST or None, request.FILES or None, usuario=usuario
    )

    if request.method == 'POST' and form.is_valid():
        archivo = form.cleaned_data['archivo']
        try:
            documentos = bulk_biller.parse(
                contribuyente,
                archivo.read(),
                Path(archivo.name).suffix.lower().removeprefix('.'),
            )
        except ServiceError as error:
            form.add_error('archivo', str(error))
        else:
            if not documentos:
                form.add_error('archivo', 'La planilla no tiene documentos.')
            elif form.cleaned_data['modo'] == EmisionMasivaForm.MODO_VER:
                # Ver lo que se generará, sin generar nada.
                return HttpResponse(
                    bulk_biller.documentos_to_yaml(documentos),
                    content_type='application/yaml; charset=utf-8',
                    headers={
                        'Content-Disposition': content_disposition_header(
                            True, f'{Path(archivo.name).stem}_documentos.yaml'
                        ),
                    },
                )
            else:
                try:
                    tasks.enqueue_bulk_billing(
                        contribuyente,
                        usuario,
                        documentos,
                        dte_real=(
                            form.cleaned_data['modo']
                            == EmisionMasivaForm.MODO_REAL
                        ),
                        pdf=bool(form.cleaned_data['pdf']),
                    )
                except bulk_biller.BulkBillingInProgressError as error:
                    messages.warning(
                        request,
                        f'{error} El resultado se notificará vía correo '
                        f'electrónico a {usuario.email}.',
                    )
                except ServiceError as error:
                    messages.error(request, str(error))
                else:
                    messages.success(
                        request,
                        'La emisión masiva está siendo procesada, se '
                        f'notificará vía correo electrónico a {usuario.email} '
                        'el resultado.',
                    )
                return redirect('billing:emitir_masivo')

    return render(
        request,
        'billing/emitir_masivo.html',
        {
            'form': form,
            'correo_usuario': usuario.email,
            'glosas_codigo': sorted(bulk_biller.GLOSAS_CODIGO.items()),
        },
    )


@login_required
def emitir_masivo_plantilla(
    request: HttpRequest, extension: str
) -> FileResponse:
    """
    Descarga una planilla de ejemplo de la emisión masiva (CSV o XLSX).

    Se sirve desde una vista y no como archivo estático porque el
    proyecto no publica un `static/` propio (ver `config/settings.py`),
    y así además queda detrás del login igual que el resto.

    :param request: El request.
    :type request: HttpRequest
    :param extension: `csv` o `xlsx`.
    :type extension: str
    :return: La planilla de ejemplo, como descarga.
    :rtype: FileResponse
    :raises Http404: Si no hay un ejemplo con esa extensión.
    """
    if extension not in ('csv', 'xlsx'):
        raise Http404
    ruta = _EJEMPLOS_EMISION_MASIVA / f'emision_masiva.{extension}'
    return FileResponse(
        ruta.open('rb'), as_attachment=True, filename=ruta.name
    )


def emitir_masivo_pdf(request: HttpRequest, token: str) -> FileResponse:
    """
    Descarga el ZIP con los PDF de una emisión masiva.

    Es el enlace que lleva el correo de resultado. No pide login: lo
    protege la firma del token (ver `bulk_biller.find_pdf_zip()`). La
    URL lleva ese token y no una PK: el ZIP es un archivo, no un
    registro de la base.

    :param request: El request.
    :type request: HttpRequest
    :param token: El token firmado del enlace.
    :type token: str
    :return: El ZIP, como descarga.
    :rtype: FileResponse
    :raises Http404: Si el enlace no es válido, venció o el archivo ya se
        borró.
    """
    encontrado = bulk_biller.find_pdf_zip(token)
    if encontrado is None:
        raise Http404('El enlace de descarga no es válido o ya venció.')
    ruta, nombre = encontrado
    return FileResponse(ruta.open('rb'), as_attachment=True, filename=nombre)


@login_required
def borradores(request: HttpRequest) -> HttpResponse:
    """
    Borradores del contribuyente activo.

    Igual que `emitidos`: Tabulator pide los datos directo a
    `billing_api:borradores` (ver `billing.api.views.BorradorListView`).
    """
    return render(request, 'billing/borradores.html')


@login_required
def borrador_detalle(request: HttpRequest, pk: int) -> HttpResponse:
    """Detalle de un borrador: receptor, totales — sin folio ni firma."""
    contribuyente = get_current_contribuyente(request)
    borrador = get_object_or_404(
        Borrador.objects.select_related('tipo_dte', 'receptor'),
        pk=pk,
        contribuyente=contribuyente,
    )
    return render(
        request,
        'billing/borrador_detalle.html',
        {
            'borrador': borrador,
            # Para las pestañas "JSON Normalizado"/"JSON Extra" — se
            # arma acá (no en el template) porque `json.dumps` no es
            # un filtro de Django; `borrador.extra` viene `None` casi
            # siempre hoy (ver docstring de `Borrador`), de ahí el `{}`.
            'datos_json': json.dumps(
                borrador.datos,
                ensure_ascii=False,
                indent=2,
            ),
            'extra_json': json.dumps(
                borrador.extra or {},
                ensure_ascii=False,
                indent=2,
            ),
        },
    )


@login_required
@xframe_options_exempt
def borrador_render_html(request: HttpRequest, pk: int) -> HttpResponse:
    """
    HTML del borrador vía `document_renderer`.

    Mismo criterio que `emitido_render_html`, para el iframe de
    "Vista previa" de `borrador_detalle`.
    """
    contribuyente = get_current_contribuyente(request)
    borrador = get_object_or_404(
        Borrador,
        pk=pk,
        contribuyente=contribuyente,
    )
    try:
        html = document_renderer.render_html(borrador)
    except ServiceError as error:
        return HttpResponse(
            f'<p style="font-family: sans-serif; padding: 1rem; '
            f'color: #842029;">No se pudo generar la vista previa: '
            f'{error}</p>',
            content_type='text/html; charset=utf-8',
            status=502,
        )
    return HttpResponse(html, content_type='text/html; charset=utf-8')


@login_required
def borrador_descargar_xml(request: HttpRequest, pk: int) -> HttpResponse:
    """Descarga el XML del borrador (sin timbre ni firma)."""
    contribuyente = get_current_contribuyente(request)
    borrador = get_object_or_404(Borrador, pk=pk, contribuyente=contribuyente)
    # Mismo criterio que `emitido_descargar_xml`: se sirven los bytes
    # reales, con el charset que el propio XML declara en su prolog
    # (ISO-8859-1) — un `HttpResponse` sin `charset` explícito usaría
    # UTF-8 y corrompería el archivo.
    response = HttpResponse(
        borrador.xml_bytes,
        content_type='application/xml; charset=iso-8859-1',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="Borrador_{borrador.codigo}.xml"'
    )
    return response


@login_required
def borrador_descargar_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    """Descarga el PDF del borrador, generado al vuelo."""
    contribuyente = get_current_contribuyente(request)
    borrador = get_object_or_404(Borrador, pk=pk, contribuyente=contribuyente)
    try:
        rendering = document_renderer.render_pdf(borrador)
    except ServiceError:
        messages.error(request, 'No se pudo generar el PDF.')
        return redirect('billing:borrador_detalle', pk=pk)

    response = HttpResponse(
        rendering.content_bytes,
        content_type=rendering.mime_type,
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{rendering.filename}"'
    )
    return response


@login_required
def borrador_descargar_json_normalizado(
    request: HttpRequest, pk: int
) -> HttpResponse:
    """Descarga `Borrador.datos` (JSON normalizado) tal cual se guardó."""
    contribuyente = get_current_contribuyente(request)
    borrador = get_object_or_404(Borrador, pk=pk, contribuyente=contribuyente)
    return _download_json(
        f'Borrador_{borrador.codigo}_normalizado.json',
        borrador.datos,
    )


@login_required
def borrador_descargar_json_extra(
    request: HttpRequest, pk: int
) -> HttpResponse:
    """Descarga `Borrador.extra` (JSON extra) tal cual se guardó."""
    contribuyente = get_current_contribuyente(request)
    borrador = get_object_or_404(Borrador, pk=pk, contribuyente=contribuyente)
    return _download_json(
        f'Borrador_{borrador.codigo}_extra.json',
        borrador.extra or {},
    )


def _download_json(filename: str, data: Any) -> HttpResponse:
    """`HttpResponse` de descarga para `data`, serializado como JSON."""
    response = HttpResponse(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type='application/json; charset=utf-8',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def borrador_confirmar(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Confirma un borrador: genera el DTE real (folio, timbre, firma).

    Solo `POST` ejecuta, porque consume un folio real y no es una
    acción segura para un enlace. La confirmación se pide en el modal
    con el resumen del documento que vive en `borrador_detalle` (ver
    `billing/borrador_detalle.html`), así que un `GET` acá no tiene
    nada propio que mostrar y vuelve a esa página.
    `biller.bill_draft()` elimina el borrador si tiene éxito.
    """
    contribuyente = get_current_contribuyente(request)
    borrador = get_object_or_404(
        Borrador.objects.select_related('tipo_dte', 'receptor'),
        pk=pk,
        contribuyente=contribuyente,
    )
    if request.method != 'POST':
        return redirect('billing:borrador_detalle', pk=pk)

    try:
        documento = biller.bill_draft(borrador)
    except ServiceError as error:
        messages.error(request, str(error))
        return redirect('billing:borrador_detalle', pk=pk)

    messages.success(request, 'Documento emitido correctamente.')
    return redirect('billing:emitido_detalle', pk=documento.pk)


if TYPE_CHECKING:
    _BorradorDeleteBase = DeleteView[Borrador, Form]
else:
    _BorradorDeleteBase = DeleteView


class BorradorDeleteView(LoginRequiredMixin, _BorradorDeleteBase):
    """Descarta un borrador — no genera ningún DTE."""

    model = Borrador
    template_name = 'confirm_delete.html'
    success_url = reverse_lazy('billing:borradores')

    def get_queryset(self) -> QuerySet[Borrador]:
        """Solo borradores del contribuyente activo — no de otro tenant."""
        return Borrador.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )


@login_required
def recibidos(request: HttpRequest) -> HttpResponse:
    """
    DTE recibidos de terceros.

    Igual que `emitidos`: Tabulator pide los datos directo a
    `billing_api:recibidos` (ver `billing.api.views.DteRecibidoListView`),
    esta vista solo renderiza el template.
    """
    return render(request, 'billing/recibidos.html')


@login_required
def recibido_detalle(request: HttpRequest, pk: int) -> HttpResponse:
    """Detalle de un DTE recibido: emisor, totales, estado RCV, XML."""
    contribuyente = get_current_contribuyente(request)
    documento = get_object_or_404(
        DteRecibido.objects.select_related(
            'tipo_dte',
            'emisor',
            'usuario',
        ).prefetch_related('rcv_eventos'),
        pk=pk,
        contribuyente=contribuyente,
    )
    return render(
        request,
        'billing/recibido_detalle.html',
        {
            'documento': documento,
            'detalle_items': _detalle_items_desde_xml(documento.xml),
        },
    )


@login_required
def recibido_subir(request: HttpRequest) -> HttpResponse:
    """Carga un sobre `EnvioDTE` recibido de un proveedor (XML)."""
    contribuyente = get_current_contribuyente(request)
    form = RecibidoSobreUploadForm(
        request.POST or None,
        request.FILES or None,
        contribuyente=contribuyente,
        usuario=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            recibidos_cargados = form.save()
        except ServiceError as error:
            form.add_error('archivo', str(error))
        else:
            if len(recibidos_cargados) == 1:
                messages.success(request, '1 documento recibido cargado.')
                return redirect(
                    'billing:recibido_detalle',
                    pk=recibidos_cargados[0].pk,
                )
            messages.success(
                request,
                f'{len(recibidos_cargados)} documentos recibidos cargados.',
            )
            return redirect('billing:recibidos')

    return render(request, 'billing/recibido_subir.html', {'form': form})


@login_required
def recibido_descargar_xml(request: HttpRequest, pk: int) -> HttpResponse:
    """Descarga el XML real del documento recibido."""
    contribuyente = get_current_contribuyente(request)
    documento = get_object_or_404(
        DteRecibido.objects.select_related('tipo_dte', 'emisor'),
        pk=pk,
        contribuyente=contribuyente,
    )
    # Mismo padding de folio (10 dígitos) que `emitido_descargar_xml` —
    # acá con el RUT del emisor real, no el nuestro: el folio es suyo.
    nombre_archivo = (
        f'LibreDTE_{documento.emisor.rut}-{documento.emisor.dv}_'
        f'T{documento.tipo_dte.codigo:03d}F{documento.folio:010d}.xml'
    )
    response = HttpResponse(
        documento.xml_bytes,
        content_type='application/xml; charset=iso-8859-1',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{nombre_archivo}"'
    )
    return response


@login_required
@xframe_options_exempt
def recibido_render_html(request: HttpRequest, pk: int) -> HttpResponse:
    """
    HTML del documento recibido vía `document_renderer`.

    Para el iframe de "Vista previa" de `recibido_detalle` — mismo
    criterio que `emitido_render_html` (necesita `xframe_options_exempt`,
    llama a la API en cada carga, `charset=utf-8` explícito).
    """
    contribuyente = get_current_contribuyente(request)
    documento = get_object_or_404(
        DteRecibido,
        pk=pk,
        contribuyente=contribuyente,
    )
    try:
        html = document_renderer.render_html(documento)
    except ServiceError as error:
        return HttpResponse(
            f'<p style="font-family: sans-serif; padding: 1rem; '
            f'color: #842029;">No se pudo generar la vista previa: '
            f'{error}</p>',
            content_type='text/html; charset=utf-8',
            status=502,
        )
    return HttpResponse(html, content_type='text/html; charset=utf-8')


@login_required
def recibido_descargar_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    """Descarga el PDF del documento recibido, generado al vuelo."""
    contribuyente = get_current_contribuyente(request)
    documento = get_object_or_404(
        DteRecibido,
        pk=pk,
        contribuyente=contribuyente,
    )
    try:
        rendering = document_renderer.render_pdf(documento)
    except ServiceError:
        messages.error(request, 'No se pudo generar el PDF.')
        return redirect('billing:recibido_detalle', pk=pk)

    response = HttpResponse(
        rendering.content_bytes,
        content_type=rendering.mime_type,
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{rendering.filename}"'
    )
    return response


@login_required
def ventas(request: HttpRequest) -> HttpResponse:
    """
    Reporte de ventas: períodos con documentos emitidos.

    Solo lectura sobre `DteEmitido` (ver `services/sales_reporter.py`) — no es
    el "libro" oficial que se envía al SII, es un reporte interno.
    Tabulator pide los datos directo a `billing_api:ventas_periodos`
    (ver `billing.api.views.VentasPeriodosListView`) — esta vista solo
    renderiza el template.
    """
    return render(request, 'billing/ventas.html')


@login_required
def ventas_periodo(request: HttpRequest, periodo: int) -> HttpResponse:
    """Resumen de un período de ventas, por tipo de documento."""
    contribuyente = require_current_contribuyente(request)
    resumen = sales_service.resumen_periodo(contribuyente, periodo)
    if resumen is None:
        raise Http404
    return render(
        request,
        'billing/ventas_periodo.html',
        {'resumen': resumen},
    )


_RCV_DETALLE_COLUMNS = [
    {'title': 'RUT', 'field': 'rut'},
    {'title': 'Razón social', 'field': 'razon_social'},
    {'title': 'Folio', 'field': 'folio', 'hozAlign': 'right'},
    {'title': 'Fecha', 'field': 'fecha'},
    {
        'title': 'Exento',
        'field': 'exento',
        'hozAlign': 'right',
        'formatter': 'money',
        'formatterParams': {'symbol': '$', 'precision': 0},
    },
    {
        'title': 'Neto',
        'field': 'neto',
        'hozAlign': 'right',
        'formatter': 'money',
        'formatterParams': {'symbol': '$', 'precision': 0},
    },
    {
        'title': 'IVA',
        'field': 'iva',
        'hozAlign': 'right',
        'formatter': 'money',
        'formatterParams': {'symbol': '$', 'precision': 0},
    },
    {
        'title': 'Total',
        'field': 'total',
        'hozAlign': 'right',
        'formatter': 'money',
        'formatterParams': {'symbol': '$', 'precision': 0},
    },
]


def _tipo_dte_label(dte: int) -> str:
    """
    Glosa de un tipo de documento del RCV para mostrar en pantalla.

    `TipoDte` es el catálogo de documentos que esta app emite, no todo
    el catálogo del SII (ver `CODIGOS_DTE_ELECTRONICOS` en
    `seeders.py`) — un `dte` del RCV sin `TipoDte` local (ej. 43,
    Liquidación-Factura) es válido, solo no tiene una glosa propia.
    """
    tipo_dte = TipoDte.objects.filter(codigo=dte).first()
    return tipo_dte.label if tipo_dte else f'Tipo documento {dte}'


def _rcv_detalle_rows(
    detalle: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Filas reducidas del detalle de RCV.

    Mismos campos que un `DteEmitido`/`DteRecibido` local — el detalle
    crudo del RCV trae unos 50 campos por documento, la mayoría sin uso
    práctico. El SII responde `None` (en vez de una lista vacía) cuando
    no hay documentos para el filtro pedido.
    """
    return [
        {
            'rut': f'{item["detRutDoc"]}-{item["detDvDoc"]}',
            'razon_social': item['detRznSoc'],
            'folio': item['detNroDoc'],
            'fecha': item['detFchDoc'],
            'exento': item['detMntExe'],
            'neto': item['detMntNeto'],
            'iva': item['detMntIVA'],
            'total': item['detMntTotal'],
        }
        for item in detalle or []
    ]


@login_required
def ventas_registro(request: HttpRequest) -> HttpResponse:
    """Formulario de período para consultar el RCV de ventas en el SII."""
    form = RcvPeriodoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        return redirect(
            'billing:ventas_periodo_rcv_resumen',
            periodo=form.periodo_int(),
        )
    return render(request, 'billing/ventas_registro.html', {'form': form})


@login_required
def ventas_periodo_rcv_resumen(
    request: HttpRequest, periodo: int
) -> HttpResponse:
    """
    Resumen del RCV de ventas del período, consultado en línea al SII.

    No guarda nada en la base de datos — cada carga vuelve a consultar
    al SII, y los montos pueden diferir de los que muestra
    `ventas_periodo` (que reporta sobre `DteEmitido` local).
    """
    contribuyente = require_current_contribuyente(request)
    backend = get_backend(contribuyente)
    if backend is None:
        return render(
            request, 'libredte/sii_backend_upsell.html', upsell_context()
        )
    try:
        respuesta = backend.sii_rcv_ventas_resumen(str(periodo))
    except SiiBackendError as error:
        messages.error(request, str(error))
        return redirect('billing:ventas_periodo', periodo=periodo)
    return render(
        request,
        'billing/ventas_rcv_resumen.html',
        {
            'periodo': periodo,
            'periodo_glosa': period_label(periodo),
            'resumen': respuesta['data']['data'] or [],
        },
    )


@login_required
def ventas_periodo_rcv_detalle(
    request: HttpRequest, periodo: int, dte: int
) -> HttpResponse:
    """Detalle del RCV de ventas del período para un tipo de documento."""
    contribuyente = require_current_contribuyente(request)
    backend = get_backend(contribuyente)
    if backend is None:
        return render(
            request, 'libredte/sii_backend_upsell.html', upsell_context()
        )
    try:
        respuesta = backend.sii_rcv_ventas_detalle(str(periodo), dte=dte)
    except SiiBackendError as error:
        messages.error(request, str(error))
        return redirect('billing:ventas_periodo_rcv_resumen', periodo=periodo)
    return render(
        request,
        'billing/ventas_rcv_detalle.html',
        {
            'periodo': periodo,
            'periodo_glosa': period_label(periodo),
            'dte': dte,
            'tipo_dte_label': _tipo_dte_label(dte),
            'rows': _rcv_detalle_rows(respuesta['data']['data']),
            'columns': _RCV_DETALLE_COLUMNS,
        },
    )


@login_required
def compras(request: HttpRequest) -> HttpResponse:
    """
    Reporte de compras: períodos con documentos de compra.

    Une `DteEmitido` (tipo 46 y derivados, lo que `services/sales_reporter.py`
    omite) con `DteRecibido` (ver `services/purchases_reporter.py`) — no es el
    "libro" oficial que se envía al SII, es un reporte interno.
    Tabulator pide los datos directo a `billing_api:compras_periodos`
    (ver `billing.api.views.ComprasPeriodosListView`) — esta vista solo
    renderiza el template.
    """
    return render(request, 'billing/compras.html')


@login_required
def compras_periodo(request: HttpRequest, periodo: int) -> HttpResponse:
    """
    Resumen de un período de compras, por tipo de documento.

    La tabla "Documentos del período" pide los datos directo a
    `billing_api:compras_periodo_documentos` (ver `billing.api.views
    .ComprasPeriodoDocumentosListView`) — mezcla `DteEmitido` y
    `DteRecibido`, así que no es el mismo endpoint que usa
    `ventas_periodo.html` (ese sí es un único `QuerySet`).
    """
    contribuyente = require_current_contribuyente(request)
    resumen = purchases_service.resumen_periodo(contribuyente, periodo)
    if resumen is None:
        raise Http404
    return render(
        request,
        'billing/compras_periodo.html',
        {'resumen': resumen},
    )


@login_required
def compras_registro(request: HttpRequest) -> HttpResponse:
    """Formulario de período/estado para el RCV de compras del SII."""
    form = RcvCompraPeriodoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        return redirect(
            'billing:compras_periodo_rcv_resumen',
            periodo=form.periodo_int(),
            estado=form.cleaned_data['estado'],
        )
    return render(request, 'billing/compras_registro.html', {'form': form})


@login_required
def compras_periodo_rcv_resumen(
    request: HttpRequest, periodo: int, estado: str = 'REGISTRO'
) -> HttpResponse:
    """
    Resumen del RCV de compras del período y estado, en línea al SII.

    No guarda nada en la base de datos — cada carga vuelve a consultar
    al SII, y los montos pueden diferir de los que muestra
    `compras_periodo` (que reporta sobre `DteEmitido`/`DteRecibido`
    locales).
    """
    estados = dict(RcvCompraPeriodoForm.ESTADO_CHOICES)
    if estado not in estados:
        raise Http404
    contribuyente = require_current_contribuyente(request)
    backend = get_backend(contribuyente)
    if backend is None:
        return render(
            request, 'libredte/sii_backend_upsell.html', upsell_context()
        )
    try:
        respuesta = backend.sii_rcv_compras_resumen(
            str(periodo), estado=estado
        )
    except SiiBackendError as error:
        messages.error(request, str(error))
        return redirect('billing:compras_periodo', periodo=periodo)
    return render(
        request,
        'billing/compras_rcv_resumen.html',
        {
            'periodo': periodo,
            'periodo_glosa': period_label(periodo),
            'estado': estado,
            'estado_glosa': estados[estado],
            'estado_choices': RcvCompraPeriodoForm.ESTADO_CHOICES,
            'resumen': respuesta['data']['data'] or [],
        },
    )


@login_required
def compras_periodo_rcv_detalle(
    request: HttpRequest, periodo: int, dte: int, estado: str = 'REGISTRO'
) -> HttpResponse:
    """Detalle del RCV de compras del período/estado para un tipo de doc."""
    estados = dict(RcvCompraPeriodoForm.ESTADO_CHOICES)
    if estado not in estados:
        raise Http404
    contribuyente = require_current_contribuyente(request)
    backend = get_backend(contribuyente)
    if backend is None:
        return render(
            request, 'libredte/sii_backend_upsell.html', upsell_context()
        )
    try:
        respuesta = backend.sii_rcv_compras_detalle(
            str(periodo), dte=dte, estado=estado
        )
    except SiiBackendError as error:
        messages.error(request, str(error))
        return redirect(
            'billing:compras_periodo_rcv_resumen',
            periodo=periodo,
            estado=estado,
        )
    return render(
        request,
        'billing/compras_rcv_detalle.html',
        {
            'periodo': periodo,
            'periodo_glosa': period_label(periodo),
            'dte': dte,
            'estado': estado,
            'estado_glosa': estados[estado],
            'estado_choices': RcvCompraPeriodoForm.ESTADO_CHOICES,
            'tipo_dte_label': _tipo_dte_label(dte),
            'rows': _rcv_detalle_rows(respuesta['data']['data']),
            'columns': _RCV_DETALLE_COLUMNS,
        },
    )


@login_required
def emisores(request: HttpRequest) -> HttpResponse:
    """
    Contrapartes que emiten DTE recibidos.

    Igual que `receptores`: Tabulator pide los datos directo a
    `billing_api:emisores` (ver `billing.api.views.EmisorListView`),
    esta vista solo renderiza el template. Sin "+ Nuevo": un `Emisor`
    se agrega solo, al recibirse un DTE de un proveedor nuevo (ver
    docstring del modelo).
    """
    return render(request, 'billing/emisores.html')


@login_required
def emisor_detalle(request: HttpRequest, pk: int) -> HttpResponse:
    """Ficha de un emisor: sus datos y los DTE recibidos de él."""
    contribuyente = get_current_contribuyente(request)
    emisor = get_object_or_404(
        Emisor.objects.select_related('comuna', 'pais'),
        pk=pk,
        contribuyente=contribuyente,
    )
    return render(request, 'billing/emisor_detalle.html', {'emisor': emisor})
