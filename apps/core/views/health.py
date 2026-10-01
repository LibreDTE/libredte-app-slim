"""Estado de salud de la app, para los healthchecks del despliegue."""

from __future__ import annotations

import logging

from django.db import Error as DatabaseError
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@require_safe
@never_cache
def health(_request: HttpRequest) -> JsonResponse:
    """
    `200` si la app responde y la base de datos contesta; `503` si no.

    No exige sesión. No consulta Redis ni la API de LibreDTE: que una
    dependencia externa caiga no debe dar por muerto al proceso web.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        logger.exception('Healthcheck: la base de datos no responde.')
        return JsonResponse({'status': 'error'}, status=503)
    return JsonResponse({'status': 'ok'})
