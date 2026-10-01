"""Formulario de configuración del plugin `libredte_lib_api`."""

from __future__ import annotations

from typing import Any

from django import forms
from django.conf import settings

from apps.core.widgets import PasswordToggleInput

from .config_resolver import resolve_api_token, resolve_base_url


class LibredteLibApiConfigForm(forms.Form):
    """
    `base_url`/`api_token`/`auth_scheme` de la instancia de LibreDTE Lib API.

    `base_url`/`api_token` opcionales: vacíos, `LibredteLibApiPlugin
    .get_backend()` usa los valores globales de la plataforma
    (`PLUGIN_LIBREDTE_BACKEND_API_URL`/`PLUGIN_LIBREDTE_BACKEND_API_TOKEN`)
    — un tenant solo necesita llenar esto si quiere apuntar a SU
    PROPIA instancia, no a la que ya trae la plataforma por defecto.

    `auth_scheme` siempre trae un valor explícito (`'Bearer'` por
    defecto) — a diferencia de los otros dos, no queda vacío: cada
    instancia de LibreDTE Lib API espera un esquema fijo (`Bearer` la
    oficial, `Token` si se accede vía API Gateway), no tiene sentido
    "heredar" el de la plataforma si se está apuntando a otra URL.
    """

    base_url = forms.URLField(
        label='URL base',
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control'}),
    )
    api_token = forms.CharField(
        label='Token de API',
        required=False,
        widget=PasswordToggleInput(
            attrs={'class': 'form-control'},
            render_value=True,
        ),
    )
    auth_scheme = forms.ChoiceField(
        label='Esquema de autenticación',
        choices=[('Bearer', 'Bearer'), ('Token', 'Token')],
        initial='Bearer',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Agrega el valor global de reserva como placeholder/ayuda."""
        super().__init__(*args, **kwargs)
        self.fields['base_url'].widget.attrs['placeholder'] = (
            settings.PLUGIN_LIBREDTE_BACKEND_API_URL
        )
        self.fields[
            'base_url'
        ].help_text = (
            'Vacío usa la URL global de la plataforma (la del placeholder).'
        )
        if settings.PLUGIN_LIBREDTE_BACKEND_API_TOKEN:
            self.fields[
                'api_token'
            ].help_text = (
                'Vacío usa el token global configurado en la plataforma.'
            )

    def clean(self) -> dict[str, Any]:
        """
        Evita filtrar el token global a una URL que no sea la de la plataforma.

        Si el token que terminaría usando esta config es el global
        (porque el tenant no puso el suyo), la URL también tiene que
        ser la global — de lo contrario `get_backend()` mandaría el
        token de la plataforma a una URL que el tenant controla.
        """
        cleaned_data = super().clean() or {}
        global_token = settings.PLUGIN_LIBREDTE_BACKEND_API_TOKEN
        if (
            global_token
            and resolve_api_token(cleaned_data) == global_token
            and resolve_base_url(cleaned_data)
            != settings.PLUGIN_LIBREDTE_BACKEND_API_URL
        ):
            raise forms.ValidationError(
                'No puedes dejar el token vacío (usa el global de la '
                'plataforma) con una URL propia — configura tu propio '
                'token, o deja también la URL vacía.'
            )
        return cleaned_data
