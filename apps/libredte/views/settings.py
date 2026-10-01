"""Vistas de `libredte` bajo Configuración: empresa, sucursales, etc."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.forms import Form
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, UpdateView

from apps.core.sudo import RequiresSudoMixin

from ..forms import (
    ActividadEconomicaAgregarForm,
    CertificadoLinkForm,
    ContribuyenteEmpresaForm,
    SucursalForm,
)
from ..models import Sucursal
from ..tenancy import get_current_contribuyente, require_current_contribuyente


@login_required
def empresa(request: HttpRequest) -> HttpResponse:
    """
    Datos del contribuyente activo — sección "Configuración" ("Mi empresa").

    Página propia registrada en el menú de Configuración de `core` (ver
    `platform.py`) — permite que el menú de Configuración junte
    secciones de varias apps sin que ninguna necesite conocer a las
    demás.
    """
    contribuyente = get_current_contribuyente(request)
    form = ContribuyenteEmpresaForm(
        request.POST or None,
        request.FILES or None,
        instance=contribuyente,
    )

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Empresa actualizada.')
        return redirect('libredte_settings:empresa')

    return render(
        request,
        'libredte/empresa.html',
        {'form': form},
    )


@login_required
def actividades(request: HttpRequest) -> HttpResponse:
    """
    Actividades económicas del contribuyente activo ("Configuración").

    Solo asocia/desasocia — no crea ni edita `ActividadEconomica`: elige
    entre las que ya están cargadas en la base (ver
    `apps.libredte.seeders.seed()`). Una tabla con lo ya asociado (nunca
    el catálogo completo, que podría tener cientos de filas) + un
    `<select>` para agregar una más.
    """
    contribuyente = require_current_contribuyente(request)
    action = request.POST.get('action')

    if request.method == 'POST' and action == 'agregar':
        form = ActividadEconomicaAgregarForm(
            request.POST,
            contribuyente=contribuyente,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Actividad económica agregada.')
        else:
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, str(error))
        return redirect('libredte_settings:actividades')

    if request.method == 'POST' and action == 'eliminar':
        asociacion = get_object_or_404(
            contribuyente.actividades,
            actividad_economica_id=request.POST.get('actividad_economica'),
        )
        if asociacion.es_principal:
            messages.error(
                request,
                'No puedes quitar la actividad principal — marca otra '
                'como principal primero.',
            )
        else:
            asociacion.delete()
            messages.success(request, 'Actividad económica quitada.')
        return redirect('libredte_settings:actividades')

    if request.method == 'POST' and action == 'principal':
        asociacion = get_object_or_404(
            contribuyente.actividades,
            actividad_economica_id=request.POST.get('actividad_economica'),
        )
        contribuyente.actividades.update(es_principal=False)
        asociacion.es_principal = True
        asociacion.save(update_fields=['es_principal'])
        messages.success(request, 'Actividad principal actualizada.')
        return redirect('libredte_settings:actividades')

    return render(
        request,
        'libredte/actividades.html',
        {
            'form': ActividadEconomicaAgregarForm(contribuyente=contribuyente),
            'actividades': contribuyente.actividades.select_related(
                'actividad_economica',
            ).order_by('actividad_economica__codigo'),
        },
    )


@login_required
def certificado(request: HttpRequest) -> HttpResponse:
    """
    Certificado enlazado al contribuyente activo ("Configuración").

    Solo enlaza — no sube nada acá: los certificados se cargan desde
    `libredte:certificados` (el perfil del usuario dueño del
    contribuyente, ver `Contribuyente.usuario`).
    """
    contribuyente = require_current_contribuyente(request)
    form = CertificadoLinkForm(
        request.POST or None,
        instance=contribuyente,
        usuario=contribuyente.usuario,
    )

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Certificado actualizado.')
        return redirect('libredte_settings:certificado')

    return render(
        request,
        'libredte/certificado.html',
        {'form': form},
    )


@login_required
def sucursales(request: HttpRequest) -> HttpResponse:
    """
    Sucursales del contribuyente activo.

    Tabulator pide los datos directo a `libredte_api:sucursales` (ver
    `libredte.api.views.SucursalListView`), esta vista solo renderiza
    el template.
    """
    return render(request, 'libredte/sucursales.html')


if TYPE_CHECKING:
    _SucursalCreateBase = CreateView[Sucursal, SucursalForm]
else:
    _SucursalCreateBase = CreateView


class SucursalCreateView(
    LoginRequiredMixin,
    _SucursalCreateBase,
):
    """Alta de una sucursal del contribuyente activo."""

    model = Sucursal
    form_class = SucursalForm
    template_name = 'libredte/sucursal_form.html'
    success_url = reverse_lazy('libredte_settings:sucursales')

    def form_valid(self, form: SucursalForm) -> HttpResponse:
        """Asigna el contribuyente activo antes de guardar."""
        form.instance.contribuyente = require_current_contribuyente(
            self.request
        )
        return super().form_valid(form)


if TYPE_CHECKING:
    _SucursalUpdateBase = UpdateView[Sucursal, SucursalForm]
else:
    _SucursalUpdateBase = UpdateView


class SucursalUpdateView(
    LoginRequiredMixin,
    _SucursalUpdateBase,
):
    """Edición de una sucursal del contribuyente activo."""

    form_class = SucursalForm
    template_name = 'libredte/sucursal_form.html'
    success_url = reverse_lazy('libredte_settings:sucursales')

    def get_queryset(self) -> QuerySet[Sucursal]:
        """Solo sucursales del contribuyente activo — no de otro tenant."""
        return Sucursal.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )


if TYPE_CHECKING:
    _SucursalDeleteBase = DeleteView[Sucursal, Form]
else:
    _SucursalDeleteBase = DeleteView


class SucursalDeleteView(
    LoginRequiredMixin,
    RequiresSudoMixin,
    _SucursalDeleteBase,
):
    """Eliminación de una sucursal del contribuyente activo."""

    template_name = 'confirm_delete.html'
    success_url = reverse_lazy('libredte_settings:sucursales')
    # Sucursales vive bajo Configuración (ver `platform.py`) — el shell
    # con el nav de Configuración, a diferencia de otras vistas.
    extra_context = {'base_template': 'layouts/settings.html'}

    def get_queryset(self) -> QuerySet[Sucursal]:
        """Solo sucursales del contribuyente activo — no de otro tenant."""
        return Sucursal.objects.filter(
            contribuyente=get_current_contribuyente(self.request),
        )
