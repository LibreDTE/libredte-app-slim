"""
Paquete de configuración del proyecto.

Carga la app Celery junto con Django, para que `@shared_task` la use.
"""

from __future__ import annotations

from .celery import app as celery_app

__all__ = ('celery_app',)
