"""
Servicio: ejemplos reales de documentos (`billing.document.examples`).

Único módulo que llama a ese worker del SDK — nada fuera de
`services/*.py` debe tocarlo directamente. Uso exclusivo de datos de
prueba hoy: no hay equivalente en la emisión real de un DTE (ahí los
datos del documento los arma quien factura, no un catálogo de ejemplos
de prueba).
"""

from __future__ import annotations

from libredte_lib_sdk.billing.document import Example, ExampleSummary
from libredte_lib_sdk.exceptions import LibreDteSdkError

from apps.libredte.services.exceptions import wrap
from apps.libredte.services.libredte_backend import get_backend


def list_examples() -> list[ExampleSummary]:
    """Ejemplos disponibles (`id`, `category`, `case`)."""
    try:
        with get_backend() as backend:
            return backend.billing.document.examples.list()
    except LibreDteSdkError as error:
        raise wrap(error) from error


def get_example(example_id: str) -> Example:
    """Datos completos del ejemplo `example_id`."""
    try:
        with get_backend() as backend:
            return backend.billing.document.examples.get(example_id)
    except LibreDteSdkError as error:
        raise wrap(error) from error
