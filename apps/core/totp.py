"""
Segundo factor de autenticación (TOTP, RFC 6238).

Toda la mecánica del TOTP vive acá — el modelo (`TwoFactorAuth`), el
formulario de login y la vista de perfil solo llaman a estas funciones
y nunca importan `pyotp`/`qrcode` directamente.
"""

from __future__ import annotations

import base64

import pyotp
import qrcode
import qrcode.image.svg

# Nombre que la app autenticadora muestra junto a la cuenta.
ISSUER = 'LibreDTE Slim'


def generate_secret() -> str:
    """Secreto nuevo en base32, listo para `TwoFactorAuth.secret`."""
    return pyotp.random_base32()


def verify(secret: str, code: str) -> bool:
    """`True` si `code` es el TOTP vigente para `secret`."""
    if not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip())


def provisioning_uri(username: str, secret: str) -> str:
    """URI `otpauth://` que se codifica en el QR de enrolamiento."""
    return pyotp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=ISSUER,
    )


def qr_data_uri(otpauth_uri: str) -> str:
    """
    El QR de `otpauth_uri` como `data:` URI, para un `<img src="...">`.

    Devuelve un `data:` URI y no el SVG en crudo a propósito: así el
    template lo interpola como cualquier atributo (escapado por Django)
    y no hace falta `mark_safe` sobre un bloque de markup.
    """
    image = qrcode.make(
        otpauth_uri,
        image_factory=qrcode.image.svg.SvgPathImage,
    )
    svg = image.to_string()
    return f'data:image/svg+xml;base64,{base64.b64encode(svg).decode()}'
