"""Tests del token de API que el usuario emite desde su perfil."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token

from apps.core.api import PublicApiMixin
from apps.core.tests.test_two_factor import CORE_ONLY_MIDDLEWARE

pytestmark = pytest.mark.django_db

PASSWORD = 'demo12345'


@pytest.fixture
def user() -> User:
    return User.objects.create_user(username='demo', password=PASSWORD)


@override_settings(MIDDLEWARE=CORE_ONLY_MIDDLEWARE)
def test_generating_a_token_from_the_profile(
    client: Client,
    user: User,
) -> None:
    client.force_login(user)

    response = client.post(reverse('profile_api_token_generate'))

    assert response.status_code == 302
    assert Token.objects.filter(user=user).count() == 1


@override_settings(MIDDLEWARE=CORE_ONLY_MIDDLEWARE)
def test_regenerating_replaces_the_previous_token(
    client: Client,
    user: User,
) -> None:
    """El token anterior deja de existir, no queda un segundo válido."""
    previous = Token.objects.create(user=user).key
    client.force_login(user)

    client.post(reverse('profile_api_token_generate'))

    assert Token.objects.filter(user=user).count() == 1
    assert Token.objects.get(user=user).key != previous
    assert not Token.objects.filter(key=previous).exists()


@override_settings(MIDDLEWARE=CORE_ONLY_MIDDLEWARE)
def test_deleting_the_token(client: Client, user: User) -> None:
    Token.objects.create(user=user)
    client.force_login(user)

    response = client.post(reverse('profile_api_token_delete'))

    assert response.status_code == 302
    assert not Token.objects.filter(user=user).exists()


@override_settings(MIDDLEWARE=CORE_ONLY_MIDDLEWARE)
def test_the_profile_shows_the_token(client: Client, user: User) -> None:
    token = Token.objects.create(user=user)
    client.force_login(user)

    response = client.get(reverse('profile'))

    assert token.key in response.content.decode()


def test_the_public_api_base_accepts_token_and_session() -> None:
    """
    El token solo autentica donde se hereda de `PublicApiMixin`.

    Es lo que evita que un endpoint quede abierto a un cliente externo
    por omisión (ver `REST_FRAMEWORK` en `config/settings.py`).
    """
    names = [cls.__name__ for cls in PublicApiMixin.authentication_classes]

    assert names == ['TokenAuthentication', 'SessionAuthentication']


def test_the_default_authentication_has_no_token() -> None:
    from django.conf import settings

    defaults = settings.REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']

    assert not any('TokenAuthentication' in cls for cls in defaults)


@override_settings(MIDDLEWARE=CORE_ONLY_MIDDLEWARE)
def test_the_profile_links_to_the_api_documentation(
    client: Client,
    user: User,
) -> None:
    """El token no sirve de nada si no se sabe contra qué llamarlo."""
    client.force_login(user)

    html = client.get(reverse('profile')).content.decode()

    assert reverse('api_docs') in html
