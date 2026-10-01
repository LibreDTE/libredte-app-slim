"""Formularios de `billing`."""

from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from django import forms
from django.forms.formsets import DELETION_FIELD_NAME

from apps.libredte.forms import RutField
from apps.libredte.models import Comuna, Contribuyente, Pais, Sucursal
from apps.libredte.services.exceptions import ServiceError

from . import enums
from .models import (
    AduanaMoneda,
    Caf,
    CafFolio,
    DteEmitido,
    DteRecibido,
    FormaPago,
    ImpuestoAdicionalRetencion,
    Item,
    ItemCategoria,
    MedioPago,
    Receptor,
    TipoDte,
    Traslado,
)
from .services import biller, caf_manager, document_receiver

if TYPE_CHECKING:
    from django.contrib.auth.models import User

if TYPE_CHECKING:
    _ContribuyenteAmbienteFormBase = forms.ModelForm[Contribuyente]
else:
    _ContribuyenteAmbienteFormBase = forms.ModelForm


class ContribuyenteAmbienteForm(_ContribuyenteAmbienteFormBase):
    """
    Resolución SII que define el ambiente (card "Ambiente").

    Sobre `Contribuyente` (genérico, vive en `apps.libredte`) — pero la
    resolución de autorización DTE es puramente de facturación
    electrónica (ni contabilidad ni RR.HH. la necesitan), así que este
    formulario/vista/URL vive acá, no en `libredte` (mismo criterio que
    `TipoDte`: un modelo compartido no obliga a que todo lo que lo
    edite sea genérico).
    """

    field_order = [
        'autorizacion_dte_resolucion_fecha',
        'autorizacion_dte_resolucion_numero',
    ]

    class Meta:
        model = Contribuyente
        fields = [
            'autorizacion_dte_resolucion_fecha',
            'autorizacion_dte_resolucion_numero',
        ]
        widgets = {
            # `format='%Y-%m-%d'` a propósito, no el de la localización
            # (`d/m/Y`, el que usaría por defecto): un `<input
            # type="date">` exige ese formato ISO para reconocer el
            # valor — con el localizado, el navegador lo descarta en
            # silencio y el campo se ve vacío aunque el dato sí esté
            # guardado.
            'autorizacion_dte_resolucion_fecha': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'},
                format='%Y-%m-%d',
            ),
            'autorizacion_dte_resolucion_numero': forms.NumberInput(
                attrs={'class': 'form-control'},
            ),
        }


if TYPE_CHECKING:
    _ReceptorFormBase = forms.ModelForm[Receptor]
else:
    _ReceptorFormBase = forms.ModelForm


