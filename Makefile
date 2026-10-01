.PHONY: install-dev lint format format-check typecheck test test-live check migrate makemigrations seed seed-demo run worker clean

VENV = .venv
VENV_READY = $(VENV)/.installed

$(VENV_READY): pyproject.toml
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e '.[dev]'
	touch $(VENV_READY)

install-dev: $(VENV_READY)

lint: $(VENV_READY)
	$(VENV)/bin/ruff check .

format: $(VENV_READY)
	$(VENV)/bin/ruff format .

format-check: $(VENV_READY)
	$(VENV)/bin/ruff format --check .

typecheck: $(VENV_READY)
	$(VENV)/bin/mypy

test: $(VENV_READY)
	$(VENV)/bin/pytest -v

# Tests de integración: golpean la API real de LibreDTE Lib, sin mocks.
# Excluidos de `test`/`check` a propósito (requieren red, y dependen de
# un servidor corriendo en `LIBREDTE_LIB_SDK_BASE_URL`).
test-live: $(VENV_READY)
	$(VENV)/bin/pytest -v -m live

check: lint format-check typecheck test

makemigrations: $(VENV_READY)
	$(VENV)/bin/python manage.py makemigrations

migrate: $(VENV_READY)
	$(VENV)/bin/python manage.py migrate

seed: $(VENV_READY)
	$(VENV)/bin/python manage.py seed

seed-demo: $(VENV_READY)
	$(VENV)/bin/python manage.py seed_demo

run: $(VENV_READY)
	$(VENV)/bin/python manage.py runserver

# Worker de Celery (necesita Redis, ver `CELERY_BROKER_URL`). En
# producción cada cola tiene su propio worker (ver `Procfile`); acá uno
# solo atiende todas.
#
# `--prefetch-multiplier=1`, igual que el worker de `emision_masiva`:
# con tareas largas, cada proceso reserva a lo sumo una tarea más
# mientras trabaja, en vez de cuatro que esperarían detrás de la que
# está corriendo. Es lo que recomienda la documentación de Celery para
# tareas largas; no llega a "una a la vez" porque para eso hace falta
# `acks_late`, que la emisión masiva no puede usar (ver
# `apps/billing/tasks/bulk_biller.py`).
worker: $(VENV_READY)
	$(VENV)/bin/celery -A config worker -Q default,emision_masiva --prefetch-multiplier=1 --loglevel=info

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
