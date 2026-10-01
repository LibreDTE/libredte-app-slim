"""Tarea de la emisión masiva y su encolado (ver `services/bulk_biller`)."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

from celery import shared_task
from django.contrib.auth.models import User
from kombu.exceptions import OperationalError
from redis.exceptions import RedisError

from apps.libredte.models import Contribuyente
from apps.libredte.services.exceptions import ServiceError

from ..services import bulk_biller


# `acks_late=False` y sin reintentos: si el worker cae a mitad de camino,
# repetir la tarea emitiría de nuevo lo que ya alcanzó a emitir.
@shared_task(
    name='billing.process_bulk_billing',
    queue='emision_masiva',
    acks_late=False,
)
def process_bulk_billing(
    contribuyente_id: int,
    usuario_id: int,
    ruta: str,
    *,
    dte_real: bool,
    pdf: bool,
) -> dict[str, bool | str | int | list[dict[str, Any]] | None]:
    """
    Emite los documentos de una planilla y avisa del resultado por correo.

    Recibe la ruta del archivo que dejó `bulk_biller.save_documentos()`.
    Al terminar, bien o mal, libera el bloqueo de la planilla y borra ese
    archivo.

    :param contribuyente_id: El emisor de los documentos.
    :type contribuyente_id: int
    :param usuario_id: Quien subió la planilla.
    :type usuario_id: int
    :param ruta: El archivo JSON con los documentos ya parseados.
    :type ruta: str
    :param dte_real: `True` para emitir el DTE real.
    :type dte_real: bool
    :param pdf: `True` para generar los PDF (el correo lleva el enlace de
        descarga).
    :type pdf: bool
    :return: `status`, `envio`, `pdf_fallidos`, `pdf_enlace` y `result`, con
        el resultado de cada documento.
    :rtype: dict[str, bool | str | int | list[dict[str, Any]] | None]
    :raises ObjectDoesNotExist: Si el contribuyente o el usuario ya no
        existen; en ese caso no sale ningún correo.
    """
    archivo = Path(ruta)
    try:
        emision = bulk_biller.process(
            Contribuyente.objects.get(pk=contribuyente_id),
            bulk_biller.load_documentos(archivo),
            User.objects.get(pk=usuario_id),
            dte_real=dte_real,
            pdf=pdf,
        )
    finally:
        bulk_biller.release_lock(contribuyente_id, archivo.stem)
        archivo.unlink(missing_ok=True)
    return {
        'status': True,
        'envio': emision.envio,
        'pdf_fallidos': emision.pdf_fallidos,
        'pdf_enlace': emision.pdf_enlace,
        'result': [asdict(resultado) for resultado in emision.resultados],
    }


def enqueue_bulk_billing(
    contribuyente: Contribuyente,
    usuario: User,
    documentos: list[dict[str, Any]],
    *,
    dte_real: bool,
    pdf: bool,
) -> None:
    """
    Guarda los documentos de la planilla, toma su bloqueo y encola la emisión.

    :param contribuyente: El emisor de los documentos.
    :type contribuyente: Contribuyente
    :param usuario: Quien subió la planilla.
    :type usuario: User
    :param documentos: Los documentos que entregó `bulk_biller.parse()`.
    :type documentos: list[dict[str, Any]]
    :param dte_real: `True` para emitir el DTE real.
    :type dte_real: bool
    :param pdf: `True` para generar los PDF.
    :type pdf: bool
    :raises bulk_biller.BulkBillingInProgressError: Si esa misma planilla ya
        está en proceso.
    :raises ServiceError: Si no se pudo tomar el bloqueo o encolar.
    """
    ruta = bulk_biller.save_documentos(contribuyente, documentos)
    try:
        bulk_biller.acquire_lock(contribuyente.pk, ruta.stem)
        process_bulk_billing.delay(
            contribuyente.pk,
            usuario.pk,
            str(ruta),
            dte_real=dte_real,
            pdf=pdf,
        )
    except (OperationalError, RedisError) as error:
        # Nada quedó encolado: se libera para poder reintentar.
        with suppress(RedisError):
            bulk_biller.release_lock(contribuyente.pk, ruta.stem)
        ruta.unlink(missing_ok=True)
        raise ServiceError(
            'No fue posible programar la emisión masiva. Intente nuevamente '
            'en unos minutos.',
        ) from error
