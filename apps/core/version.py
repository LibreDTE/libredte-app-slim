"""Versión de la app y commits con los que corre, para mostrar en el pie."""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from functools import cache
from pathlib import Path

from django.conf import settings

SHORT_COMMIT_LENGTH = 7

_COMMIT_RE = re.compile(r'[0-9a-f]{7,64}')


@cache
def get_version() -> str:
    """
    La `version` de `pyproject.toml` (ej. `0.1.0b1`), o `''` si no se lee.

    `pyproject.toml` es la única fuente de la versión. Se lee el archivo
    en vez de los metadatos instalados (`importlib.metadata`) porque la
    app se ejecuta desde su carpeta, sin instalarse como paquete.
    """
    try:
        with (Path(settings.BASE_DIR) / 'pyproject.toml').open('rb') as file:
            version = tomllib.load(file)['project']['version']
    except OSError, KeyError, tomllib.TOMLDecodeError:
        return ''
    return str(version)


def _normalize_commit(value: str) -> str:
    """El hash completo en minúsculas, o `''` si no es un hash."""
    value = value.strip().lower()
    return value if _COMMIT_RE.fullmatch(value) else ''


def short_commit(commit: str) -> str:
    """Los primeros 7 caracteres del hash (`''` si no hay hash)."""
    return commit[:SHORT_COMMIT_LENGTH]


@cache
def get_commit() -> str:
    """
    El commit completo del código de la app, o `''` si se desconoce.

    Se guarda completo (permite comparar contra el repositorio, ej. para
    saber si hay una versión más nueva); el recorte a 7 caracteres es
    solo de presentación (`short_commit()`).

    Primero `SLIM_COMMIT`: quien construye la imagen (Docker) la define,
    porque dentro de la imagen no hay `.git`. Sin ella, se le pregunta a
    git (desarrollo desde un clon).
    """
    commit = _normalize_commit(os.environ.get('SLIM_COMMIT', ''))
    if commit:
        return commit
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return ''
    if result.returncode != 0:
        return ''
    return _normalize_commit(result.stdout)


@cache
def get_backend_commit() -> str:
    """
    El commit completo de la imagen de LibreDTE Lib Core API, o `''`.

    Solo existe la variable `LIBREDTE_BACKEND_COMMIT`: quien despliega
    la define (la app no puede averiguarlo del backend). Sin ella no se
    muestra.
    """
    return _normalize_commit(os.environ.get('LIBREDTE_BACKEND_COMMIT', ''))


def get_version_label() -> str:
    """Lo que va en el pie: `0.1.0b1 · d305a17 · Core API 9f8e7d6`."""
    parts = [get_version(), short_commit(get_commit())]
    backend = short_commit(get_backend_commit())
    if backend:
        parts.append(f'Core API {backend}')
    return ' · '.join(part for part in parts if part)


def get_version_detail() -> str:
    """Los datos completos, para el `title` del pie y para soporte."""
    lines = [f'LibreDTE Slim {get_version()}'.strip()]
    if commit := get_commit():
        lines.append(f'Commit: {commit}')
    if backend := get_backend_commit():
        lines.append(f'Core API: {backend}')
    return '\n'.join(lines)