class ReceptorForm(_ReceptorFormBase):
    """Datos de un receptor — reusa `RutField`, igual que `Contribuyente`."""

    rut = RutField(label='RUT')
    comuna = forms.ModelChoiceField(
        queryset=Comuna.objects.all(),
        required=False,
        empty_label='(Sin especificar)',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    field_order = [
        'rut',
        'codigo_interno',
        'razon_social',
        'giro',
        'telefono',
        'correo',
        'direccion',
        'comuna',
        'ciudad',
        'pais',
        'numero_identificacion',
    ]

    class Meta:
        model = Receptor
        fields = [
            'codigo_interno',
            'razon_social',
            'giro',
            'telefono',
            'correo',
            'direccion',
            'comuna',
            'ciudad',
            'pais',
            'numero_identificacion',
        ]
        widgets = {
            'codigo_interno': forms.TextInput(attrs={'class': 'form-control'}),
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'giro': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
            'ciudad': forms.TextInput(attrs={'class': 'form-control'}),
            'pais': forms.Select(attrs={'class': 'form-select'}),
            'numero_identificacion': forms.TextInput(
                attrs={'class': 'form-control'},
            ),
        }
        labels = {
            'codigo_interno': 'Código interno',
            'razon_social': 'Razón social',
            'direccion': 'Dirección',
            'pais': 'País',
            'numero_identificacion': 'N.° de identificación',
        }
        help_texts = {
            'numero_identificacion': (
                'Documento de identidad en su país de origen — solo se '
                'usa al emitir una exportación (NumId del SII).'
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Precarga `rut` al editar, y `pais` en Chile para uno nuevo.

        `rut` no es un campo real del modelo. `pais` en Chile es solo
        para un receptor nuevo — la gran mayoría lo es
        (`Receptor.save()` lo dejaría en Chile de todas formas si se
        deja vacío, esto solo evita que la persona tenga que buscarlo).
        """
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['rut'] = f'{self.instance.rut}-{self.instance.dv}'
        else:
            self.initial['pais'] = (
                Pais.objects.filter(
                    codigo=Pais.CHILE,
                )
                .values_list('pk', flat=True)
                .first()
            )

    def clean_rut(self) -> str:
        """
        Separa el RUT normalizado en `rut`/`dv`.

        A diferencia de `Contribuyente`, `Receptor.rut` no es único — un
        mismo RUT puede repetirse entre receptores (ver docstring del
        modelo) — no hay nada que validar acá.
        """
        base, dv = self.cleaned_data['rut'].split('-')
        self._rut = int(base)
        self._dv = dv
        return str(self.cleaned_data['rut'])

    def save(self, commit: bool = True) -> Receptor:
        """Vuelca `rut`/`dv` (separados en `clean_rut`) a la instancia."""
        self.instance.rut = self._rut
        self.instance.dv = self._dv
        return super().save(commit=commit)


if TYPE_CHECKING:
    _ItemCategoriaFormBase = forms.ModelForm[ItemCategoria]
else:
    _ItemCategoriaFormBase = forms.ModelForm


class ItemCategoriaForm(_ItemCategoriaFormBase):
    """Datos de una categoría de ítems."""

    class Meta:
        model = ItemCategoria
        fields = ['nombre', 'activa']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


if TYPE_CHECKING:
    _ItemCatalogoFormBase = forms.ModelForm[Item]
else:
    _ItemCatalogoFormBase = forms.ModelForm


class ItemCatalogoForm(_ItemCatalogoFormBase):
    """
    Datos de un ítem del catálogo de facturación.

    Nombre distinto al `ItemForm` de más abajo (una fila del `Detalle`
    en `/billing/emitir`) — son formularios sin relación entre sí.
    """

    class Meta:
        model = Item
        fields = [
            'codigo_tipo',
            'codigo',
            'nombre',
            'descripcion',
            'categoria',
            'unidad',
            'precio',
            'bruto',
            'indicador_exencion',
            'descuento',
            'descuento_tipo',
            'impuesto_adicional',
            'activo',
        ]
        widgets = {
            'codigo_tipo': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 2},
            ),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'unidad': forms.TextInput(attrs={'class': 'form-control'}),
            'precio': forms.NumberInput(attrs={'class': 'form-control'}),
            'bruto': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'indicador_exencion': forms.Select(
                attrs={'class': 'form-select'},
            ),
            'descuento': forms.NumberInput(attrs={'class': 'form-control'}),
            'descuento_tipo': forms.Select(attrs={'class': 'form-select'}),
            'impuesto_adicional': forms.Select(
                attrs={'class': 'form-select'},
            ),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(
        self, *args: Any, contribuyente: Any = None, **kwargs: Any
    ) -> None:
        """Acota `categoria` a las del contribuyente activo."""
        super().__init__(*args, **kwargs)
        cast(
            'forms.ModelChoiceField[ItemCategoria]', self.fields['categoria']
        ).queryset = ItemCategoria.objects.filter(contribuyente=contribuyente)


if TYPE_CHECKING:
    _CafFolioFormBase = forms.ModelForm[CafFolio]
else:
    _CafFolioFormBase = forms.ModelForm


class CafFolioForm(_CafFolioFormBase):
    """
    Modificar el contador de folios (siguiente/alerta) de un tipo de DTE.

    `disponibles` no es editable acá a propósito: se deriva de los CAF
    cargados, no de un valor que el usuario escriba a mano.
    """

    class Meta:
        model = CafFolio
        fields = ['siguiente', 'alerta']
        widgets = {
            'siguiente': forms.NumberInput(attrs={'class': 'form-control'}),
            'alerta': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class CafUploadForm(forms.Form):
    """
    Carga de un CAF ya descargado desde el sitio del SII.

    `caf_manager.validate_caf()` no solo extrae `tipo_dte`/`desde`/
    `hasta` de la estructura del XML, sino que valida la firma real
    contra la API — algo que un parseo local con `xml.etree` no puede
    hacer.
    """

    archivo = forms.FileField(
        label='Archivo XML',
        help_text='El CAF descargado desde el sitio web del SII.',
        widget=forms.ClearableFileInput(
            attrs={'class': 'form-control', 'accept': '.xml,text/xml'},
        ),
    )

    def clean_archivo(self) -> Any:
        """Valida el CAF contra la API y resuelve su tipo de DTE."""
        archivo = self.cleaned_data['archivo']
        xml_base64 = base64.b64encode(archivo.read()).decode()

        try:
            caf = caf_manager.validate_caf(xml_base64, self.contribuyente)
        except ServiceError as error:
            raise forms.ValidationError(
                f'El archivo no es un CAF válido: {error}',
            ) from error

        try:
            tipo_dte = TipoDte.objects.get(codigo=caf.tipo_documento)
        except TipoDte.DoesNotExist as error:
            raise forms.ValidationError(
                f'El tipo de documento {caf.tipo_documento} no está '
                f'registrado en el sistema.',
            ) from error

        self.cleaned_data['tipo_dte'] = tipo_dte
        self.cleaned_data['caf'] = caf
        return archivo

    def clean(self) -> dict[str, Any]:
        """Rechaza un CAF ya cargado (mismo contribuyente/tipo/desde)."""
        cleaned_data = super().clean() or {}
        tipo_dte = cleaned_data.get('tipo_dte')
        caf = cleaned_data.get('caf')
        if tipo_dte is None or caf is None:
            return cleaned_data
        if Caf.objects.filter(
            contribuyente=self.contribuyente,
            tipo_dte=tipo_dte,
            desde=caf.folio_desde,
        ).exists():
            raise forms.ValidationError(
                'Ya existe un CAF cargado con ese rango de folios.',
            )
        return cleaned_data

    def __init__(
        self, *args: Any, contribuyente: Any = None, **kwargs: Any
    ) -> None:
        """Guarda `contribuyente` — lo necesita `clean()` para validar."""
        self.contribuyente = contribuyente
        super().__init__(*args, **kwargs)

    def save(self) -> Caf:
        """Registra el `Caf` validado en `clean_archivo()`."""
        return caf_manager.register_caf(
            self.contribuyente,
            self.cleaned_data['tipo_dte'],
            self.cleaned_data['caf'],
        )


class CafSolicitarForm(forms.Form):
    """
    Solicita folios NUEVOS al SII para un tipo de documento.

    A diferencia de `CafUploadForm`, esto no carga un archivo ya
    descargado: pide folios reales al SII (aunque el ambiente activo
    sea certificación, no es una simulación — ver
    `SiiBackend.sii_caf_solicitar()`).
    """

    tipo_dte = forms.ModelChoiceField(
        queryset=TipoDte.objects.all(),
        label='Tipo de documento',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    cantidad = forms.IntegerField(
        label='Cantidad de folios',
        min_value=1,
        max_value=500,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )

    def __init__(
        self, *args: Any, tipo_dte: TipoDte | None = None, **kwargs: Any
    ) -> None:
        """Si viene `tipo_dte` (desde el detalle de un tipo), lo fija."""
        super().__init__(*args, **kwargs)
        if tipo_dte is not None:
            self.fields['tipo_dte'].initial = tipo_dte
            self.fields['tipo_dte'].disabled = True


if TYPE_CHECKING:
    _CafChoiceFieldBase = forms.ModelChoiceField[Caf]
else:
    _CafChoiceFieldBase = forms.ModelChoiceField


class CafChoiceField(_CafChoiceFieldBase):
    """`caf` de `CafAnularForm` — solo el rango, sin tipo/contribuyente."""

    def label_from_instance(self, obj: Caf) -> str:
        cantidad = obj.hasta - obj.desde + 1
        return f'{obj.desde} — {obj.hasta} ({cantidad} folios)'


class CafAnularForm(forms.Form):
    """
    Anula un rango de folios de un CAF cargado — irreversible en el SII.

    El CAF se elige de una lista (no se listan aparte con potencialmente
    cientos de filas) y el rango a anular debe caer dentro de ese CAF —
    así no se puede anular por error un rango de un CAF que ni siquiera
    está cargado en Slim.
    """

    caf = CafChoiceField(
        queryset=Caf.objects.none(),
        label='CAF',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    folio_inicial = forms.IntegerField(
        label='Folio inicial',
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    folio_final = forms.IntegerField(
        label='Folio final',
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )

    def __init__(
        self,
        *args: Any,
        contribuyente: Any = None,
        tipo_dte: TipoDte,
        **kwargs: Any,
    ) -> None:
        """Acota `caf` a los CAF de `contribuyente`/`tipo_dte`."""
        super().__init__(*args, **kwargs)
        cast(
            'forms.ModelChoiceField[Caf]', self.fields['caf']
        ).queryset = Caf.objects.filter(
            contribuyente=contribuyente, tipo_dte=tipo_dte
        ).order_by('desde')

    def clean(self) -> dict[str, Any]:
        """El rango debe caer dentro del CAF elegido, e ir de menor a mayor."""
        cleaned_data = super().clean() or {}
        caf = cleaned_data.get('caf')
        inicial = cleaned_data.get('folio_inicial')
        final = cleaned_data.get('folio_final')
        if inicial is not None and final is not None and final < inicial:
            raise forms.ValidationError(
                'El folio final no puede ser menor que el inicial.',
            )
        elif (
            caf is not None
            and inicial is not None
            and final is not None
            and (inicial < caf.desde or final > caf.hasta)
        ):
            raise forms.ValidationError(
                f'El rango debe estar dentro de los folios del CAF '
                f'seleccionado ({caf.desde} — {caf.hasta}).',
            )
        return cleaned_data


class CafReobtenerCargarForm(forms.Form):
    """
    Datos de un CAF a reobtener, ya listados por `sii_caf_solicitudes`.

    Campos ocultos: no los escribe la persona, vienen de una fila que
    "Reobtener CAF" ya mostró — este formulario solo los valida antes
    de pedir el XML (`sii_caf_xml`).
    """

    folio_inicial = forms.IntegerField(min_value=1)
    folio_final = forms.IntegerField(min_value=1)
    fecha_autorizacion = forms.DateField()


class RecibidoSobreUploadForm(forms.Form):
    """
    Carga un sobre `EnvioDTE` recibido de un proveedor (archivo XML).

    Se sube el archivo, nunca se pega el XML a mano: el XML declara
    `encoding="ISO-8859-1"` en su prolog, y pegarlo en un textarea puede
    reinterpretar esos bytes y romper la firma electrónica.
    """

    archivo = forms.FileField(
        label='Archivo XML',
        help_text='El sobre EnvioDTE recibido del proveedor.',
        widget=forms.ClearableFileInput(
            attrs={'class': 'form-control', 'accept': '.xml,text/xml'},
        ),
    )

    def __init__(
        self,
        *args: Any,
        contribuyente: Any = None,
        usuario: Any = None,
        **kwargs: Any,
    ) -> None:
        """Guarda `contribuyente`/`usuario` — los necesita `save()`."""
        self.contribuyente = contribuyente
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def save(self) -> list[DteRecibido]:
        """Procesa el sobre y persiste un `DteRecibido` por documento."""
        archivo = self.cleaned_data['archivo']
        xml_base64 = base64.b64encode(archivo.read()).decode()
        return document_receiver.load_xml(
            self.contribuyente,
            xml_base64,
            self.usuario,
        )


class EmitidoXmlUploadForm(forms.Form):
    """
    Registra un DTE ya emitido por este contribuyente (archivo XML).

    Se sube el archivo, nunca se pega el XML a mano (mismo motivo que
    `RecibidoSobreUploadForm`). A diferencia de ese, acá el XML es un
    documento suelto (no un sobre) — se subió por otro medio, o se
    perdió su registro en Slim y se recupera desde un respaldo.
    """

    archivo = forms.FileField(
        label='Archivo XML',
        help_text='El DTE ya timbrado y firmado, emitido por este '
        'contribuyente.',
        widget=forms.ClearableFileInput(
            attrs={'class': 'form-control', 'accept': '.xml,text/xml'},
        ),
    )

    def __init__(
        self,
        *args: Any,
        contribuyente: Any = None,
        usuario: Any = None,
        **kwargs: Any,
    ) -> None:
        """Guarda `contribuyente`/`usuario` — los necesita `save()`."""
        self.contribuyente = contribuyente
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def save(self) -> DteEmitido:
        """Procesa el XML y persiste el `DteEmitido`."""
        archivo = self.cleaned_data['archivo']
        xml_base64 = base64.b64encode(archivo.read()).decode()
        return biller.load_xml(self.contribuyente, xml_base64, self.usuario)


class EmisionMasivaForm(forms.Form):
    """
    Carga de la planilla de emisión masiva (ver `services/bulk_biller.py`).

    Sin validación de la planilla acá: la biblioteca la parsea en la vista
    (`bulk_biller.parse()`) y su error, si hay, se muestra en este
    formulario. Este formulario solo se asegura de que el usuario tenga un
    correo al que avisarle.
    """

    MODO_VER = 'ver'
    MODO_BORRADOR = 'borrador'
    MODO_REAL = 'real'

    archivo = forms.FileField(
        label='Planilla',
        help_text='Planilla CSV o XLSX con los documentos a emitir.',
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'form-control',
                'accept': (
                    '.csv,.xlsx,text/csv,application/vnd.openxmlformats-'
                    'officedocument.spreadsheetml.sheet'
                ),
            },
        ),
    )
    modo = forms.ChoiceField(
        label='Modo de ejecución',
        choices=[
            (
                MODO_VER,
                'Solo ver los documentos (descargar el YAML, sin emitir nada)',
            ),
            (MODO_BORRADOR, 'Borradores (dejar los documentos como borrador)'),
            (
                MODO_REAL,
                'DTE real (emitir el DTE real, consume folios del CAF)',
            ),
        ],
        initial=MODO_BORRADOR,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    pdf = forms.ChoiceField(
        label='¿Generar PDF?',
        choices=[
            ('', 'No generar PDF'),
            (
                '1',
                'Sí, generar todos los PDF (el correo trae el enlace '
                'de descarga)',
            ),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args: Any, usuario: User, **kwargs: Any) -> None:
        """
        Guarda `usuario`: lo necesita `clean()` para validar su correo.

        :param usuario: Quien sube la planilla.
        :type usuario: User
        """
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any] | None:
        """
        Rechaza la planilla si el usuario no tiene correo.

        El resultado de la emisión masiva solo llega por correo: sin uno,
        la emisión ocurriría igual pero nadie se enteraría de cómo
        terminó. Con "solo ver los documentos" no se emite nada ni se envía
        ningún correo, así que no hace falta.

        :return: Los datos validados.
        :rtype: dict[str, Any] | None
        :raises ValidationError: Si el usuario no tiene correo.
        """
        if (
            not self.usuario.email
            and self.cleaned_data.get('modo') != self.MODO_VER
        ):
            raise forms.ValidationError(
                'El resultado de la emisión masiva llega por correo y su '
                'perfil no tiene uno. Agréguelo en su perfil antes de '
                'subir la planilla.',
            )
        return super().clean()


class TipoDteSelect(forms.Select):
    """
    `<select>` de `tipo_dte` con el código SII de cada opción en `data-codigo`.

    Lo usa el JS de `emitir.html` (`actualizarSeccionesCondicionales()`)
    para mostrar/ocultar secciones según el tipo de documento elegido
    (`data-solo-tipo`). `value` ya trae el código como
    `ModelChoiceIteratorValue.instance` (Django ≥ 3.1) — sin esto,
    `value` es el `pk` del `TipoDte`, no el código SII, así que no
    sirve para comparar contra `data-solo-tipo`.
    """

    def create_option(
        self,
        name: str,
        value: Any,
        label: int | str,
        selected: bool,
        index: int,
        subindex: int | None = None,
        attrs: Any = None,
    ) -> dict[str, Any]:
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex,
            attrs,
        )
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-codigo'] = instance.codigo
        return option


if TYPE_CHECKING:
    _TipoDteChoiceFieldBase = forms.ModelChoiceField[TipoDte]
else:
    # `ModelChoiceField` tampoco es `Generic` en tiempo de ejecución
    # (ver alias de `ModelForm` más arriba, mismo motivo).
    _TipoDteChoiceFieldBase = forms.ModelChoiceField


class TipoDteChoiceField(_TipoDteChoiceFieldBase):
    """`tipo_dte` de `DocumentoForm` — solo la glosa, sin el código."""

    def label_from_instance(self, obj: TipoDte) -> str:
        return obj.glosa


class DocumentoForm(forms.Form):
    """
    Campos "Documento"/"Receptor" de `/billing/emitir`.

    Sin repetición de filas — Ítems/Referencias/Pago programado son
    los `FormSet` de más abajo. Los nombres de campo son los mismos
    que espera `form.estandar` (la API) — no hay traducción entre esto y
    `views.py::_form_data_from_forms()`. Deliberadamente
    permisivo: casi todo `required=False`, el mismo criterio que ya
    tenía el HTML plano que reemplaza (ahí también eran opcionales,
    solo el HTML5 `required` los frenaba en el navegador). La
    validación de negocio real (qué exige cada tipo de documento, etc.)
    sigue siendo trabajo exclusivo de `form.estandar` en la API — este
    formulario no reinterpreta ni valida más que eso; solo existe para
    que el formulario quede "sticky" si la API rechaza el envío.
    """

    tipo_dte = TipoDteChoiceField(
        queryset=TipoDte.objects.all(),
        widget=TipoDteSelect(attrs={'class': 'form-select'}),
    )
    FchEmis = forms.DateField(
        # `format='%Y-%m-%d'` a propósito, no el de la localización —
        # mismo motivo que `ContribuyenteAmbienteForm`: un `<input
        # type="date">` exige ISO para reconocer el valor inicial
        # (`initial`, ver `views.py::emitir()`), si no el navegador lo
        # descarta en silencio y el campo se ve vacío.
        widget=forms.DateInput(
            attrs={'class': 'form-control', 'type': 'date'},
            format='%Y-%m-%d',
        ),
    )
    CdgSIISucur = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    RUTSolicita = RutField(required=False)

    FmaPago = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    FchVenc = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )
    IndServicio = forms.ChoiceField(
        choices=[('', '(No aplica)'), *enums.IndicadorServicio.choices],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    CdgVendedor = forms.CharField(
        max_length=60,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    TermPagoGlosa = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    PeriodoDesde = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )
    PeriodoHasta = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )

    MedioPago = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    BcoPago = forms.CharField(
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    TpoCtaPago = forms.ChoiceField(
        choices=[('', '(Sin cuenta bancaria)'), *enums.TipoCuentaPago.choices],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    NumCtaPago = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    TpoTranVenta = forms.ChoiceField(
        choices=[
            ('', '(Sin especificar)'),
            *enums.TipoTransaccionVenta.choices,
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    TpoTranCompra = forms.ChoiceField(
        choices=[
            ('', '(Sin especificar)'),
            *enums.TipoTransaccionCompra.choices,
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    IndTraslado = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    Patente = forms.CharField(
        max_length=8,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    PatenteCarro = forms.CharField(
        max_length=8,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    RUTTrans = RutField(required=False)
    RUTChofer = RutField(required=False)
    NombreChofer = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    DirDest = forms.CharField(
        max_length=70,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    CmnaDest = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    FchSalida = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )
    HraSalida = forms.CharField(
        max_length=8,
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'form-control', 'placeholder': 'Ejemplo: 13:13'},
        ),
    )
    FchLlegada = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )

    TpoMoneda = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    TpoCambio = forms.DecimalField(
        required=False,
        # Un tipo de cambio cero o negativo no existe — misma guarda de
        # forma que `ItemForm.QtyItem`, con el `step` del widget como
        # piso para no inventar uno propio.
        min_value=Decimal('0.0001'),
        widget=forms.NumberInput(
            attrs={'class': 'form-control', 'step': '0.0001'},
        ),
    )

    RUTRecep = RutField(
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                # Sugerencias del catálogo de receptores del
                # contribuyente activo — poblada por JS en
                # `emitir.html`, igual que con los ítems.
                'list': 'datalist-receptores-rut',
                'autocomplete': 'off',
            },
        ),
    )
    RznSocRecep = forms.CharField(
        max_length=100,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'list': 'datalist-receptores-razon-social',
                'autocomplete': 'off',
            },
        ),
    )
    GiroRecep = forms.CharField(
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    CdgIntRecep = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'list': 'datalist-receptores-codigo-interno',
                'autocomplete': 'off',
            },
        ),
    )
    Contacto = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    CorreoRecep = forms.EmailField(
        max_length=80,
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
    DirRecep = forms.CharField(
        max_length=70,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    CmnaRecep = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    CiudadRecep = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    Nacionalidad = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    NumId = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    ValorDR_global = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(
            attrs={'class': 'form-control', 'step': '0.01'},
        ),
    )
    TpoValor_global = forms.ChoiceField(
        choices=enums.TipoValor.choices,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(
        self, *args: Any, contribuyente: Any = None, **kwargs: Any
    ) -> None:
        """
        Arma los `choices` que dependen de catálogos de la base.

        No pueden ir en la definición de la clase (se evaluarían al
        importar el módulo, sin base de datos todavía disponible) — se
        arman acá, una vez por instancia. El valor real de cada opción
        es el mismo que ya usaba el HTML plano (`codigo`/`glosa`, no el
        `pk`), para no cambiarle el shape a los datos que recibe
        `form.estandar`.
        """
        super().__init__(*args, **kwargs)
        cast(forms.ChoiceField, self.fields['CdgSIISucur']).choices = [
            ('', '(Casa matriz)'),
            *(
                (
                    str(s.codigo_sii) if s.codigo_sii is not None else '',
                    s.nombre or s.direccion,
                )
                for s in Sucursal.objects.filter(contribuyente=contribuyente)
            ),
        ]
        cast(forms.ChoiceField, self.fields['FmaPago']).choices = [
            ('', '(Sin especificar)'),
            *((str(f.codigo), f.glosa) for f in FormaPago.objects.all()),
        ]
        cast(forms.ChoiceField, self.fields['MedioPago']).choices = [
            ('', '(Cualquier medio de pago)'),
            *((m.codigo, m.glosa) for m in MedioPago.objects.all()),
        ]
        cast(forms.ChoiceField, self.fields['IndTraslado']).choices = [
            (str(t.codigo), t.glosa) for t in Traslado.objects.all()
        ]
        comuna_choices = [
            ('', '(Sin especificar)'),
            *((c.glosa, c.glosa) for c in Comuna.objects.all()),
        ]
        cast(
            forms.ChoiceField, self.fields['CmnaDest']
        ).choices = comuna_choices
        cast(
            forms.ChoiceField, self.fields['CmnaRecep']
        ).choices = comuna_choices
        cast(forms.ChoiceField, self.fields['TpoMoneda']).choices = [
            ('', '(Sin especificar)'),
            *(
                (
                    m.glosa,
                    f'{m.glosa} ({m.codigo_iso})' if m.codigo_iso else m.glosa,
                )
                for m in AduanaMoneda.objects.all()
            ),
        ]
        cast(forms.ChoiceField, self.fields['Nacionalidad']).choices = [
            ('', '(Sin especificar)'),
            *((str(p.codigo), p.glosa) for p in Pais.objects.all()),
        ]
        # La gran mayoría de los receptores son chilenos — se preselecciona
        # para no obligar a elegirlo a mano en el caso común, igual que
        # `Receptor.save()` deja `pais` en Chile si no se especifica otro.
        self.fields['Nacionalidad'].initial = str(Pais.CHILE)


class ItemForm(forms.Form):
    """Una fila de `Detalle` — ver `EstandarParserStrategy::addDetails()`."""

    TpoCodigo = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'INT1',
            },
        ),
    )
    VlrCodigo = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control form-control-sm',
                # Sugerencias del catálogo del contribuyente activo
                # (`datalist-items`, poblado por JS en `emitir.html`) —
                # `autocomplete="off"` para que no compita con el
                # autocompletado nativo del navegador (historial de lo
                # tipeado antes), igual que legacy.
                'list': 'datalist-items',
                'autocomplete': 'off',
            },
        ),
    )
    NmbItem = forms.CharField(
        max_length=80,
        widget=forms.TextInput(
            attrs={'class': 'form-control form-control-sm'},
        ),
    )
    DscItem = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'form-control form-control-sm'},
        ),
    )
    IndExe = forms.ChoiceField(
        choices=[('0', 'Afecto'), *enums.IndicadorExencion.choices],
        initial='0',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    QtyItem = forms.DecimalField(
        initial=1,
        required=False,
        # Guarda de forma, no una regla del SII: una cantidad cero o
        # negativa no es un caso de negocio que la API tenga que
        # resolver, es un dato mal tipeado. El piso es el mismo `step`
        # del widget — el navegador lo hereda como `min` y lo frena
        # antes de enviar.
        min_value=Decimal('0.0001'),
        widget=forms.NumberInput(
            attrs={'class': 'form-control form-control-sm', 'step': '0.0001'},
        ),
    )
    UnmdItem = forms.CharField(
        max_length=4,
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'form-control form-control-sm'},
        ),
    )
    PrcItem = forms.IntegerField(
        # Un precio negativo no existe en un DTE: un descuento va en
        # `ValorDR`/`TpoValor`, no en el precio unitario. Misma guarda
        # de forma que `QtyItem` — el navegador la hereda como `min`.
        min_value=0,
        widget=forms.NumberInput(
            attrs={'class': 'form-control form-control-sm', 'step': '1'},
        ),
    )
    CodImpAdic = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    ValorDR = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(
            attrs={'class': 'form-control form-control-sm', 'step': '0.01'},
        ),
    )
    TpoValor = forms.ChoiceField(
        choices=[(valor, valor) for valor, _ in enums.TipoValor.choices],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """`CodImpAdic` depende del catálogo — ver `DocumentoForm.__init__`."""
        super().__init__(*args, **kwargs)
        cast(forms.ChoiceField, self.fields['CodImpAdic']).choices = [
            ('', '(Ninguno)'),
            *(
                (str(i.codigo), f'{i.glosa} ({i.tasa}%)')
                for i in ImpuestoAdicionalRetencion.objects.all()
            ),
        ]


class ReferenciaForm(forms.Form):
    """Una fila de `Referencia` — ver `addReferences()` en el core."""

    TpoDocRef = forms.CharField(
        max_length=3,
        widget=forms.TextInput(
            attrs={'class': 'form-control form-control-sm'},
        ),
    )
    FolioRef = forms.CharField(
        max_length=18,
        widget=forms.TextInput(
            attrs={'class': 'form-control form-control-sm'},
        ),
    )
    FchRef = forms.DateField(
        widget=forms.DateInput(
            attrs={'class': 'form-control form-control-sm', 'type': 'date'},
        ),
    )
    CodRef = forms.ChoiceField(
        choices=[('', '(Sin especificar)'), *enums.CodigoReferencia.choices],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    RazonRef = forms.CharField(
        max_length=90,
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'form-control form-control-sm'},
        ),
    )


class PagoForm(forms.Form):
    """Una cuota de `MntPagos` (pago programado a crédito)."""

    FchPago = forms.DateField(
        widget=forms.DateInput(
            attrs={'class': 'form-control form-control-sm', 'type': 'date'},
        ),
    )
    MntPago = forms.IntegerField(
        # Misma guarda de forma que `ItemForm.PrcItem`: una cuota por un
        # monto negativo es un dato mal tipeado, no un caso de negocio.
        min_value=0,
        widget=forms.NumberInput(
            attrs={'class': 'form-control form-control-sm', 'step': '1'},
        ),
    )
    GlosaPagos = forms.CharField(
        max_length=40,
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'form-control form-control-sm'},
        ),
    )


# `extra=1` en `ItemFormSet`: siempre arranca con una fila para llenar
# (mismo criterio que el HTML plano de antes, "al menos un ítem para
# partir") — las otras dos parten vacías, el usuario agrega filas con
# el botón "Agregar" si las necesita.
#
# `can_delete=True` en las tres: "Quitar" (JS, ver `emitir.html`) tilda
# el campo `DELETE` de la fila y la oculta, no la saca del DOM — sacar
# los `<input>` del DOM entero deja esa fila con puros campos ausentes,
# y como `QtyItem`/`IndExe` (`ItemForm`) sí tienen un `initial` propio
# (`1`/`'0'`), Django detecta esa ausencia como "cambió" respecto a su
# valor por defecto (`Field.has_changed()`) y dejaría de tratarla como
# vacía (`empty_permitted`) — validaría igual una fila que el usuario
# ya quitó, y fallaría por sus campos requeridos faltantes. Con
# `can_delete=True`, `BaseFormSet.is_valid()` nunca valida los otros
# campos de una fila con `DELETE=True`, sea cual sea su estado.
if TYPE_CHECKING:
    _ItemFormSetBase = forms.BaseFormSet[ItemForm]
else:
    _ItemFormSetBase = forms.BaseFormSet


class BaseItemFormSet(_ItemFormSetBase):
    """`ItemFormSet` con la exigencia de que quede al menos un ítem."""

    def clean(self) -> None:
        """
        Rechaza un documento sin ninguna fila de detalle.

        No se usa `min_num=1`/`validate_min=True`: eso ata la exigencia
        a la fila de índice 0 (deja de ser `empty_permitted`), y una
        fila 0 vacía con la fila 1 llena es un estado legítimo — es
        justo lo que queda después de quitar la primera. Se cuentan las
        filas realmente vivas: las que el usuario tocó y no marcó como
        borradas. Lo segundo se lee del propio `cleaned_data` en vez de
        `BaseFormSet._should_delete_form()` (mismo cuerpo, pero el
        método es privado y `django-stubs` no lo declara).
        """
        super().clean()
        vivas = [
            form
            for form in self.forms
            if form.has_changed()
            and not (
                self.can_delete
                and form.cleaned_data.get(DELETION_FIELD_NAME, False)
            )
        ]
        if not vivas:
            raise forms.ValidationError(
                'Agrega al menos un ítem al documento.',
            )


ItemFormSet = forms.formset_factory(
    ItemForm,
    formset=BaseItemFormSet,
    extra=1,
    can_delete=True,
)
ReferenciaFormSet = forms.formset_factory(
    ReferenciaForm,
    extra=0,
    can_delete=True,
)
PagoFormSet = forms.formset_factory(PagoForm, extra=0, can_delete=True)


class RcvPeriodoForm(forms.Form):
    """
    Período para ir directo al RCV de ventas del SII.

    Consulta en línea al SII, no busca en datos locales — por eso no
    valida que el período tenga documentos en Slim.
    """

    periodo = forms.DateField(
        label='Período',
        input_formats=['%Y-%m'],
        widget=forms.DateInput(
            attrs={'type': 'month', 'class': 'form-control'},
            format='%Y-%m',
        ),
    )

    def periodo_int(self) -> int:
        fecha = cast('date', self.cleaned_data['periodo'])
        return fecha.year * 100 + fecha.month


class RcvCompraPeriodoForm(RcvPeriodoForm):
    """Período + estado para ir directo al RCV de compras del SII."""

    ESTADO_CHOICES = (
        ('REGISTRO', 'Registrados'),
        ('PENDIENTE', 'Pendientes'),
        ('NO_INCLUIR', 'No incluídos'),
        ('RECLAMADO', 'Reclamados'),
    )

    estado = forms.ChoiceField(
        label='Estado',
        choices=ESTADO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
