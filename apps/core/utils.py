"""Utilidades genéricas compartidas entre apps."""

from __future__ import annotations


def action_buttons(*links: tuple[str, str, str, str]) -> str:
    """
    Arma el HTML de una celda "Acciones": un botón-ícono por enlace.

    Cada `link` es `(title, icon, url, css_class)` — `icon` es el
    nombre del ícono de Font Awesome (sin el prefijo `fa-solid`/`fa-`) y
    `title` queda como `title`/`aria-label` (los botones son solo
    ícono, sin texto).
    """
    return ' '.join(
        f'<a href="{url}" class="btn btn-sm btn-outline-{css_class}" '
        f'title="{title}" aria-label="{title}">'
        f'<i class="fa-solid fa-{icon} fa-fw"></i></a>'
        for title, icon, url, css_class in links
    )
