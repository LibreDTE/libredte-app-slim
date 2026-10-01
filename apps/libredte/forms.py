"""Formularios de `libredte`: contribuyente, certificado, sucursal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django import forms
from rutificador import Rut

from .models import (
    ActividadEconomica,
    Certificado,
    Contribuyente,
    ContribuyenteActividadEconomica,
    Sucursal,
)
from .services import certificate_manager
from .services.exceptions import ServiceError


class RutField(forms.CharField):
    """
    RUT chileno en un solo input de texto (ej. `12.345.678-5`).

    Valida el dígito verificador con `rutificador` y devuelve el valor
    ya normalizado (`12345678-5`) — separarlo en `rut`/`dv` (las
    columnas reales de `Contribuyente`/`Receptor`) es responsabilidad
    del `ModelForm` que lo use, no de este campo.
    """

    widget = forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': '12.345.678-5'},
    )

    default_error_messages = {
        'invalid': 'Ingresa un RUT chileno válido (ej. 12.345.678-5).',
    }

    def to_python(self, value: Any | None) -> str | None:
        """Valida `value` con `rutificador` y devuelve su forma normal."""
        value = super().to_python(value)
        if not value:
            return value
        resultado = Rut.parse(value)
        if resultado.estado != 'valido':
            raise forms.ValidationError(
                self.error_messages['invalid'],
                code='invalid',
            )
        return resultado.normalizado


if TYPE_CHECKING:
    _ContribuyenteFormBase = forms.ModelForm[Contribuyente]
else:
    # Los `ModelForm` de Django no son `Generic` en tiempo de ejecución
    # (solo en los stubs de `django-stubs`) — subscribir
    # `forms.ModelForm[...]` directo como base real lanzaría
    # `TypeError: not subscriptable` al importar el módulo.
    _ContribuyenteFormBase = forms.ModelForm


class ContribuyenteForm(_ContribuyenteFormBase):
    """
    Datos básicos (esenciales) de un contribuyente.

    Usado en el alta (`ContribuyenteWizardView`) — solo pide lo
    imprescindible para operar. La card "Datos básicos" de
    `/settings/libredte/empresa/` usa `ContribuyenteEmpresaForm`
    (subclase, agrega los campos opcionales de marca/contacto).
    """

    rut = RutField(label='RUT')

    # `rut` es un campo declarado a mano, no uno generado desde el
    # modelo (ver `Meta.fields`) — sin esto, Django lo agrega al final
    # del form en vez de al principio.
    field_order = ['rut', 'razon_social', 'giro', 'direccion', 'comuna']

    class Meta:
        model = Contribuyente
        fields = ['razon_social', 'giro', 'direccion', 'comuna']
        widgets = {
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'giro': forms.TextInput(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
            'comuna': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Precarga `rut` al editar (no es un campo real del modelo)."""
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['rut'] = f'{self.instance.rut}-{self.instance.dv}'

    def clean_rut(self) -> str:
        """Separa el RUT normalizado en `rut`/`dv` y valida unicidad."""
        base, dv = self.cleaned_data['rut'].split('-')
        rut = int(base)

        contribuyentes = Contribuyente.objects.filter(rut=rut)
        if self.instance.pk:
            contribuyentes = contribuyentes.exclude(pk=self.instance.pk)
        if contribuyentes.exists():
            raise forms.ValidationError(
                'Ya existe un contribuyente con ese RUT.',
            )

        self._rut = rut
        self._dv = dv
        return str(self.cleaned_data['rut'])

    def save(self, commit: bool = True) -> Contribuyente:
        """Vuelca `rut`/`dv` (separados en `clean_rut`) a la instancia."""
        self.instance.rut = self._rut
        self.instance.dv = self._dv
        return super().save(commit=commit)


class LogoClearableFileInput(forms.ClearableFileInput):
    """`ClearableFileInput` que muestra el logo actual, no un enlace."""

    template_name = 'billing/widgets/logo_clearable_file_input.html'
    clear_checkbox_label = 'Eliminar logo'


class ContribuyenteEmpresaForm(ContribuyenteForm):
    """
    `ContribuyenteForm` + los campos opcionales de "Mi empresa".

    Solo se usa en `/settings/libredte/empresa/` — el alta
    (`ContribuyenteWizardView`) sigue usando `ContribuyenteForm` a
    secas, con solo lo esencial.
    """

    field_order = [
        'rut',
        'razon_social',
        'giro',
        'direccion',
        'comuna',
        'nombre_fantasia',
        'logo',
        'telefono',
        'correo',
        'sitio_web',
    ]

    class Meta(ContribuyenteForm.Meta):
        fields = [
            *ContribuyenteForm.Meta.fields,
            'nombre_fantasia',
            'logo',
            'telefono',
            'correo',
            'sitio_web',
        ]
        widgets = {
            **ContribuyenteForm.Meta.widgets,
            'nombre_fantasia': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'logo': LogoClearableFileInput(
                attrs={'class': 'form-control', 'accept': 'image/*'},
            ),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control'}),
            'sitio_web': forms.URLInput(attrs={'class': 'form-control'}),
        }


