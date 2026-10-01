"""Tests para `plugin/base.py`."""

from __future__ import annotations

from django.template import Context, Template

from apps.core.plugin.base import BasePlugin


class _DummyPlugin(BasePlugin):
    """Plugin de mentira, solo para probar el mecanismo — sin dominio."""

    id = 'dummy'
    label = 'Dummy'


def test_a_plugin_class_renders_in_a_template_without_instantiating() -> None:
    """
    Una CLASE `BasePlugin` en el contexto no debe intentar instanciarse.

    Django llama cualquier "callable" que resuelve en un template
    (toda clase lo es) salvo que declare `do_not_call_in_templates` —
    sin eso, `{{ plugin.label }}` con `plugin` = la clase intentaría
    `_DummyPlugin()` (sin el `config` requerido), fallaría, y Django lo
    silenciaría como variable inválida (string vacío, sin excepción).
    """
    template = Template('{{ plugin.label }}')

    rendered = template.render(Context({'plugin': _DummyPlugin}))

    assert rendered == 'Dummy'
