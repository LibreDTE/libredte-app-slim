"""Tests del segundo factor: login, activación y desactivación."""

from __future__ import annotations

import time

import pyotp
import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, override_settings
from django.urls import reverse

from apps.core import totp
from apps.core.forms import LoginForm
from apps.core.models import TwoFactorAuth
from apps.core.views.hub import _SESSION_PENDING_SECRET

pytestmark = pytest.mark.django_db

# Descartable y sin relación con la clave del seed demo (ver
# `apps/billing/seeders.py`): un test no tiene por qué depender de
# una credencial real. Mismo valor que usa el resto de la suite.
PASSWORD = 'demo12345'

# Margen mínimo de ventana TOTP que `_code()` garantiza: de sobra para
# el PBKDF2 del login y el request, sin alargar la suite (solo espera
# cuando el paso está por terminar).
_MIN_MARGIN_SECONDS = 5

# Stack mínimo con el que corre la vista de perfil, sin el middleware de
# ninguna app de dominio. `core` no conoce el dominio (ver
# `apps/core/tenant.py`): con el stack completo, este test tendría que
# crear un `Contribuyente` para satisfacer a `apps.libredte` e importar
# su modelo acá, que es el único import de ese tipo que `core` no hace
# en ninguna parte. Que `profile` funcione con el stack real ya lo
# cubre `apps/billing/tests/test_smoke_urls.py`, que le hace un `GET`
# autenticado con datos completos de todas las apps.
CORE_ONLY_MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.RequireInitialUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]


@pytest.fixture
def user() -> User:
    return User.objects.create_user(username='demo', password=PASSWORD)


def _code(secret: str) -> str:
    """
    Código TOTP recién nacido, con la ventana entera por delante.

    `totp.verify()` solo acepta el paso en curso, así que un código
    emitido sobre el final de su ventana ya no vale cuando el test
    termina de armar el request (`authenticate()` paga ~0,4s de PBKDF2
    antes de verificar) y el test falla sin que haya nada roto. Esperar
    al próximo paso cuando queda poco margen lo vuelve determinista sin
    relajar la verificación real.
    """
    totp_gen = pyotp.TOTP(secret)
    remaining = totp_gen.interval - (time.time() % totp_gen.interval)
    if remaining < _MIN_MARGIN_SECONDS:
        time.sleep(remaining)
    return totp_gen.now()


def test_verify_accepts_the_current_code() -> None:
    secret = totp.generate_secret()

    assert totp.verify(secret, _code(secret))


def test_verify_rejects_an_arbitrary_code() -> None:
    secret = totp.generate_secret()

    assert not totp.verify(secret, '000000')
    assert not totp.verify(secret, '')


def test_login_without_two_factor_ignores_the_code_field(user: User) -> None:
    form = LoginForm(data={'username': user.username, 'password': PASSWORD})

    assert form.is_valid()


def test_login_with_two_factor_requires_the_code(user: User) -> None:
    TwoFactorAuth.objects.create(user=user, secret=totp.generate_secret())

    form = LoginForm(data={'username': user.username, 'password': PASSWORD})

    assert not form.is_valid()


def test_login_with_two_factor_rejects_an_invalid_code(user: User) -> None:
    TwoFactorAuth.objects.create(user=user, secret=totp.generate_secret())

    form = LoginForm(
        data={
            'username': user.username,
            'password': PASSWORD,
            'two_factor_code': '000000',
        },
    )

    assert not form.is_valid()


def test_login_with_two_factor_accepts_the_current_code(user: User) -> None:
    secret = totp.generate_secret()
    TwoFactorAuth.objects.create(user=user, secret=secret)

    form = LoginForm(
        data={
            'username': user.username,
            'password': PASSWORD,
            'two_factor_code': _code(secret),
        },
    )

    assert form.is_valid()


def test_a_wrong_password_still_fails_with_a_valid_code(user: User) -> None:
    """El segundo factor correcto no compensa una contraseña incorrecta."""
    secret = totp.generate_secret()
    TwoFactorAuth.objects.create(user=user, secret=secret)

    form = LoginForm(
        data={
            'username': user.username,
            'password': 'otra-cosa',
            'two_factor_code': _code(secret),
        },
    )

    assert not form.is_valid()


