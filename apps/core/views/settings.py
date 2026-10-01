"""Vistas de `core` bajo Configuración (entrada + sección "Plugins")."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import format_html

from ..forms import PluginActivationForm
from ..models import PluginConfig
from ..plugin.base import BasePlugin
from ..plugin.catalog import all_plugins
from ..plugin.catalog import get as get_plugin
from ..registry import get_all
from ..tenant import require_current_tenant
from ..utils import action_buttons


def _plugin_label_html(plugin_class: type[BasePlugin]) -> str:
    """HTML de la celda "Plugin": nombre, descripción y sus capacidades."""
    capacidades = ', '.join(
        definition_class.label
        for definition_class in plugin_class.capabilities
    )
    if not capacidades:
        return format_html(
            '<strong>{}</strong><br><small>{}</small>',
            plugin_class.label,
            plugin_class.description,
        )
    return format_html(
        '<strong>{}</strong><br><small>{}</small>'
        '<br><small class="text-muted">{}</small>',
        plugin_class.label,
        plugin_class.description,
        capacidades,
    )


@login_required
def settings_index(request: HttpRequest) -> HttpResponse:
    """
    Entrada de "Configuración" — redirige al primer ítem registrado.

    `core` arma el shell (`layouts/settings.html`, con el nav de todas
    las secciones registradas — ver `_settings_sections` en
    `context_processors.py`) pero no tiene contenido propio que mostrar
    acá: cada página real la aporta la app que la registró. Sin
    ninguna sección registrada (no debería pasar con al menos una app
    de dominio instalada) muestra un mensaje en vez de un 404 confuso.
    """
    sections = get_all('settings')
    if sections and sections[0].items:
        return redirect(sections[0].items[0].url_name)
    return render(request, 'core/settings_empty.html')


@login_required
def plugins(request: HttpRequest) -> HttpResponse:
    """
    Listado de Plugins — una fila por plugin, "Configurar" por fila.

    Un plugin puede implementar varias capabilities
    (`BasePlugin.capabilities` es un arreglo) — se listan sus nombres bajo
    la descripción, dentro de la misma celda (ver
    `_plugin_label_html()`), en vez de agrupar/duplicar la fila por
    capability: hoy cada capability tiene a lo más un plugin que la
    implementa, así que agrupar no ordena nada que una lista simple no
    muestre igual de bien.

    Mismo patrón que cualquier otro listado de Configuración (ej.
    `billing_settings:folios`): `_table.html` con `rows`/`columns`
    armados acá, sin API aparte — no hay volumen que justifique
    paginación remota. Vive en `core` y no en una app de dominio
    porque no es un concern específico de ninguna (ver `apps.py`).
    """
    tenant = require_current_tenant(request)
    content_type = ContentType.objects.get_for_model(tenant)
    active_ids = set(
        PluginConfig.objects.filter(
            content_type=content_type,
            object_id=tenant.pk,
            active=True,
        ).values_list('plugin_id', flat=True)
    )
    rows = [
        {
            'label': _plugin_label_html(plugin_class),
            'active': 'Sí' if plugin_class.id in active_ids else 'No',
            'deprecated': (
                f'Sí (desde {plugin_class.deprecated_at})'
                if plugin_class.deprecated_at
                else 'No'
            ),
            'actions': action_buttons(
                (
                    'Configurar',
                    'gear',
                    reverse(
                        'core_settings:plugin_configure',
                        args=[plugin_class.id],
                    ),
                    'primary',
                ),
            ),
        }
        for plugin_class in all_plugins()
        if plugin_class.listable
    ]
    has_deprecated_plugins = any(
        plugin_class.deprecated_at is not None
        for plugin_class in all_plugins()
    )
    columns = [
        {
            'title': 'Plugin',
            'field': 'label',
            'formatter': 'html',
            'widthGrow': 1,
            'minWidth': 160,
            'headerFilter': 'input',
        },
        {
            'title': 'Activo',
            'field': 'active',
            'width': 120,
            'minWidth': 120,
            'headerFilter': 'input',
        },
        *(
            [
                {
                    'title': 'Deprecado',
                    'field': 'deprecated',
                    'width': 140,
                    'minWidth': 140,
                    'headerFilter': 'input',
                },
            ]
            if has_deprecated_plugins
            else []
        ),
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
    deprecated_active_labels = [
        plugin_class.label
        for plugin_class in all_plugins()
        if plugin_class.deprecated_at is not None
        and plugin_class.id in active_ids
    ]
    return render(
        request,
        'core/plugins.html',
        {
            'rows': rows,
            'columns': columns,
            'deprecated_active_labels': deprecated_active_labels,
        },
    )


@login_required
def plugin_configure(request: HttpRequest, plugin_id: str) -> HttpResponse:
    """
    Activa/configura un `BasePlugin` para el tenant actual.

    Dos forms, un solo `<form>` HTML: `PluginActivationForm` (el único
    campo que decide `core`, `active`) y `plugin_class.config_form`
    (los campos propios del plugin — validación/transformación propia
    vía `clean()`/`clean_<campo>()`, estándar de Django, `core` no
    necesita saber nada de eso). La plantilla es extensible por plugin
    (`BasePlugin.template_name`, ver `apps/core/plugin/base.py`) — el
    default (`core/plugin_configure.html`) es un fallback trivial;
    contexto extra vía `get_extra_context()`.
    """
    plugin_class = get_plugin(plugin_id)
    if plugin_class is None:
        raise Http404
    tenant = require_current_tenant(request)
    content_type = ContentType.objects.get_for_model(tenant)
    plugin_config, _created = PluginConfig.objects.get_or_create(
        content_type=content_type,
        object_id=tenant.pk,
        plugin_id=plugin_id,
    )

    activation_form = PluginActivationForm(
        request.POST or None,
        initial={'active': plugin_config.active},
        deprecated=plugin_class.deprecated_at is not None,
        was_active=plugin_config.active,
    )
    config_form = plugin_class.config_form(
        request.POST or None,
        initial=plugin_config.config,
    )
    if (
        request.method == 'POST'
        and activation_form.is_valid()
        and config_form.is_valid()
    ):
        plugin_config.active = activation_form.cleaned_data['active']
        plugin_config.config = config_form.cleaned_data
        plugin_config.save()
        messages.success(request, 'Plugin actualizado.')
        return redirect('core_settings:plugin_configure', plugin_id=plugin_id)

    plugin_instance = plugin_class(plugin_config.config)
    capabilities = list(plugin_class.capabilities)
    return render(
        request,
        plugin_class.template_name,
        {
            'plugin': plugin_class,
            'activation_form': activation_form,
            'form': config_form,
            'capabilities': capabilities,
            **plugin_instance.get_extra_context(),
        },
    )
