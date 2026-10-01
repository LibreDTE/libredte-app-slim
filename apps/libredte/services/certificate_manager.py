"""
Servicio: certificado digital de un usuario/contribuyente.

Único módulo que llama a `system.certificate.loader`/`trading_parties
.mandatario_manager` del SDK — nada fuera de `services/*.py` debe
tocarlo directamente.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from libredte_lib_sdk.billing.trading_parties import Certificate, Mandatario
from libredte_lib_sdk.exceptions import LibreDteSdkError

from ..models import Certificado, Contribuyente
from .exceptions import ServiceError, wrap
from .libredte_backend import get_backend

if TYPE_CHECKING:
    from django.contrib.auth.models import User


def load_real_certificate(data: bytes, password: str) -> Certificate:
    """Carga un certificado real (`.p12`/`.pfx`) — no persiste nada."""
    try:
        with get_backend() as backend:
            return backend.system.certificate.loader.load(data, password)
    except LibreDteSdkError as error:
        raise wrap(error) from error


def create_fake_certificate(
    rut: str,
    nombre: str,
    email: str,
) -> Certificate:
    """Genera un certificado ficticio (solo demo) — no persiste nada."""
    mandatario = Mandatario(run=rut, nombre=nombre, email=email)
    try:
        with get_backend() as backend:
            manager = backend.billing.trading_parties.mandatario_manager
            return manager.create_fake_certificate(mandatario)
    except LibreDteSdkError as error:
        raise wrap(error) from error


def save_certificate(usuario: User, certificate: Certificate) -> Certificado:
    """
    Guarda `certificate` (real o ficticio) como `Certificado` de `usuario`.

    `update_or_create` por `(usuario, certificado_id)`: subir de nuevo
    un certificado con el mismo `certificado_id` (el RUT del titular)
    actualiza el mismo `Certificado` en vez de crear uno aparte — todo
    contribuyente que ya lo tuviera enlazado pasa a usar la versión
    nueva automáticamente, sin tener que reenlazarlo.

    `valid_from`/`valid_until` llegan sin zona horaria en el ISO 8601 de
    la API — siempre en UTC (son `notBefore`/`notAfter` de X.509), así
    que se marcan como tal acá; no se leen ni interpretan de ninguna
    otra forma.
    """
    certificado, _creado = Certificado.objects.update_or_create(
        usuario=usuario,
        certificado_id=certificate.id or '',
        defaults={
            'nombre': certificate.name or '',
            'email': certificate.email or '',
            'issuer': certificate.issuer or '',
            'x509': certificate.certificate,
            'clave_privada': certificate.private_key,
            'valido_desde': (
                certificate.valid_from.replace(tzinfo=datetime.UTC)
                if certificate.valid_from
                else None
            ),
            'valido_hasta': (
                certificate.valid_until.replace(tzinfo=datetime.UTC)
                if certificate.valid_until
                else None
            ),
        },
    )
    return certificado


def certificate_for(contribuyente: Contribuyente) -> Certificate:
    """`Certificate` del SDK armado desde el certificado enlazado."""
    if contribuyente.certificado is None:
        raise ServiceError(
            f'{contribuyente} no tiene un certificado digital enlazado.',
        )
    return Certificate(
        certificate=contribuyente.certificado.x509,
        private_key=contribuyente.certificado.clave_privada,
    )
