"""Widgets de formulario genéricos, reusables entre apps."""

from __future__ import annotations

from django import forms


class PasswordToggleInput(forms.PasswordInput):
    """`PasswordInput` con botón para mostrar/ocultar y botón para copiar."""

    template_name = 'core/widgets/password_toggle_input.html'
