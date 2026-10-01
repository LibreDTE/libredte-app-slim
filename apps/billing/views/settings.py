"""Vistas de `billing` bajo Configuración (ambiente, ítems, folios)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, ProtectedError, QuerySet
from django.forms import Form
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, UpdateView

from apps.core.sudo import RequiresSudoMixin
from apps.core.utils import action_buttons
from apps.libredte.models import Contribuyente
from apps.libredte.plugins.contracts import SiiBackendError
from apps.libredte.services.exceptions import ServiceError
from apps.libredte.services.sii_backend import get_backend, upsell_context
from apps.libredte.tenancy import (
    get_current_contribuyente,
    require_current_contribuyente,
)

from ..forms import (
    CafAnularForm,
    CafFolioForm,
    CafReobtenerCargarForm,
    CafSolicitarForm,
    CafUploadForm,
    ContribuyenteAmbienteForm,
    ItemCatalogoForm,
    ItemCategoriaForm,
)
from ..models import Caf, CafFolio, DteEmitido, Item, ItemCategoria, TipoDte
from ..services import caf_manager


@login_required
def ambiente(request: HttpRequest) -> HttpResponse:
    """Ambiente (resolución SII) del contribuyente activo ("Configuración")."""
    contribuyente = get_current_contribuyente(request)
    form = ContribuyenteAmbienteForm(
        request.POST or None,
        instance=contribuyente,
    )

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Ambiente actualizado.')
        return redirect('billing_settings:ambiente')

    return render(
        request,
        'billing/ambiente.html',
        {'form': form},
    )


@login_required
def ambiente_sii_datos_empresa(request: HttpRequest) -> HttpResponse:
    """Fragmento AJAX (modal): datos de la empresa ante el SII."""
    contribuyente = get_current_contribuyente(request)
    backend = get_backend(contribuyente)
    if backend is None:
        return render(
            request, 'libredte/_sii_backend_upsell.html', upsell_context()
        )
    try:
        respuesta = backend.sii_dte_contribuyentes_datos()
    except SiiBackendError as error:
        return render(
            request,
            'billing/_sii_backend_error.html',
            {'mensaje': str(error)},
        )
    return render(
        request,
        'billing/_sii_datos_empresa.html',
        {'datos': respuesta['data']},
    )


@login_required
def ambiente_sii_usuarios(request: HttpRequest) -> HttpResponse:
    """Fragmento AJAX (modal): usuarios autorizados ante el SII."""
    contribuyente = get_current_contribuyente(request)
    backend = get_backend(contribuyente)
    if backend is None:
        return render(
            request, 'libredte/_sii_backend_upsell.html', upsell_context()
        )
    try:
        respuesta = backend.sii_dte_contribuyentes_usuarios()
    except SiiBackendError as error:
        return render(
            request,
            'billing/_sii_backend_error.html',
            {'mensaje': str(error)},
        )
    return render(
        request,
        'billing/_sii_usuarios.html',
        {'usuarios': respuesta['data']},
    )


@login_required
def items(request: HttpRequest) -> HttpResponse:
    """
    Catálogo de ítems del contribuyente activo: 2 pestañas.

    "Productos y/o servicios" (Tabulator vía `billing_api:items`) y
    "Categorías" (`billing_api:item_categorias`) — mismo criterio que
    `sucursales`: esta vista solo renderiza el template, los datos los
    pide Tabulator directo a la API.
    """
    return render(request, 'billing/items.html')


if TYPE_CHECKING:
    _ItemCreateBase = CreateView[Item, ItemCatalogoForm]
else:
    _ItemCreateBase = CreateView


class ItemCreateView(LoginRequiredMixin, _ItemCreateBase):
    """Alta de un ítem del contribuyente activo."""

    model = Item
    form_class = ItemCatalogoForm
    template_name = 'billing/item_form.html'
    success_url = reverse_lazy('billing_settings:items')

    def get_form_kwargs(self) -> dict[str, Any]:
        """Pasa el contribuyente activo para acotar `categoria`."""
        kwargs = super().get_form_kwargs()
        kwargs['contribuyente'] = get_current_contribuyente(self.request)
        return kwargs

    def form_valid(self, form: ItemCatalogoForm) -> HttpResponse:
        """Asigna el contribuyente activo antes de guardar."""
        form.instance.contribuyente = require_current_contribuyente(
            self.request
        )
        return super().form_valid(form)


if TYPE_CHECKING:
    _ItemUpdateBase = UpdateView[Item, ItemCatalogoForm]
else:
    _ItemUpdateBase = UpdateView


class ItemUpdateView(LoginRequiredMixin, _ItemUpdateBase):
    """Edición de un ítem del contribuyente activo."""

    form_class = ItemCatalogoForm
    template_name = 'billing/item_form.html'
    success_url = reverse_lazy('billing_settings:items')

    def get_form_kwargs(self) -> dict[str, Any]:
        """Pasa el contribuyente activo para acotar `categoria`."""
        kwargs = super().get_form_kwargs()
        kwargs['contribuyente'] = get_current_contribuyente(self.request)
        return kwargs

    def get_queryset(self) -> QuerySet[Item]:
        """Solo ítems del contribuyente activo — no de otro tenant."""
        return Item.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )


if TYPE_CHECKING:
    _ItemDeleteBase = DeleteView[Item, Form]
else:
    _ItemDeleteBase = DeleteView


class ItemDeleteView(
    LoginRequiredMixin,
    RequiresSudoMixin,
    _ItemDeleteBase,
):
    """Eliminación de un ítem del contribuyente activo."""

    template_name = 'confirm_delete.html'
    success_url = reverse_lazy('billing_settings:items')
    extra_context = {'base_template': 'layouts/settings.html'}

    def get_queryset(self) -> QuerySet[Item]:
        """Solo ítems del contribuyente activo — no de otro tenant."""
        return Item.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )


if TYPE_CHECKING:
    _ItemCategoriaCreateBase = CreateView[ItemCategoria, ItemCategoriaForm]
else:
    _ItemCategoriaCreateBase = CreateView


class ItemCategoriaCreateView(
    LoginRequiredMixin,
    _ItemCategoriaCreateBase,
):
    """Alta de una categoría de ítems del contribuyente activo."""

    model = ItemCategoria
    form_class = ItemCategoriaForm
    template_name = 'billing/item_categoria_form.html'

    def get_success_url(self) -> str:
        """A la pestaña "Categorías" de `items` — ver `items.html`."""
        return f'{reverse("billing_settings:items")}#categorias'

    def form_valid(self, form: ItemCategoriaForm) -> HttpResponse:
        """Asigna el contribuyente activo antes de guardar."""
        form.instance.contribuyente = require_current_contribuyente(
            self.request
        )
        return super().form_valid(form)


if TYPE_CHECKING:
    _ItemCategoriaUpdateBase = UpdateView[ItemCategoria, ItemCategoriaForm]
else:
    _ItemCategoriaUpdateBase = UpdateView


class ItemCategoriaUpdateView(
    LoginRequiredMixin,
    _ItemCategoriaUpdateBase,
):
    """Edición de una categoría de ítems del contribuyente activo."""

    form_class = ItemCategoriaForm
    template_name = 'billing/item_categoria_form.html'

    def get_success_url(self) -> str:
        """A la pestaña "Categorías" de `items` — ver `items.html`."""
        return f'{reverse("billing_settings:items")}#categorias'

    def get_queryset(self) -> QuerySet[ItemCategoria]:
        """Solo categorías del contribuyente activo — no de otro tenant."""
        return ItemCategoria.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )


if TYPE_CHECKING:
    _ItemCategoriaDeleteBase = DeleteView[ItemCategoria, Form]
else:
    _ItemCategoriaDeleteBase = DeleteView


class ItemCategoriaDeleteView(
    LoginRequiredMixin,
    RequiresSudoMixin,
    _ItemCategoriaDeleteBase,
):
    """Eliminación de una categoría de ítems del contribuyente activo."""

    template_name = 'confirm_delete.html'
    extra_context = {'base_template': 'layouts/settings.html'}

    def get_success_url(self) -> str:
        """A la pestaña "Categorías" de `items` — ver `items.html`."""
        return f'{reverse("billing_settings:items")}#categorias'

    def get_queryset(self) -> QuerySet[ItemCategoria]:
        """Solo categorías del contribuyente activo — no de otro tenant."""
        return ItemCategoria.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )

    def form_valid(self, form: Form) -> HttpResponse:
        """
        Bloquea el borrado si la categoría tiene ítems asociados.

        `Item.categoria` usa `on_delete=PROTECT` — mismo criterio que
        `ReceptorDeleteView`.
        """
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                'No se puede eliminar: esta categoría tiene ítems asociados.',
            )
            url = reverse('billing_settings:items')
            return redirect(f'{url}#categorias')


def _caf_vigencia_html(caf: Caf) -> str:
    """HTML de vigencia de un CAF puntual (sin importar `siguiente`)."""
    if caf.fecha_vencimiento is None:
        return '<span class="badge bg-success">Vigente</span>'
    color = 'success' if caf.vigente else 'danger'
    fecha = caf.fecha_vencimiento.strftime('%d-%m-%Y')
    return f'<span class="badge bg-{color}">{fecha}</span>'


def _vigencia_html(contribuyente: Contribuyente, caf_folio: CafFolio) -> str:
    """
    HTML de la columna "Vigente": el CAF que cubre `caf_folio.siguiente`.

    Ese es el CAF que de verdad se usaría en la próxima emisión (ver
    `caf_manager.reserve_next_folio()`), no "el último CAF cargado" —
    un CAF viejo con folios de sobra puede seguir siendo el que cubre
    `siguiente` si el más reciente todavía no se empieza a usar.
    """
    caf = Caf.objects.filter(
        contribuyente=contribuyente,
        tipo_dte=caf_folio.tipo_dte,
        desde__lte=caf_folio.siguiente,
        hasta__gte=caf_folio.siguiente,
    ).first()
    if caf is None:
        return '<span class="text-muted">Sin CAF cargado</span>'
    return _caf_vigencia_html(caf)


@login_required
def folios(request: HttpRequest) -> HttpResponse:
    """Listado de folios — un contador por tipo de DTE con CAF cargado."""
    contribuyente = require_current_contribuyente(request)
    rows = [
        {
            'tipo_dte': folio.tipo_dte.label,
            'siguiente': folio.siguiente,
            'disponibles': folio.disponibles,
            'alerta': folio.alerta,
            'alertado': 'Sí' if folio.alertado else 'No',
            'vigente': _vigencia_html(contribuyente, folio),
            'acciones': action_buttons(
                (
                    'Ver',
                    'eye',
                    reverse(
                        'billing_settings:folio_detalle',
                        args=[folio.tipo_dte.pk],
                    ),
                    'primary',
                )
            ),
        }
        for folio in CafFolio.objects.filter(
            contribuyente=contribuyente,
        )
        .select_related('tipo_dte')
        .order_by('tipo_dte__codigo')
    ]
    columns = [
        {'title': 'Tipo de DTE', 'field': 'tipo_dte'},
        {'title': 'Siguiente', 'field': 'siguiente', 'hozAlign': 'right'},
        {'title': 'Disponibles', 'field': 'disponibles', 'hozAlign': 'right'},
        {'title': 'Alerta', 'field': 'alerta', 'hozAlign': 'right'},
        {'title': 'Alertado', 'field': 'alertado', 'width': 120},
        {
            'title': 'Vigente',
            'field': 'vigente',
            'formatter': 'html',
            'width': 150,
        },
        {
            'title': 'Acciones',
            'field': 'acciones',
            'formatter': 'html',
            'width': 130,
        },
    ]
    return render(
        request,
        'billing/folios.html',
        {'rows': rows, 'columns': columns},
    )


@login_required
def folio_detalle(request: HttpRequest, pk: int) -> HttpResponse:
    """CAF cargados y uso mensual de un tipo de DTE, con tabs."""
    contribuyente = get_current_contribuyente(request)
    tipo_dte = get_object_or_404(TipoDte, pk=pk)
    caf_folio = get_object_or_404(
        CafFolio,
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
    )

    caf_rows = [
        {
            'desde': caf.desde,
            'hasta': caf.hasta,
            'cantidad': caf.hasta - caf.desde + 1,
            'fecha_autorizacion': caf.fecha_autorizacion,
            'vigente': _caf_vigencia_html(caf),
            'en_uso': (
                '<i class="fa-solid fa-check text-success"></i>'
                if caf.desde <= caf_folio.siguiente <= caf.hasta
                else ''
            ),
            'acciones': action_buttons(
                (
                    'Descargar XML',
                    'file-arrow-down',
                    reverse(
                        'billing_settings:caf_descargar_xml', args=[caf.pk]
                    ),
                    'secondary',
                ),
                (
                    'Eliminar',
                    'trash',
                    reverse('billing_settings:caf_eliminar', args=[caf.pk]),
                    'danger',
                ),
            ),
        }
        for caf in Caf.objects.filter(
            contribuyente=contribuyente,
            tipo_dte=tipo_dte,
        ).order_by('-desde')
    ]
    caf_columns = [
        {'title': 'Folio desde', 'field': 'desde', 'hozAlign': 'right'},
        {'title': 'Folio hasta', 'field': 'hasta', 'hozAlign': 'right'},
        {'title': 'Cantidad', 'field': 'cantidad', 'hozAlign': 'right'},
        {'title': 'Fecha de solicitud', 'field': 'fecha_autorizacion'},
        {
            'title': 'Vigente',
            'field': 'vigente',
            'formatter': 'html',
            'width': 130,
        },
        {
            'title': 'En uso',
            'field': 'en_uso',
            'formatter': 'html',
            'hozAlign': 'center',
            'width': 120,
        },
        {
            'title': 'Acciones',
            'field': 'acciones',
            'formatter': 'html',
            'hozAlign': 'center',
            'width': 130,
        },
    ]

    usage_rows = list(
        DteEmitido.objects.filter(
            contribuyente=contribuyente,
            tipo_dte=tipo_dte,
        )
        .values('periodo')
        .annotate(cantidad=Count('id'))
        .order_by('-periodo'),
    )
    usage_columns = [
        {'title': 'Período', 'field': 'periodo'},
        {
            'title': 'Documentos emitidos',
            'field': 'cantidad',
            'hozAlign': 'right',
        },
    ]
    promedio_mensual = (
        round(sum(row['cantidad'] for row in usage_rows) / len(usage_rows))
        if usage_rows
        else 0
    )

    return render(
        request,
        'billing/folio_detalle.html',
        {
            'tipo_dte': tipo_dte,
            'caf_folio': caf_folio,
            'promedio_mensual': promedio_mensual,
            'caf_rows': caf_rows,
            'caf_columns': caf_columns,
            'usage_rows': usage_rows,
            'usage_columns': usage_columns,
        },
    )


@login_required
def folio_modificar(request: HttpRequest, pk: int) -> HttpResponse:
    """Modifica `siguiente`/`alerta` del contador de folios de un tipo."""
    contribuyente = get_current_contribuyente(request)
    tipo_dte = get_object_or_404(TipoDte, pk=pk)
    caf_folio = get_object_or_404(
        CafFolio,
        contribuyente=contribuyente,
        tipo_dte=tipo_dte,
    )

    form = CafFolioForm(request.POST or None, instance=caf_folio)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Folio actualizado.')
        return redirect('billing_settings:folio_detalle', pk=pk)

    return render(
        request,
        'billing/folio_modificar.html',
        {'form': form, 'tipo_dte': tipo_dte},
    )


@login_required
def folio_subir_caf(request: HttpRequest) -> HttpResponse:
    """Carga un CAF descargado desde el SII (XML)."""
    contribuyente = get_current_contribuyente(request)
    form = CafUploadForm(
        request.POST or None,
        request.FILES or None,
        contribuyente=contribuyente,
    )
    if request.method == 'POST' and form.is_valid():
        caf = form.save()
        messages.success(
            request,
            f'CAF cargado: folios {caf.desde} a {caf.hasta} de '
            f'{caf.tipo_dte.label}.',
        )
        return redirect('billing_settings:folio_detalle', pk=caf.tipo_dte.pk)

    return render(request, 'billing/folio_subir_caf.html', {'form': form})


@login_required
def folio_solicitar_caf(
    request: HttpRequest, pk: int | None = None
) -> HttpResponse:
    """Pide folios NUEVOS al SII para un tipo de documento y los carga."""
    contribuyente = require_current_contribuyente(request)
    tipo_dte = None
    if pk is not None:
        tipo_dte = get_object_or_404(TipoDte, pk=pk)
        get_object_or_404(
            CafFolio, contribuyente=contribuyente, tipo_dte=tipo_dte
        )

    form = CafSolicitarForm(request.POST or None, tipo_dte=tipo_dte)
    if request.method == 'POST' and form.is_valid():
        backend = get_backend(contribuyente)
        if backend is None:
            return render(
                request,
                'libredte/sii_backend_upsell.html',
                {**upsell_context(), 'base_template': 'layouts/settings.html'},
            )

        elegido = form.cleaned_data['tipo_dte']
        try:
            xml_bytes = backend.sii_caf_solicitar(
                dte=elegido.codigo,
                cantidad=form.cleaned_data['cantidad'],
            )
            caf = caf_manager.register_caf_from_xml(
                contribuyente, elegido, xml_bytes
            )
        except (SiiBackendError, ServiceError) as error:
            messages.error(request, f'No se pudo solicitar el CAF: {error}')
            if tipo_dte is not None:
                return redirect(
                    'billing_settings:folio_solicitar_caf_tipo',
                    pk=tipo_dte.pk,
                )
            return redirect('billing_settings:folio_solicitar_caf')

        messages.success(
            request,
            f'CAF solicitado: folios {caf.desde} a {caf.hasta} de '
            f'{elegido.label}.',
        )
        return redirect('billing_settings:folio_detalle', pk=elegido.pk)

    return render(
        request,
        'billing/folio_solicitar_caf.html',
        {'form': form, 'tipo_dte': tipo_dte},
    )


@login_required
def folio_reobtener_caf(request: HttpRequest, pk: int) -> HttpResponse:
    """Busca en el SII CAF ya autorizados que no están cargados en Slim."""
    contribuyente = get_current_contribuyente(request)
    tipo_dte = get_object_or_404(TipoDte, pk=pk)
    get_object_or_404(CafFolio, contribuyente=contribuyente, tipo_dte=tipo_dte)

    resultados = None
    siguiente_pagina = None
    if request.method == 'POST':
        backend = get_backend(contribuyente)
        if backend is None:
            return render(
                request,
                'libredte/sii_backend_upsell.html',
                {**upsell_context(), 'base_template': 'layouts/settings.html'},
            )

        pagina = int(request.POST.get('pagina') or 1)
        try:
            respuesta = backend.sii_caf_solicitudes(
                dte=tipo_dte.codigo, pagina=pagina
            )
        except SiiBackendError as error:
            messages.error(request, f'No se pudo buscar en el SII: {error}')
            return redirect('billing_settings:folio_reobtener_caf', pk=pk)

        cargados = set(
            Caf.objects.filter(
                contribuyente=contribuyente, tipo_dte=tipo_dte
            ).values_list('desde', flat=True)
        )
        resultados = [
            item
            for item in respuesta['data']
            if item['inicial'] not in cargados
        ]
        siguiente_pagina = respuesta['metadata'].get('siguiente_pagina')

    return render(
        request,
        'billing/folio_reobtener_caf.html',
        {
            'tipo_dte': tipo_dte,
            'resultados': resultados,
            'siguiente_pagina': siguiente_pagina,
        },
    )


@login_required
def folio_reobtener_caf_cargar(request: HttpRequest, pk: int) -> HttpResponse:
    """Descarga y registra un CAF encontrado por "Reobtener CAF"."""
    contribuyente = require_current_contribuyente(request)
    tipo_dte = get_object_or_404(TipoDte, pk=pk)
    get_object_or_404(CafFolio, contribuyente=contribuyente, tipo_dte=tipo_dte)

    form = CafReobtenerCargarForm(request.POST or None)
    if request.method != 'POST' or not form.is_valid():
        messages.error(request, 'No se pudo reobtener el CAF.')
        return redirect('billing_settings:folio_reobtener_caf', pk=pk)

    backend = get_backend(contribuyente)
    if backend is None:
        return render(
            request,
            'libredte/sii_backend_upsell.html',
            {**upsell_context(), 'base_template': 'layouts/settings.html'},
        )

    try:
        xml_bytes = backend.sii_caf_xml(
            dte=tipo_dte.codigo,
            folio_inicial=form.cleaned_data['folio_inicial'],
            folio_final=form.cleaned_data['folio_final'],
            fecha_autorizacion=form.cleaned_data[
                'fecha_autorizacion'
            ].isoformat(),
        )
        caf = caf_manager.register_caf_from_xml(
            contribuyente, tipo_dte, xml_bytes
        )
    except (SiiBackendError, ServiceError) as error:
        messages.error(request, f'No se pudo reobtener el CAF: {error}')
        return redirect('billing_settings:folio_reobtener_caf', pk=pk)

    messages.success(
        request,
        f'CAF cargado: folios {caf.desde} a {caf.hasta} de {tipo_dte.label}.',
    )
    return redirect('billing_settings:folio_detalle', pk=pk)


@login_required
def folio_anular_caf(request: HttpRequest, pk: int) -> HttpResponse:
    """Anula un rango de folios de un tipo de documento en el SII."""
    contribuyente = get_current_contribuyente(request)
    tipo_dte = get_object_or_404(TipoDte, pk=pk)
    caf_folio = get_object_or_404(
        CafFolio, contribuyente=contribuyente, tipo_dte=tipo_dte
    )

    form = CafAnularForm(
        request.POST or None, contribuyente=contribuyente, tipo_dte=tipo_dte
    )
    if request.method == 'POST' and form.is_valid():
        backend = get_backend(contribuyente)
        if backend is None:
            return render(
                request,
                'libredte/sii_backend_upsell.html',
                {**upsell_context(), 'base_template': 'layouts/settings.html'},
            )

        folio_inicial = form.cleaned_data['folio_inicial']
        folio_final = form.cleaned_data['folio_final']
        try:
            backend.sii_caf_anular(
                dte=tipo_dte.codigo,
                folio_inicial=folio_inicial,
                folio_final=folio_final,
            )
        except SiiBackendError as error:
            messages.error(request, f'No se pudo anular: {error}')
            return redirect('billing_settings:folio_anular_caf', pk=pk)

        messages.success(
            request,
            f'Folios {folio_inicial} a {folio_final} de {tipo_dte.label} '
            f'anulados en el SII.',
        )
        return redirect('billing_settings:folio_detalle', pk=pk)

    return render(
        request,
        'billing/folio_anular_caf.html',
        {'form': form, 'tipo_dte': tipo_dte, 'caf_folio': caf_folio},
    )


@login_required
def caf_descargar_xml(request: HttpRequest, pk: int) -> HttpResponse:
    """Descarga el XML de un CAF cargado (el que devolvió la API)."""
    contribuyente = require_current_contribuyente(request)
    caf = get_object_or_404(
        Caf.objects.select_related('tipo_dte'),
        pk=pk,
        contribuyente=contribuyente,
    )
    nombre_archivo = f'CAF_{caf.tipo_dte.codigo}_{caf.desde}_{caf.hasta}.xml'
    response = HttpResponse(
        caf.xml_bytes,
        content_type='application/xml; charset=iso-8859-1',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{nombre_archivo}"'
    )
    return response


if TYPE_CHECKING:
    _CafDeleteBase = DeleteView[Caf, Form]
else:
    _CafDeleteBase = DeleteView


class CafDeleteView(
    LoginRequiredMixin,
    RequiresSudoMixin,
    _CafDeleteBase,
):
    """
    Eliminación de un CAF cargado — requiere sudo.

    Solo borra el registro local: no ajusta `disponibles`/`siguiente`
    de `CafFolio` (mismo criterio que "Reobtener CAF" — revisarlos a
    mano si corresponde, ver `folio_modificar`).
    """

    model = Caf
    template_name = 'confirm_delete.html'
    extra_context = {'base_template': 'layouts/settings.html'}

    def get_queryset(self) -> QuerySet[Caf]:
        """Solo CAF del contribuyente activo — no de otro tenant."""
        return Caf.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )

    def get_success_url(self) -> str:
        """Al detalle del tipo de documento del CAF eliminado."""
        return reverse(
            'billing_settings:folio_detalle',
            args=[self.object.tipo_dte.pk],
        )
