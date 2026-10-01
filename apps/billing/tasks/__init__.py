"""
Tareas en segundo plano de `billing` (ver `config/celery.py`).

Un módulo por servicio que se ejecuta en segundo plano, con el mismo
nombre que el servicio. Las tareas se reexportan acá porque Celery las
descubre importando `apps.billing.tasks` (`autodiscover_tasks()`): una
tarea que no se importe desde este paquete no queda registrada en el
worker.
"""

from __future__ import annotations

from .bulk_biller import enqueue_bulk_billing, process_bulk_billing

__all__ = ('enqueue_bulk_billing', 'process_bulk_billing')