def test_the_secret_is_stored_encrypted(user: User) -> None:
    secret = totp.generate_secret()
    TwoFactorAuth.objects.create(user=user, secret=secret)

    with connection.cursor() as cursor:
        cursor.execute('SELECT secret FROM core_twofactorauth')
        (stored,) = cursor.fetchone()

    assert stored != secret
    assert TwoFactorAuth.objects.get(user=user).secret == secret


@override_settings(MIDDLEWARE=CORE_ONLY_MIDDLEWARE)
def test_activating_two_factor_from_the_profile(
    client: Client,
    user: User,
) -> None:
    client.force_login(user)

    # El GET emite el secreto pendiente y renderiza su QR.
    get_response = client.get(reverse('profile'))
    secret = client.session[_SESSION_PENDING_SECRET]

    assert get_response.status_code == 200
    html = get_response.content.decode()
    assert 'data:image/svg+xml;base64,' in html
    assert secret in html

    response = client.post(
        reverse('profile_two_factor_activate'),
        {'two_factor_code': _code(secret)},
    )

    assert response.status_code == 302
    assert TwoFactorAuth.objects.get(user=user).secret == secret
    assert _SESSION_PENDING_SECRET not in client.session


@override_settings(MIDDLEWARE=CORE_ONLY_MIDDLEWARE)
def test_activating_with_an_invalid_code_activates_nothing(
    client: Client,
    user: User,
) -> None:
    client.force_login(user)
    client.get(reverse('profile'))

    response = client.post(
        reverse('profile_two_factor_activate'),
        {'two_factor_code': '000000'},
    )

    assert response.status_code == 302
    assert not TwoFactorAuth.objects.filter(user=user).exists()


@override_settings(MIDDLEWARE=CORE_ONLY_MIDDLEWARE)
def test_the_pending_secret_survives_a_reload(
    client: Client,
    user: User,
) -> None:
    """Recargar el perfil no invalida el QR que el usuario ya escaneó."""
    client.force_login(user)

    client.get(reverse('profile'))
    first = client.session[_SESSION_PENDING_SECRET]
    client.get(reverse('profile'))

    assert client.session[_SESSION_PENDING_SECRET] == first


@override_settings(MIDDLEWARE=CORE_ONLY_MIDDLEWARE)
def test_deactivating_two_factor_from_the_profile(
    client: Client,
    user: User,
) -> None:
    TwoFactorAuth.objects.create(user=user, secret=totp.generate_secret())
    client.force_login(user)

    response = client.post(reverse('profile_two_factor_deactivate'))

    assert response.status_code == 302
    assert not TwoFactorAuth.objects.filter(user=user).exists()


def test_the_login_page_shows_the_code_field(
    client: Client,
    user: User,
) -> None:
    """
    El template de login renderiza con el campo que agrega `LoginForm`.

    Pide el fixture `user` aunque no lo use: sin ningún `User` en la
    base, `RequireInitialUserMiddleware` desvía cualquier página al
    alta del primer usuario y el login no llega a renderizarse.
    """
    response = client.get(reverse('login'))

    assert response.status_code == 200
    assert 'two_factor_code' in response.content.decode()


def test_login_end_to_end_with_two_factor(client: Client, user: User) -> None:
    secret = totp.generate_secret()
    TwoFactorAuth.objects.create(user=user, secret=secret)

    without_code = client.post(
        reverse('login'),
        {'username': user.username, 'password': PASSWORD},
    )

    assert without_code.status_code == 200
    assert not without_code.wsgi_request.user.is_authenticated

    with_code = client.post(
        reverse('login'),
        {
            'username': user.username,
            'password': PASSWORD,
            'two_factor_code': _code(secret),
        },
    )

    assert with_code.status_code == 302


def test_the_login_page_shows_field_errors(
    client: Client,
    user: User,
) -> None:
    """
    Un error de campo llega renderizado, no solo los `non_field_errors`.

    El navegador frena este envío con el `required` del widget, así que
    solo se llega sin validación HTML5 — pero es lo que distingue
    "mostramos el error" de "la página no dice nada".
    """
    response = client.post(reverse('login'), {'username': '', 'password': ''})
    html = response.content.decode()

    assert response.status_code == 200
    assert 'text-danger' in html
