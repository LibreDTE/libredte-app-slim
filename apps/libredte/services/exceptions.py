"""
Excepción de negocio compartida por `services/*`.

Único tipo de error que el resto de la app (forms, views, comandos)
necesita conocer o capturar al llamar a un servicio — nadie fuera de
`services/*.py` importa nada de `libredte_lib_sdk`, ni siquiera sus
excepciones.
"""

from __future__ import annotations

from libredte_lib_sdk.exceptions import LibreDteApiError, LibreDteSdkError


class ServiceError(Exception):
    """Error de negocio al orquestar el SDK — mensaje ya listo para UI."""


def wrap(error: LibreDteSdkError) -> ServiceError:
    """`ServiceError` con el mejor mensaje disponible de `error`."""
    if isinstance(error, LibreDteApiError):
        return ServiceError(error.full_message)
    return ServiceError(str(error))
