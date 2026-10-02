# Imagen de LibreDTE Slim. Sirve para el proceso web, los workers de Celery y las
# tareas de `manage.py`: cambia solo el comando. La imagen sola no basta para
# operar la aplicación (necesita PostgreSQL, Valkey/Redis y LibreDTE Lib Core
# API): el stack Docker que la usa es
# https://github.com/LibreDTE/libredte-docker-slim
ARG PYTHON_VERSION=3.14

# --- Etapa de construcción: dependencias y código ---
FROM python:${PYTHON_VERSION}-slim AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

# Las dependencias salen de `pyproject.toml` (sin los extras `dev`): el proyecto
# no se instala como paquete, se ejecuta desde /app.
COPY pyproject.toml /app/pyproject.toml
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python --requirement /app/pyproject.toml

COPY . /app

# Hash completo del commit, para el pie de la aplicación y para saber con qué
# código corre un servidor. Lo entrega quien construye (`--build-arg
# SLIM_COMMIT=...`, como hace el workflow de publicación); si falta, se toma del
# repositorio (construcción desde un contexto de Git que conserva `.git`).
ARG SLIM_COMMIT=
RUN commit="${SLIM_COMMIT}"; \
    if [ -z "${commit}" ] && [ -d /app/.git ]; then commit="$(git -C /app rev-parse HEAD)"; fi; \
    echo "${commit}" > /slim-commit; \
    rm -rf /app/.git

# --- Imagen final ---
FROM python:${PYTHON_VERSION}-slim

ARG SLIM_COMMIT=

# `SLIM_COMMIT` vacío (construcción sin el argumento): el hash queda en
# /etc/slim-commit, que el entrypoint del stack exporta.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SLIM_COMMIT=${SLIM_COMMIT} \
    STATIC_ROOT=/srv/static \
    MEDIA_ROOT=/var/lib/slim/media \
    EMISION_MASIVA_PDF_DIR=/var/lib/slim/emision_masiva

# UID fijo: los volúmenes compartidos (media, emision_masiva) deben tener el
# mismo dueño en todos los contenedores que corren Slim.
RUN groupadd --gid 10001 slim \
    && useradd --uid 10001 --gid slim --no-create-home --shell /usr/sbin/nologin slim \
    && mkdir -p /srv/static /var/lib/slim/media /var/lib/slim/emision_masiva /var/lib/slim/state \
    && chown -R slim:slim /srv/static /var/lib/slim \
    && chmod 700 /var/lib/slim/state

COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app
COPY --from=build /slim-commit /etc/slim-commit

WORKDIR /app
USER slim
