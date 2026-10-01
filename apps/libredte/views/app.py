"""Vistas de `libredte` fuera de Configuración (alta, certificados)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.forms import Form
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView

from apps.core.auth import require_authenticated_user
from apps.core.sudo import RequiresSudoMixin
from apps.core.utils import action_buttons

from ..forms import CertificadoUploadForm, ContribuyenteForm
from ..models import Certificado, Contribuyente
from ..tenancy import set_current_contribuyente

if TYPE_CHECKING:
    _ContribuyenteWizardBase = CreateView[Contribuyente, ContribuyenteForm]
else:
    # Los CBV genéricos de Django no son `Generic` en tiempo de
    # ejecución (solo en los stubs de `django-stubs`) — subscribir
    # `CreateView[...]` directo como base real lanzaría
    # `TypeError: not subscriptable` al importar el módulo.
    _ContribuyenteWizardBase = CreateView


class ContribuyenteWizardView(
    LoginRequiredMixin,
    _ContribuyenteWizardBase,
):
    """Alta del contribuyente — solo los datos básicos."""

    model = Contribuyente
    form_class = ContribuyenteForm
    template_name = 'libredte/contribuyente_form.html'
    success_url = reverse_lazy('core:dashboard')

    def form_valid(self, form: ContribuyenteForm) -> HttpResponse:
        """Registra al usuario actual como dueño, y lo deja activo."""
        form.instance.usuario = require_authenticated_user(self.request)
        response = super().form_valid(form)
        # `super().form_valid()` ya hizo `self.object = form.save()`.
        assert self.object is not None
        set_current_contribuyente(self.request, self.object)
        return response


@login_required
def contribuyentes(request: HttpRequest) -> HttpResponse:
    """
    Contribuyentes del usuario actual — permite elegir cuál queda activo.

    Mismo patrón que cualquier otro listado de la app (`_table.html`
    con `rows`/`columns` armados acá) — sin API aparte, no hay volumen
    que lo justifique (son los contribuyentes de UN usuario, no un
    catálogo global).
    """
    rows = [
        {
            'rut_dv': f'{contribuyente.rut}-{contribuyente.dv}',
            'razon_social': contribuyente.razon_social,
            'comuna': contribuyente.comuna.glosa,
            'actions': action_buttons(
                (
                    'Seleccionar',
                    'check',
                    reverse(
                        'libredte:contribuyente_seleccionar',
                        args=[contribuyente.rut],
                    ),
                    'primary',
                ),
            ),
        }
        for contribuyente in Contribuyente.objects.filter(
            usuario=require_authenticated_user(request),
        ).select_related('comuna')
    ]
    columns = [
        {
            'title': 'RUT',
            'field': 'rut_dv',
            'width': 140,
            'headerFilter': 'input',
        },
        {
            'title': 'Razón social',
            'field': 'razon_social',
            'widthGrow': 2,
            'minWidth': 180,
            'headerFilter': 'input',
        },
        {
            'title': 'Comuna',
            'field': 'comuna',
            'widthGrow': 1,
            'minWidth': 140,
            'headerFilter': 'input',
        },
        {
            'title': 'Acciones',
            'field': 'actions',
            'formatter': 'html',
            'width': 110,
            'minWidth': 110,
            'hozAlign': 'center',
            'headerSort': False,
        },
    ]
    return render(
        request,
        'libredte/contribuyentes.html',
        {'rows': rows, 'columns': columns},
    )


@login_required
def contribuyente_seleccionar(request: HttpRequest, rut: int) -> HttpResponse:
    """Selecciona el contribuyente de RUT `rut` como activo de la sesión."""
    contribuyente = get_object_or_404(
        Contribuyente,
        rut=rut,
        usuario=request.user,
    )
    set_current_contribuyente(request, contribuyente)
    return redirect('core:dashboard')


@login_required
def certificados(request: HttpRequest) -> HttpResponse:
    """
    Procesa la carga de un certificado — sin página propia.

    Un certificado es del usuario, no de un contribuyente en
    particular — puede enlazarse a varios (ver `Contribuyente
    .certificado`/`libredte_settings:certificado`). La pestaña
    "Certificados" vive en `/accounts/profile/`, aportada por
    `libredte.platform` al registro `'profile'` de `core` (mismo
    mecanismo que el dashboard) — `core` nunca importa `libredte`, así
    que el `<form>` de esa pestaña apunta acá para procesar la carga
    (`certificate_manager`, que sí puede tocar el SDK) y siempre vuelve
    a la pestaña, con o sin errores.
    """
    tab_url = reverse('profile') + '#certificados'
    if request.method != 'POST':
        return redirect(tab_url)

    form = CertificadoUploadForm(
        request.POST,
        request.FILES,
        usuario=request.user,
    )
    if form.is_valid():
        form.save()
        messages.success(request, 'Certificado cargado.')
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, str(error))
    return redirect(tab_url)


if TYPE_CHECKING:
    _CertificadoDeleteBase = DeleteView[Certificado, Form]
else:
    _CertificadoDeleteBase = DeleteView


class CertificadoDeleteView(
    LoginRequiredMixin,
    RequiresSudoMixin,
    _CertificadoDeleteBase,
):
    """
    Elimina un certificado del usuario logueado.

    `Contribuyente.certificado` usa `on_delete=SET_NULL`: los
    contribuyentes que lo tuvieran enlazado quedan sin certificado, no
    se bloquea el borrado — `get_context_data` expone cuántos para que
    la confirmación lo advierta.
    """

    template_name = 'confirm_delete.html'

    def get_success_url(self) -> str:
        """Vuelve a la pestaña "Certificados" del perfil."""
        return reverse('profile') + '#certificados'

    def get_queryset(self) -> QuerySet[Certificado]:
        """Solo certificados del usuario logueado — no de otro usuario."""
        return require_authenticated_user(self.request).certificados.all()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Agrega cuántos contribuyentes quedarían sin certificado."""
        context = super().get_context_data(**kwargs)
        context['contribuyentes_afectados'] = (
            self.object.contribuyentes.count()
        )
        return context
