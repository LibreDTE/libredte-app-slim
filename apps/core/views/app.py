"""Vistas de `core` fuera de Configuración (sudo, setup)."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from ..forms import SudoForm
from ..sudo import activate_sudo


@login_required
def sudo(request: HttpRequest) -> HttpResponse:
    """Reconfirma la contraseña antes de dejar pasar a una acción sensible."""
    next_url = (
        request.GET.get('next')
        or request.POST.get('next')
        or reverse('core:dashboard')
    )
    form = SudoForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        activate_sudo(request)
        return redirect(next_url)

    return render(
        request,
        'core/sudo.html',
        {'form': form, 'next': next_url},
    )


def setup(request: HttpRequest) -> HttpResponse:
    """Alta del primer usuario (administrador) — solo si no hay ninguno."""
    if User.objects.exists():
        return redirect('public:welcome')

    form = UserCreationForm[User](request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        user.backend = settings.AUTHENTICATION_BACKENDS[0]
        login(request, user)
        return redirect('core:dashboard')

    return render(request, 'core/setup.html', {'form': form})
