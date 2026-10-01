"""
App Celery del proyecto.

Se configura desde `config/settings.py` (prefijo `CELERY_`) y descubre
las tareas en el `tasks.py` de cada app.
"""

from __future__ import annotations

import os

from celery import Celery

# El worker no pasa por `manage.py`.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('libredte_slim')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
