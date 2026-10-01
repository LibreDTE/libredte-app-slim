"""
Tests para `services.certificate_manager.save_certificate()`.

`load_real_certificate()`/`create_fake_certificate()`/`certificate_for()`
llaman a la API real de LibreDTE Lib o son un simple chequeo de `None`
— no se prueban acá (mismo criterio que `test_biller.py`). Esto solo
prueba `save_certificate()`, que es puramente local (`update_or_create`
+ el manejo de zona horaria de `valid_from`/`valid_until`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.contrib.auth.models import User
from libredte_lib_sdk.billing.trading_parties import Certificate

from apps.libredte.models import Certificado
from apps.libredte.services.certificate_manager import save_certificate

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario() -> User:
    return User.objects.create_user('demo', password='demo12345')


def _certificate(
    *,
    certificado_id: str | None = '12345678-5',
    name: str | None = 'Juan Pérez',
    email: str | None = 'juan@example.com',
    issuer: str | None = 'E-CERTCHILE',
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> Certificate:
    return Certificate(
        certificate='-----BEGIN CERTIFICATE-----...',
        private_key='-----BEGIN PRIVATE KEY-----...',
        id=certificado_id,
        name=name,
        email=email,
        issuer=issuer,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def test_crea_un_certificado_nuevo_si_no_existe(usuario: User) -> None:
    certificado = save_certificate(usuario, _certificate())

    assert certificado.usuario == usuario
    assert certificado.certificado_id == '12345678-5'
    assert certificado.nombre == 'Juan Pérez'
    assert certificado.email == 'juan@example.com'
    assert certificado.issuer == 'E-CERTCHILE'


def test_resubir_el_mismo_certificado_actualiza_en_vez_de_duplicar(
    usuario: User,
) -> None:
    """Mismo `(usuario, certificado_id)` — se reemplaza, no se duplica."""
    save_certificate(usuario, _certificate(name='Nombre antiguo'))
    save_certificate(usuario, _certificate(name='Nombre renovado'))

    assert Certificado.objects.filter(usuario=usuario).count() == 1
    certificado = Certificado.objects.get(usuario=usuario)
    assert certificado.nombre == 'Nombre renovado'


def test_certificado_id_ausente_no_falla_y_queda_en_blanco(
    usuario: User,
) -> None:
    certificado = save_certificate(usuario, _certificate(certificado_id=None))

    assert certificado.certificado_id == ''


def test_valid_from_y_valid_until_quedan_en_utc(usuario: User) -> None:
    """
    `valid_from`/`valid_until` llegan sin zona horaria (siempre UTC).

    Se marcan como tal acá — un datetime "naive" guardado tal cual en
    un campo `DateTimeField` (`USE_TZ=True`) dispararía un warning y
    quedaría interpretado en la zona horaria local, no en UTC.
    """
    # Deliberadamente "naive" (sin tzinfo) — así es como el SDK entrega
    # `Certificate.valid_from`/`.valid_until` (ver docstring de arriba).
    naive_desde = datetime(2024, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    naive_hasta = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)

    certificado = save_certificate(
        usuario,
        _certificate(valid_from=naive_desde, valid_until=naive_hasta),
    )

    assert certificado.valido_desde == datetime(2024, 1, 1, tzinfo=UTC)
    assert certificado.valido_hasta == datetime(2026, 1, 1, tzinfo=UTC)


def test_valid_from_y_valid_until_ausentes_quedan_none(
    usuario: User,
) -> None:
    certificado = save_certificate(usuario, _certificate())

    assert certificado.valido_desde is None
    assert certificado.valido_hasta is None
