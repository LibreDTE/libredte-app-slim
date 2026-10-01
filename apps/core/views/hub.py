"""
Vistas de `core` que componen contenido aportado por otras apps.

Ni "app" ni "settings": `dashboard`/`profile` no son páginas propias de
`core` — arman su contenido juntando lo que cada app registró
(`DashboardWidget`/`ProfileSection`, ver `contracts.py`/`registry.py`)
y renderizando cada fragmento por su cuenta. Ninguna otra vista del
proyecto hace esto (confirmado: es el único lugar que llama a
`get_all()` para componer HTML de otra app, no solo para leer datos).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from rest_framework.authtoken.models import Token

from .. import totp
from ..auth import require_authenticated_user
from ..forms import (
    ProfileForm,
    ProfilePasswordChangeForm,
    TwoFactorActivateForm,
)
from ..models import TwoFactorAuth
from ..registry import get_all

if TYPE_CHECKING:
    pass

# Dónde vive el secreto TOTP entre que se muestra el QR y el usuario
# confirma el primer código: en la sesión y no en un campo oculto del
# formulario, para no aceptar como secreto algo que mandó el cliente.
_SESSION_PENDING_SECRET = 'core_2fa_pending_secret'

# Tarjetas del perfil a las que vuelve cada operación (contrato de
# `Tabs`, ver CLAUDE.md: `#pestaña:tarjeta`).
_CARD_2FA = '#security:2fa'
_CARD_TOKEN = '#api:token'


def _profile_url(card: str) -> str:
    """URL del perfil con la tarjeta `card` abierta."""
    return reverse('profile') + card


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """
    Página de entrada tras iniciar sesión.

    No arma ningún dato propio: junta los `DashboardWidget` registrados
    (registro `'dashboard'`, ver `contracts.py`) en orden de
    `priority`, renderiza el `template` de cada uno con el contexto que
    devuelve su `get_context(request)`, y le pasa a la plantilla la
    lista de fragmentos HTML ya armados — quien registra cada widget
    es quien sabe qué servicio llamar, no `core`.
    """
    widgets_html = [
        mark_safe(
            render_to_string(
                widget.template,
                widget.get_context(request),
                request,
            ),
        )
        for widget in get_all('dashboard')
    ]
    return render(
        request,
        'core/dashboard.html',
        {'dashboard_widgets': widgets_html},
    )


@login_required
@require_POST
def profile_two_factor_activate(request: HttpRequest) -> HttpResponse:
    """Activa el 2FA si el código confirma el secreto pendiente."""
    user = require_authenticated_user(request)
    if TwoFactorAuth.objects.filter(user=user).exists():
        return redirect(_profile_url(_CARD_2FA))

    secret = request.session.get(_SESSION_PENDING_SECRET, '')
    form = TwoFactorActivateForm(request.POST, secret=secret)
    if not form.is_valid():
        # `ErrorList` itera `ValidationError | str | _StrPromise`, no
        # `str`: hay que forzar cada elemento antes de unirlos.
        errores = form.errors['two_factor_code']
        messages.error(request, ' '.join(str(error) for error in errores))
        return redirect(_profile_url(_CARD_2FA))

    TwoFactorAuth.objects.create(user=user, secret=secret)
    del request.session[_SESSION_PENDING_SECRET]
    messages.success(request, 'Verificación en dos pasos activada.')
    return redirect(_profile_url(_CARD_2FA))


@login_required
@require_POST
def profile_two_factor_deactivate(request: HttpRequest) -> HttpResponse:
    """Desactiva el 2FA: borrar la fila es el estado "desactivado"."""
    user = require_authenticated_user(request)
    borradas, _detalle = TwoFactorAuth.objects.filter(user=user).delete()
    if borradas:
        messages.success(request, 'Verificación en dos pasos desactivada.')
    return redirect(_profile_url(_CARD_2FA))


@login_required
@require_POST
def profile_api_token_generate(request: HttpRequest) -> HttpResponse:
    """
    Emite un token de API, reemplazando el anterior si lo había.

    Regenerar es borrar y crear: `Token.key` es la PK y se calcula en
    el `save()` inicial, así que no hay forma de rotarlo en la fila
    existente. Va en una transacción para que un fallo al crear no deje
    al usuario sin ninguno de los dos.
    """
    user = require_authenticated_user(request)
    with transaction.atomic():
        Token.objects.filter(user=user).delete()
        Token.objects.create(user=user)
    messages.success(request, 'Token de API generado.')
    return redirect(_profile_url(_CARD_TOKEN))


@login_required
@require_POST
def profile_api_token_delete(request: HttpRequest) -> HttpResponse:
    """Revoca el token de API del usuario."""
    user = require_authenticated_user(request)
    borrados, _detalle = Token.objects.filter(user=user).delete()
    if borrados:
        messages.success(request, 'Token de API eliminado.')
    return redirect(_profile_url(_CARD_TOKEN))


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    """
    Perfil del usuario: arma los formularios y el contexto, nada más.

    Solo atiende los dos formularios de varios campos (datos básicos y
    contraseña), que tienen que volver a renderizarse con sus errores
    al lado de cada campo: por eso postean acá, con un campo oculto
    `action` para saber cuál se envió, y redirigen con `#xxx` para
    reabrir la pestaña correcta.

    Las demás operaciones del perfil (2FA y token de API) tienen su
    propia URL y su propia vista `POST` — no son formularios que deban
    conservar estado, así que informan por `messages` y vuelven acá.
    """
    action = request.POST.get('action')
    user = require_authenticated_user(request)
    two_factor = TwoFactorAuth.objects.filter(user=user).first()

    pending_secret = ''
    if two_factor is None:
        # Se reusa el secreto ya emitido en vez de generar uno nuevo en
        # cada render: si no, recargar la página (o fallar el código)
        # invalidaría el QR que el usuario ya escaneó.
        pending_secret = (
            request.session.get(_SESSION_PENDING_SECRET)
            or totp.generate_secret()
        )
        request.session[_SESSION_PENDING_SECRET] = pending_secret

    form_data = ProfileForm(
        request.POST if action == 'data' else None,
        instance=user,
    )
    form_password = ProfilePasswordChangeForm(
        request.user,
        request.POST if action == 'password' else None,
    )

    if request.method == 'POST':
        if action == 'data' and form_data.is_valid():
            form_data.save()
            messages.success(request, 'Datos actualizados.')
            return redirect(reverse('profile') + '#data')
        if action == 'password' and form_password.is_valid():
            form_password.save()
            # Cambiar la contraseña invalida el hash de sesión — sin
            # esto, el usuario queda deslogueado justo después de
            # cambiar su propia contraseña.
            update_session_auth_hash(request, user)
            messages.success(request, 'Contraseña actualizada.')
            return redirect(reverse('profile') + '#security')

    profile_sections = [
        {
            'label': section.label,
            'tab_id': section.tab_id,
            'html': mark_safe(
                render_to_string(
                    section.template,
                    section.get_context(request),
                    request,
                ),
            ),
        }
        for section in get_all('profile')
    ]

    return render(
        request,
        'core/profile.html',
        {
            'form_data': form_data,
            'form_password': form_password,
            'form_two_factor': TwoFactorActivateForm(secret=pending_secret),
            'api_token': Token.objects.filter(user=user).first(),
            'two_factor': two_factor,
            'two_factor_secret': pending_secret,
            'two_factor_qr': (
                totp.qr_data_uri(
                    totp.provisioning_uri(
                        user.get_username(),
                        pending_secret,
                    ),
                )
                if pending_secret
                else ''
            ),
            'profile_sections': profile_sections,
        },
    )