class CertificadoUploadForm(forms.Form):
    """
    Carga el certificado digital (.p12/.pfx) + su contraseña.

    Lo que se sube es el archivo y su contraseña, nunca el PEM/vigencia
    a mano — esos datos se **extraen** vía `certificate_manager
    .load_real_certificate()` (sin desempaquetar el PFX localmente).
    Queda como un `Certificado` del usuario (ver `certificate_manager
    .save_certificate()`) — enlazarlo a un contribuyente es un paso
    aparte (`CertificadoLinkForm`).
    """

    archivo = forms.FileField(
        label='Certificado digital',
        help_text='Archivo .p12 o .pfx del certificado digital.',
        widget=forms.ClearableFileInput(
            attrs={'class': 'form-control', 'accept': '.p12,.pfx'},
        ),
    )
    password = forms.CharField(
        label='Contraseña del certificado',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    def clean(self) -> dict[str, Any]:
        """Extrae el PEM/metadatos vía `certificate_manager`."""
        cleaned_data = super().clean() or {}
        archivo = cleaned_data.get('archivo')
        password = cleaned_data.get('password')
        if archivo is None or not password:
            return cleaned_data

        try:
            cleaned_data['certificado_cargado'] = (
                certificate_manager.load_real_certificate(
                    archivo.read(),
                    password,
                )
            )
        except ServiceError as error:
            raise forms.ValidationError(
                f'No se pudo cargar el certificado: {error}',
            ) from error

        return cleaned_data

    def __init__(self, *args: Any, usuario: Any = None, **kwargs: Any) -> None:
        """Guarda `usuario` — `save()` guarda el `Certificado` a su nombre."""
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def save(self) -> Certificado:
        """Vuelca el certificado cargado en `clean()` a un `Certificado`."""
        return certificate_manager.save_certificate(
            self.usuario,
            self.cleaned_data['certificado_cargado'],
        )


if TYPE_CHECKING:
    _CertificadoLinkFormBase = forms.ModelForm[Contribuyente]
else:
    _CertificadoLinkFormBase = forms.ModelForm


class CertificadoLinkForm(_CertificadoLinkFormBase):
    """
    Enlaza uno de los `Certificado` de `usuario` a un contribuyente.

    Solo puede elegir entre los certificados que el propio usuario
    dueño del contribuyente ya subió (ver `Contribuyente.usuario`) — no
    se sube nada acá, eso vive en el perfil (`CertificadoUploadForm`).
    """

    class Meta:
        model = Contribuyente
        fields = ['certificado']
        widgets = {
            'certificado': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args: Any, usuario: Any = None, **kwargs: Any) -> None:
        """Acota el `queryset` de `certificado` a los de `usuario`."""
        super().__init__(*args, **kwargs)
        cast(
            'forms.ModelChoiceField[Certificado]', self.fields['certificado']
        ).queryset = Certificado.objects.filter(usuario=usuario)
        self.fields['certificado'].required = False


class ActividadEconomicaAgregarForm(forms.Form):
    """
    Agrega una actividad económica ya existente al contribuyente.

    No crea ni edita `ActividadEconomica` — solo elige entre las que ya
    están cargadas en la base (ver `apps.libredte.seeders.seed()`), y
    solo entre las que el contribuyente todavía no tiene asociadas.
    """

    actividad_economica = forms.ModelChoiceField(
        queryset=ActividadEconomica.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Actividad económica',
    )

    def __init__(
        self, *args: Any, contribuyente: Any = None, **kwargs: Any
    ) -> None:
        """Acota el `queryset` a las que `contribuyente` no tiene ya."""
        self.contribuyente = contribuyente
        super().__init__(*args, **kwargs)
        cast(
            'forms.ModelChoiceField[ActividadEconomica]',
            self.fields['actividad_economica'],
        ).queryset = ActividadEconomica.objects.exclude(
            contribuyentes_actividades__contribuyente=contribuyente,
        )

    def save(self) -> ContribuyenteActividadEconomica:
        """
        Asocia la actividad elegida al contribuyente.

        La primera actividad que se asocie queda como principal
        automáticamente — un contribuyente sin ninguna actividad
        principal no puede emitir con `Acteco` (ver `biller.py`), así
        que no tiene sentido dejarlo sin marcar cuando es la única.
        """
        es_primera = not self.contribuyente.actividades.exists()
        return ContribuyenteActividadEconomica.objects.create(
            contribuyente=self.contribuyente,
            actividad_economica=self.cleaned_data['actividad_economica'],
            es_principal=es_primera,
        )


if TYPE_CHECKING:
    _SucursalFormBase = forms.ModelForm[Sucursal]
else:
    _SucursalFormBase = forms.ModelForm


class SucursalForm(_SucursalFormBase):
    """Datos de una sucursal."""

    class Meta:
        model = Sucursal
        fields = [
            'nombre',
            'codigo_sii',
            'es_matriz',
            'direccion',
            'comuna',
            'ciudad',
            'telefono',
            'correo',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_sii': forms.NumberInput(attrs={'class': 'form-control'}),
            'es_matriz': forms.CheckboxInput(
                attrs={'class': 'form-check-input'},
            ),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
            'comuna': forms.Select(attrs={'class': 'form-select'}),
            'ciudad': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control'}),
        }
