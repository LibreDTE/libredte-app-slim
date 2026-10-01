"""`/health/`: responde sin sesión, incluso con la base vacía."""

from __future__ import annotations

import pytest
from django.db import OperationalError
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_health_ok_sin_usuarios_ni_sesion(client: Client) -> None:
    respuesta = client.get(reverse('health'))

    assert respuesta.status_code == 200
    assert respuesta.json() == {'status': 'ok'}


def test_health_503_si_la_base_falla(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _falla(*_args: object, **_kwargs: object) -> None:
        raise OperationalError('sin base')

    monkeypatch.setattr(
        'django.db.backends.utils.CursorWrapper.execute',
        _falla,
    )

    respuesta = client.get(reverse('health'))

    assert respuesta.status_code == 503
    assert respuesta.json() == {'status': 'error'}


def test_health_rechaza_post(client: Client) -> None:
    assert client.post(reverse('health')).status_code == 405
