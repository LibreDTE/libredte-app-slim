"""Formularios de `core`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User

from . import totp
from .models import TwoFactorAuth

if TYPE_CHECKING:
    _ProfileFormBase = forms.ModelForm[User]
else:
    # `ModelForm` no es `Generic` en tiempo de ejecución (solo en los
    # stubs de `django-stubs`) — subscribir `forms.ModelForm[...]`
    # directo como base real lanzaría `TypeError: not subscriptable`
    # al importar el módulo.
    _ProfileFormBase = forms.ModelForm


class LoginForm(AuthenticationForm):
    """
    `AuthenticationForm` + el código TOTP de quien tenga 2FA activo.

    El campo va siempre visible y opcional (no en un segundo paso tras
    validar la contraseña): pedirlo recién después obligaría a decirle
    al visitante que la contraseña era correcta antes de completar la
    autenticación, que es justo lo que el segundo factor busca evitar.
    Quien no tiene 2FA lo deja en blanco y no cambia nada para él.
    """

    two_factor_code = forms.CharField(
        label='Código 2FA',
        required=False,
        max_length=10,
        widget=forms.TextInput(
            attrs={
                'autocomplete': 'one-time-code',
                'inputmode': 'numeric',
            },
        ),
        help_text='Déjalo vacío si no tienes activada la verificación '
        'en dos pasos.',
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Agrega `form-control` a los widgets que hereda de Django."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def confirm_login_allowed(self, user: User) -> None:
        """
        Exige el TOTP válido, además de lo que ya valida Django.

        Se hace acá y no en `clean()` porque `AuthenticationForm` llama
        a este hook únicamente cuando el usuario y la contraseña ya
        resultaron correctos — sin eso, un código inválido y una
        contraseña inválida darían errores distintos y revelarían
        cuál de los dos falló.
        """
        super().confirm_login_allowed(user)
        two_factor = TwoFactorAuth.objects.filter(user=user).first()
        if two_factor is None:
            return
        code = self.cleaned_data.get('two_factor_code', '')
        if not totp.verify(two_factor.secret, code):
            raise forms.ValidationError(
                'El código de verificación en dos pasos no es válido.',
                code='invalid_2fa',
            )


class TwoFactorActivateForm(forms.Form):
    """
    Confirma que la app autenticadora quedó bien enrolada.

    Validar el código antes de guardar el secreto es lo que evita dejar
    la cuenta con un 2FA que el usuario no puede responder (QR mal
    escaneado, reloj desfasado): si no verifica, no se activa nada.
    El secreto no viaja en el formulario — se guarda en la sesión
    mientras dura el enrolamiento (ver `apps/core/views/hub.py`).
    """

    two_factor_code = forms.CharField(
        label='Código de verificación',
        max_length=10,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'autocomplete': 'one-time-code',
                'inputmode': 'numeric',
            },
        ),
        help_text='El código de 6 dígitos que muestra la aplicación.',
    )

    def __init__(self, *args: Any, secret: str = '', **kwargs: Any) -> None:
        """Guarda el secreto pendiente contra el que se valida el código."""
        super().__init__(*args, **kwargs)
        self.secret = secret

    def clean_two_factor_code(self) -> str:
        """Rechaza el código si no corresponde al secreto pendiente."""
        code: str = self.cleaned_data['two_factor_code']
        if not self.secret or not totp.verify(self.secret, code):
            raise forms.ValidationError(
                'El código no coincide. Vuelve a escanear el código '
                'QR y prueba con el código que muestra la aplicación '
                'en ese momento.',
            )
        return code


class ProfileForm(_ProfileFormBase):
    """
    Datos básicos del usuario logueado (pestaña "Datos básicos").

    `username` es editable — el `ModelForm` ya valida formato (los
    mismos validadores de `User.username`, ej. sin espacios) y unicidad
    excluyendo la instancia actual, sin necesitar lógica extra acá.
    Cambiarlo no cierra la sesión: Django resuelve `request.user` por
    PK, no por username.
    """

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class ProfilePasswordChangeForm(PasswordChangeForm):
    """
    `PasswordChangeForm` de Django + clase `form-control` en sus widgets.

    No es nuestro (como `AuthenticationForm`/`UserCreationForm`), pero a
    diferencia de esos, acá conviene subclasificarlo (no usar el filtro
    `add_class` en el template) para poder reusar `_field.html` tal cual
    lo usa el resto de los forms de la app.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Agrega `form-control` a cada widget heredado de Django."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class PluginActivationForm(forms.Form):
    """
    El único campo de `PluginConfig` que `core` sabe pedir: `active`.

    Se renderiza junto al `config_form` propio de cada `BasePlugin` (dos
    forms, un solo `<form>` HTML — ver
    `apps/core/views/settings.py::plugin_configure`), porque `active`
    no es parte del contrato de configuración de ningún plugin, es la
    activación misma, que decide `core` al guardar `PluginConfig`.
    """

    active = forms.BooleanField(
        required=False,
        label='Activo',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(
        self,
        *args: Any,
        deprecated: bool = False,
        was_active: bool = False,
        **kwargs: Any,
    ) -> None:
        """`deprecated`/`was_active` habilitan `clean_active()`."""
        self.deprecated = deprecated
        self.was_active = was_active
        super().__init__(*args, **kwargs)

    def clean_active(self) -> bool:
        """Un plugin deprecado no se puede activar si no lo estaba ya."""
        active = bool(self.cleaned_data['active'])
        if active and self.deprecated and not self.was_active:
            raise forms.ValidationError(
                'Este plugin está deprecado — no se puede activar.'
            )
        return active


class SudoForm(forms.Form):
    """Pide la contraseña del usuario actual, para activar el modo sudo."""

    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'autofocus': True},
        ),
    )

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        """Guarda `user` — `clean_password()` valida contra su hash."""
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self) -> str:
        """Rechaza si la contraseña no corresponde al usuario actual."""
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise forms.ValidationError('Contraseña incorrecta.')
        return str(password)
