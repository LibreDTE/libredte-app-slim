"""Versión y commit que se muestran en el pie."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.core import version

pytestmark = pytest.mark.django_db

COMPLETO = 'd305a17' + 'abcdef0123456789abcdef0123456789a'
OTRO = '9f8e7d6' + '0123456789abcdef0123456789abcdef0'


@pytest.fixture(autouse=True)
def _limpiar_cache() -> Iterator[None]:
    version.get_version.cache_clear()
    version.get_commit.cache_clear()
    version.get_backend_commit.cache_clear()
    yield
    version.get_version.cache_clear()
    version.get_commit.cache_clear()
    version.get_backend_commit.cache_clear()


def test_version_sale_de_pyproject() -> None:
    assert re.fullmatch(r'\d+\.\d+\.\d+\S*', version.get_version())


def test_commit_de_la_variable_se_guarda_completo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('SLIM_COMMIT', COMPLETO.upper())

    assert version.get_commit() == COMPLETO
    assert version.short_commit(version.get_commit()) == 'd305a17'


def test_commit_del_backend_solo_sale_de_su_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('LIBREDTE_BACKEND_COMMIT', raising=False)
    assert version.get_backend_commit() == ''

    version.get_backend_commit.cache_clear()
    monkeypatch.setenv('LIBREDTE_BACKEND_COMMIT', OTRO)
    assert version.get_backend_commit() == OTRO


def test_etiqueta_y_detalle_incluyen_el_backend_si_esta_definido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('SLIM_COMMIT', COMPLETO)
    monkeypatch.setenv('LIBREDTE_BACKEND_COMMIT', OTRO)

    assert version.get_version_label().endswith(
        ' · d305a17 · Core API 9f8e7d6'
    )
    assert f'Commit: {COMPLETO}' in version.get_version_detail()
    assert f'Core API: {OTRO}' in version.get_version_detail()


def test_etiqueta_sin_backend_no_lo_menciona(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('SLIM_COMMIT', COMPLETO)
    monkeypatch.delenv('LIBREDTE_BACKEND_COMMIT', raising=False)

    assert 'Core API' not in version.get_version_label()
    assert 'Core API' not in version.get_version_detail()


def test_commit_invalido_de_la_variable_se_ignora(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('SLIM_COMMIT', '<script>')
    monkeypatch.setattr(subprocess, 'run', _git_sin_resultado)

    assert version.get_commit() == ''


def test_sin_variable_ni_git_no_hay_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('SLIM_COMMIT', raising=False)
    monkeypatch.setattr(subprocess, 'run', _git_inexistente)

    assert version.get_commit() == ''
    assert version.get_version_label() == version.get_version()


def test_pie_muestra_version_y_commit(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('SLIM_COMMIT', 'abc1234' + 'f' * 33)
    # Sin ningún usuario, el middleware desvía al alta del primero.
    User.objects.create_user('demo', password='demo12345')

    respuesta = client.get(reverse('login'))

    assert f'{version.get_version()} · abc1234' in respuesta.content.decode()


def _git_sin_resultado(*_args: object, **_kwargs: object) -> None:
    raise subprocess.SubprocessError


def _git_inexistente(*_args: object, **_kwargs: object) -> None:
    raise FileNotFoundError
