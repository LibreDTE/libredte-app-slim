"""Modelos del dominio de facturación electrónica (DTE)."""

from __future__ import annotations

import base64
import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from libredte_lib_sdk.billing.enums import SiiEnvironment

from apps.core.fields import DvField
from apps.libredte.models import (
    Comuna,
    Contribuyente,
    Pais,
)


class XmlBase64Mixin:
    """
    Mixin para un modelo cuyo dato principal es un XML del SII, en base64.

    El campo real (`xml_base64`) guarda ese base64 tal cual lo entrega la
    API — nunca decodificado. El XML del SII declara
    `encoding="ISO-8859-1"` en su prolog, no UTF-8; guardar el base64 en
    vez del texto ya decodificado evita cualquier reinterpretación de
    charset entre que se guarda y se usa (base64 es puro ASCII, no hay
    ninguna interpretación de encoding posible ahí). `xml_bytes`/`xml`
    decodifican bajo demanda, recién cuando hace falta texto o bytes de
    verdad (mostrar en pantalla, servir un archivo) — el dato guardado
    nunca pasa por ahí.
    """

    # Sin valor ni `models.Field` acá — cada modelo concreto lo declara
    # como campo real (`Caf`/`DteEmitido`/`DteRecibido`/`Borrador`).
    # Solo le avisa a mypy que este mixin espera ese atributo.
    xml_base64: str

    @property
    def xml_bytes(self) -> bytes:
        """XML decodificado desde base64 — los bytes reales, tal cual."""
        return base64.b64decode(self.xml_base64)

    @property
    def xml(self) -> str:
        """XML como texto (ISO-8859-1, la codificación que usa el SII)."""
        return self.xml_bytes.decode('iso-8859-1')


class Traslado(models.Model):
    """Indicador de traslado de una guía de despacho, según el SII."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'indicador de traslado'
        verbose_name_plural = 'indicadores de traslado'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class FormaPago(models.Model):
    """Forma de pago de un documento (contado/crédito/etc), según el SII."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=50)

    class Meta:
        verbose_name = 'forma de pago'
        verbose_name_plural = 'formas de pago'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class AduanaFormaPago(models.Model):
    """
    Forma de pago de un documento de exportación (`FmaPagExp`), según Aduana.

    Catálogo distinto de `FormaPago` — la nomenclatura de Aduana no
    coincide con la del SII (ver `TagXml` del repositorio del SDK, que
    mapea `FmaPagExp` a esta entidad y no a `FormaPago`).
    """

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=50)

    class Meta:
        verbose_name = 'forma de pago de exportación'
        verbose_name_plural = 'formas de pago de exportación'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class MedioPago(models.Model):
    """Medio de pago de un pago programado (efectivo/transferencia/etc)."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=2, unique=True)
    glosa = models.CharField(max_length=50)

    class Meta:
        verbose_name = 'medio de pago'
        verbose_name_plural = 'medios de pago'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class ImpuestoAdicionalRetencion(models.Model):
    """Impuesto adicional o retención aplicable a un ítem de un DTE."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    tipo = models.CharField(max_length=1)
    glosa = models.CharField(max_length=100)
    tasa = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        verbose_name = 'impuesto adicional o retención'
        verbose_name_plural = 'impuestos adicionales o retenciones'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class AduanaTransporte(models.Model):
    """Vía de transporte internacional (marítimo/aéreo/etc), según Aduana."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'vía de transporte'
        verbose_name_plural = 'vías de transporte'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class AduanaModalidadVenta(models.Model):
    """Modalidad de venta de una exportación, según Aduana."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'modalidad de venta'
        verbose_name_plural = 'modalidades de venta'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class AduanaClausulaVenta(models.Model):
    """Cláusula de venta (CIF/CFR/FOB/etc) de una exportación, según Aduana."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'cláusula de venta'
        verbose_name_plural = 'cláusulas de venta'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class AduanaUnidad(models.Model):
    """Unidad de peso/medida (tara, peso bruto/neto), según Aduana."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=50)

    class Meta:
        verbose_name = 'unidad de medida'
        verbose_name_plural = 'unidades de medida'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class AduanaPuerto(models.Model):
    """Puerto de embarque/desembarque de una exportación, según Aduana."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'puerto'
        verbose_name_plural = 'puertos'
        ordering = ['glosa']

    def __str__(self) -> str:
        return f'{self.glosa}'


class AduanaTipoBulto(models.Model):
    """Tipo de bulto/embalaje de una exportación, según Aduana."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'tipo de bulto'
        verbose_name_plural = 'tipos de bulto'
        ordering = ['glosa']

    def __str__(self) -> str:
        return f'{self.glosa}'


class AduanaMoneda(models.Model):
    """
    Moneda de un documento de exportación, según Aduana.

    `glosa` (no `codigo`) es lo que efectivamente se manda como
    `TpoMoneda` en el DTE — el SII identifica la moneda por este nombre
    (ej. `DOLAR USA`), no por `codigo`.
    """

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=20, unique=True)
    codigo_iso = models.CharField(max_length=3, blank=True)

    class Meta:
        verbose_name = 'moneda'
        verbose_name_plural = 'monedas'
        ordering = ['glosa']

    def __str__(self) -> str:
        return f'{self.glosa}'


class TipoDte(models.Model):
    """Tipo de Documento Tributario Electrónico."""

    class Categoria(models.TextChoices):
        TRIBUTARIO = 'tributario', 'Tributario'
        INFORMATIVO = 'informativo', 'Informativo'

    class Operacion(models.TextChoices):
        SUMA = 'suma', 'Suma'
        RESTA = 'resta', 'Resta'

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=50)
    glosa_corta = models.CharField(
        max_length=50,
        blank=True,
        help_text=(
            'Se autocompleta desde `glosa` al guardar si se deja vacío '
            '— mismo criterio que `CodigoDocumento::getNombreCorto()` '
            'en libredte-lib-core (Document/Enum): sacar el sufijo '
            '" Electrónica" de la glosa oficial del SII.'
        ),
    )
    categoria = models.CharField(
        max_length=11,
        choices=Categoria.choices,
        blank=True,
    )
    operacion = models.CharField(
        max_length=5,
        choices=Operacion.choices,
        blank=True,
    )
    compra = models.BooleanField(default=False)
    venta = models.BooleanField(default=False)
    cedible = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'tipo de DTE'
        verbose_name_plural = 'tipos de DTE'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Autocompleta `glosa_corta` desde `glosa` si no viene definida."""
        if not self.glosa_corta:
            self.glosa_corta = self.glosa.replace(' Electrónica', '')
        super().save(*args, **kwargs)

    @property
    def label(self) -> str:
        """`glosa_corta` para UI (tablas, encabezados) — cae a `glosa`."""
        return self.glosa_corta or self.glosa


class ItemCategoria(models.Model):
    """
    Categoría de ítems de facturación, del contribuyente.

    Lista plana (sin jerarquía) a propósito.
    """

    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.CASCADE,
        related_name='item_categorias',
    )
    nombre = models.CharField(max_length=35)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'categoría de ítem'
        verbose_name_plural = 'categorías de ítem'
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'nombre'],
                name='categoria_item_unica_por_contribuyente_y_nombre',
            ),
        ]

    def __str__(self) -> str:
        return self.nombre


class Item(models.Model):
    """
    Ítem de facturación (producto o servicio) reutilizable.

    Campos alineados con `ItemForm` (`forms.py`, la fila del `Detalle`
    en `/billing/emitir`) para poder rellenarla desde acá.

    `IndicadorExencion`/`DescuentoTipo` duplican el vocabulario de
    `IndExe`/`TpoValor` que ya vive en `enums.py` — a propósito, no por
    olvido: ese archivo es solo para los campos del formulario de
    `/billing/emitir` (ver su propio docstring), un modelo persistente
    define su propio enum (mismo patrón que `TipoDte.Categoria`).

    `precio` es el valor tal como se ingresó — puede ser neto o bruto
    según `bruto` (mismo par de campos que legacy, `Model_Item::
    $precio`/`$bruto`); usar `precio_neto` para obtener siempre el
    valor neto, que es lo que espera `Detalle.PrcItem`.
    """

    class IndicadorExencion(models.IntegerChoices):
        """`IndExe` — motivo de exención/no-IVA (`None` = afecto)."""

        NO_AFECTO = 1, 'No afecto o exento de IVA'
        NO_FACTURABLE = 2, 'No facturable'
        GARANTIA = 3, 'Garantía por depósito o envase'
        NO_CONSTITUYE_VENTA = 4, 'No constituye venta'
        ITEM_A_REBAJAR = 5, 'Ítem a rebajar'
        NO_FACTURABLE_NEGATIVO = 6, 'No facturable negativo'

    class DescuentoTipo(models.TextChoices):
        """`TpoValor` — unidad del descuento por defecto del ítem."""

        PORCENTAJE = '%', 'Porcentaje'
        MONTO = '$', 'Monto'

    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.CASCADE,
        related_name='items',
    )
    codigo_tipo = models.CharField(max_length=10, default='INT1')
    codigo = models.CharField(max_length=35)
    nombre = models.CharField(max_length=80)
    descripcion = models.CharField(max_length=1000, blank=True)
    categoria = models.ForeignKey(
        ItemCategoria,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='items',
    )
    unidad = models.CharField(max_length=4, blank=True)
    precio = models.IntegerField()
    bruto = models.BooleanField(
        default=False,
        help_text='Si `precio` ya incluye IVA. Ver `precio_neto`.',
    )
    indicador_exencion = models.IntegerField(
        choices=IndicadorExencion.choices,
        null=True,
        blank=True,
    )
    descuento = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    descuento_tipo = models.CharField(
        max_length=1,
        choices=DescuentoTipo.choices,
        default=DescuentoTipo.PORCENTAJE,
    )
    impuesto_adicional = models.ForeignKey(
        ImpuestoAdicionalRetencion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='items',
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'ítem'
        verbose_name_plural = 'ítems'
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'codigo_tipo', 'codigo'],
                name='item_unico_por_contribuyente_tipo_y_codigo',
            ),
        ]

    def __str__(self) -> str:
        return self.nombre

    @property
    def precio_neto(self) -> int:
        """
        `precio` en neto — lo que espera `Detalle.PrcItem` al emitir.

        Si `bruto` es `False`, `precio` ya es neto. Si es `True`, se le
        quita el IVA (19% fijo) — salvo que el ítem esté exento
        (`indicador_exencion`), donde bruto y neto son el mismo valor
        (no hay IVA que quitar). Misma fórmula que legacy
        (`Model_Item::getPrecio()`/`getPrecioBruto()`), con la misma
        limitación: no considera `impuesto_adicional` al convertir.
        """
        if not self.bruto or self.indicador_exencion is not None:
            return self.precio
        return round(self.precio / 1.19)

    @property
    def descuento_neto(self) -> Decimal:
        """
        `descuento` en neto — análoga a `precio_neto`.

        Un descuento en `%` (`DescuentoTipo.PORCENTAJE`) no se ve
        afectado por `bruto`, se entrega tal cual. Uno en `$`
        (`DescuentoTipo.MONTO`) sí necesita la misma conversión que
        `precio_neto`.
        """
        if self.descuento_tipo == self.DescuentoTipo.PORCENTAJE:
            return self.descuento
        if not self.bruto or self.indicador_exencion is not None:
            return self.descuento
        return round(self.descuento / Decimal('1.19'), 2)


class Receptor(models.Model):
    """
    Cliente de un contribuyente, al que se le emiten DTE.

    Todo es opcional salvo `rut`/`dv`/`pais` (`save()` deja `pais` en
    Chile si no se especifica otro) — un receptor puede crearse con
    datos incompletos y completarse después. Para un receptor
    extranjero, `comuna` queda vacía y se usan `ciudad`/`pais` en su
    lugar — el SII no exige comuna para extranjeros. `es_extranjero`
    (`pais` distinto de Chile) es la señal que usa el resto del código
    para elegir entre uno u otro. `numero_identificacion` es el
    `NumId` del SII: el documento de identidad del receptor en su país
    de origen, solo relevante (y solo enviado al SII) en una
    exportación (33/34/39/41 no lo usan, solo 110/111/112). Sus datos
    se actualizan con cada documento que lo referencia (ver
    `biller._resolver_receptor()`) — quien manda estos datos en cada
    documento es el propio receptor, no algo que el contribuyente
    cargue una vez y mantenga fijo.
    """

    id = models.AutoField(primary_key=True)
    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.PROTECT,
        related_name='receptores',
    )
    rut = models.IntegerField()
    dv = DvField()
    codigo_interno = models.CharField(max_length=20, blank=True)
    razon_social = models.CharField(max_length=100, blank=True)
    giro = models.CharField(max_length=40, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(max_length=80, blank=True)
    direccion = models.CharField(max_length=70, blank=True)
    comuna = models.ForeignKey(
        Comuna,
        on_delete=models.PROTECT,
        related_name='receptores',
        null=True,
        blank=True,
    )
    ciudad = models.CharField(max_length=20, blank=True)
    pais = models.ForeignKey(
        Pais,
        on_delete=models.PROTECT,
        related_name='receptores',
    )
    numero_identificacion = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'receptor'
        verbose_name_plural = 'receptores'
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'codigo_interno'],
                name='receptor_unico_por_contribuyente_y_codigo_interno',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.rut}-{self.dv} {self.razon_social}'.strip()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Autoasigna `codigo_interno` (RUT+DV) y `pais` (Chile) si faltan."""
        if not self.codigo_interno:
            self.codigo_interno = f'{self.rut:09d}{self.dv.upper()}'
        if self.pais_id is None:
            self.pais_id = Pais.objects.only('id').get(codigo=Pais.CHILE).id
        super().save(*args, **kwargs)

    @property
    def es_extranjero(self) -> bool:
        """`True` si `pais` es distinto de Chile."""
        return self.pais.codigo != Pais.CHILE


class Emisor(models.Model):
    """
    Contraparte que emite DTE recibidos por un contribuyente.

    Análogo a `Receptor`, pero para el sentido contrario: no es a quien
    el contribuyente le emite documentos, es quien le emite documentos
    al contribuyente (un proveedor, o quien corresponda según el DTE).
    Igual que `Receptor`, sus datos se actualizan con cada documento
    que lo referencia — quien manda estos datos en cada documento es
    la propia contraparte, no algo que el contribuyente cargue una vez
    y mantenga fijo.
    """

    id = models.AutoField(primary_key=True)
    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.PROTECT,
        related_name='emisores',
    )
    rut = models.IntegerField()
    dv = DvField()
    codigo_interno = models.CharField(max_length=20, blank=True)
    razon_social = models.CharField(max_length=100, blank=True)
    giro = models.CharField(max_length=80, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(max_length=80, blank=True)
    direccion = models.CharField(max_length=70, blank=True)
    comuna = models.ForeignKey(
        Comuna,
        on_delete=models.PROTECT,
        related_name='emisores',
        null=True,
        blank=True,
    )
    ciudad = models.CharField(max_length=20, blank=True)
    pais = models.ForeignKey(
        Pais,
        on_delete=models.PROTECT,
        related_name='emisores',
    )
    numero_identificacion = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'emisor'
        verbose_name_plural = 'emisores'
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'codigo_interno'],
                name='emisor_unico_por_contribuyente_y_codigo_interno',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.rut}-{self.dv} {self.razon_social}'.strip()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Autoasigna `codigo_interno` (RUT+DV) y `pais` (Chile) si faltan."""
        if not self.codigo_interno:
            self.codigo_interno = f'{self.rut:09d}{self.dv.upper()}'
        if self.pais_id is None:
            self.pais_id = Pais.objects.only('id').get(codigo=Pais.CHILE).id
        super().save(*args, **kwargs)

    @property
    def es_extranjero(self) -> bool:
        """`True` si `pais` es distinto de Chile."""
        return self.pais.codigo != Pais.CHILE


class CafFolio(models.Model):
    """
    Contador de folios disponibles de un contribuyente para un tipo de DTE.

    Un contador explícito (`siguiente`/`disponibles`), no un `MAX(folio)`
    calculado al vuelo — evita condiciones de carrera al emitir folios
    bajo concurrencia.
    """

    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.PROTECT,
        related_name='caf_folios',
    )
    tipo_dte = models.ForeignKey(
        TipoDte,
        on_delete=models.PROTECT,
        related_name='caf_folios',
    )
    siguiente = models.BigIntegerField()
    disponibles = models.IntegerField()
    alerta = models.IntegerField()
    alertado = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'contador de folios'
        verbose_name_plural = 'contadores de folios'
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'tipo_dte'],
                name='caf_folio_unico_por_contribuyente_y_tipo_dte',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.contribuyente} / {self.tipo_dte}: {self.disponibles}'


# IDK -> ambiente real del SII que emitió el CAF (ver
# `SiiEnvironment::CAF_IDKS` en libredte-lib-core). El IDK 666
# (`CafFaker::IDK`, misma biblioteca) marca un CAF ficticio y a
# propósito no aparece acá — `.get()` devuelve `None` para ese caso.
_AMBIENTE_POR_IDK = {
    300: SiiEnvironment.PRODUCTION,
    100: SiiEnvironment.CERTIFICATION,
}


def _diferencia_calendario(desde: date, hasta: date) -> tuple[int, int, int]:
    """
    (años, meses, días) de calendario entre `desde` y `hasta`.

    Mismo algoritmo que `DateTime::diff()` de PHP (lo que usa
    `Caf::getMesesAutorizacion()` en libredte-lib-core): resta de
    calendario real, no meses fijos de 30 días.
    """
    anios = hasta.year - desde.year
    meses = hasta.month - desde.month
    dias = hasta.day - desde.day
    if dias < 0:
        meses -= 1
        mes_anterior = hasta.month - 1 or 12
        anio_mes_anterior = hasta.year if hasta.month > 1 else hasta.year - 1
        dias += calendar.monthrange(anio_mes_anterior, mes_anterior)[1]
    if meses < 0:
        anios -= 1
        meses += 12
    return anios, meses, dias


class Caf(XmlBase64Mixin, models.Model):
    """
    CAF (Código de Autorización de Folios) cargado para un contribuyente.

    Un contribuyente/tipo de DTE puede tener varios CAF cargados en el
    tiempo, cada uno con su propio rango de folios (`desde`/`hasta`).

    Solo persiste lo que no se puede recalcular después (`idk`,
    `fecha_autorizacion`, `fecha_vencimiento`, tal como los entrega el
    `CafDto` del SDK al cargarlo) — `vigente`/`meses_autorizacion`
    dependen de la fecha actual, y `ambiente`/`certificacion` se derivan
    de `idk`, así que van como `@property`, no como columnas.
    """

    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.PROTECT,
        related_name='cafs',
    )
    tipo_dte = models.ForeignKey(
        TipoDte,
        on_delete=models.PROTECT,
        related_name='cafs',
    )
    desde = models.BigIntegerField()
    hasta = models.BigIntegerField()
    xml_base64 = models.TextField(
        help_text='XML del CAF en base64, tal cual lo entrega la API.',
    )
    fecha_autorizacion = models.DateField(
        help_text='Fecha de autorización del CAF (tag <FA> del XML).',
    )
    fecha_vencimiento = models.DateField(
        null=True,
        blank=True,
        help_text=(
            'Null si el tipo de documento no vence (ver '
            'Caf::hasVencimiento() en libredte-lib-core).'
        ),
    )
    idk = models.IntegerField(
        help_text='Identificador de la llave (IDK) del CAF.',
    )

    class Meta:
        verbose_name = 'CAF'
        verbose_name_plural = 'CAF'
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'tipo_dte', 'desde'],
                name='caf_unico_por_contribuyente_tipo_dte_y_desde',
            ),
        ]

    def __str__(self) -> str:
        return (
            f'{self.contribuyente} / {self.tipo_dte}: '
            f'{self.desde}-{self.hasta}'
        )

    @property
    def codigo(self) -> str:
        """
        Igual a `Caf::getId()` en libredte-lib-core.

        Se llama `codigo` (no `id`) porque ese nombre ya lo ocupa la PK
        autogenerada del modelo — mismo criterio que `TipoDte.codigo`/
        `Pais.codigo`: un identificador generado, no un autoincremental.
        """
        return f'CAF{self.tipo_dte.codigo}D{self.desde}H{self.hasta}'

    @property
    def vigente(self) -> bool:
        """Igual a `Caf::isVigente()` en libredte-lib-core, contra hoy."""
        if self.fecha_vencimiento is None:
            return True
        return timezone.localdate() < self.fecha_vencimiento

    @property
    def meses_autorizacion(self) -> float:
        """Igual a `Caf::getMesesAutorizacion()` en libredte-lib-core."""
        anios, meses, dias = _diferencia_calendario(
            self.fecha_autorizacion,
            timezone.localdate(),
        )
        total: float = meses + anios * 12
        if dias:
            total += round(dias / 30, 2)
        return total

    @property
    def ambiente(self) -> SiiEnvironment | None:
        """
        Ambiente del SII que emitió este CAF, resuelto desde `idk`.

        Igual a `Caf::getEnvironment()` en libredte-lib-core — `None`
        para un CAF ficticio o un IDK no reconocido.
        """
        return _AMBIENTE_POR_IDK.get(self.idk)

    @property
    def certificacion(self) -> int | None:
        """Igual a `Caf::getCertificacion()`: el valor plano de `ambiente`."""
        return self.ambiente.value if self.ambiente is not None else None


class DteEmitido(XmlBase64Mixin, models.Model):
    """DTE emitido por un contribuyente."""

    id = models.BigAutoField(primary_key=True)
    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.PROTECT,
        related_name='dtes_emitidos',
    )
    tipo_dte = models.ForeignKey(
        TipoDte,
        on_delete=models.PROTECT,
        related_name='dtes_emitidos',
    )
    receptor = models.ForeignKey(
        Receptor,
        on_delete=models.PROTECT,
        related_name='dtes_emitidos',
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='dtes_emitidos',
    )
    folio = models.BigIntegerField()
    periodo = models.PositiveIntegerField()
    fecha = models.DateField()
    neto = models.BigIntegerField(null=True, blank=True)
    exento = models.BigIntegerField(null=True, blank=True)
    iva = models.BigIntegerField(default=0)
    total = models.BigIntegerField()
    xml_base64 = models.TextField(
        help_text='XML del DTE en base64, tal cual lo entrega la API.',
    )
    track_id = models.BigIntegerField(null=True, blank=True)
    revision_estado = models.CharField(max_length=100, blank=True)
    revision_detalle = models.TextField(blank=True)
    fecha_hora_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'DTE emitido'
        verbose_name_plural = 'DTE emitidos'
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'tipo_dte', 'folio'],
                name='dte_emitido_unico_por_contribuyente_tipo_dte_y_folio',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.tipo_dte.codigo}-{self.folio} ({self.contribuyente})'

    def libro(self, _visitados: frozenset[int] | None = None) -> str:
        """
        `'compras'` o `'ventas'` — libro al que pertenece este documento.

        Si `tipo_dte` solo participa de un libro (`TipoDte.compra`/
        `.venta`, viene del catálogo SII — ej. una Factura de Compra,
        código 46, es `compra=True, venta=False`), ese es el libro, sin
        más. Si el tipo participa de ambos a la vez (ej. una Nota de
        Crédito puede anular tanto una venta como una factura de
        compra), el libro se hereda de lo que este documento referencia
        (`self.referencias`, ver `DteEmitidoReferencia`): si alguna
        referencia, recursivamente, resuelve a compras, este documento
        también es de compras — si no, por defecto es venta.

        `_visitados` corta ciclos por `pk` — no deberían existir (el
        SII no permite referencias circulares), pero el grafo no está
        garantizado acíclico por diseño de `DteEmitidoReferencia`.
        """
        if self.tipo_dte.compra and not self.tipo_dte.venta:
            return 'compras'
        if self.tipo_dte.venta and not self.tipo_dte.compra:
            return 'ventas'

        visitados = _visitados or frozenset()
        if self.pk in visitados:
            return 'ventas'
        visitados = visitados | {self.pk}

        for referencia in self.referencias.select_related(
            'referencia__tipo_dte',
        ):
            if referencia.referencia.libro(visitados) == 'compras':
                return 'compras'
        return 'ventas'


class DteEmitidoReferencia(models.Model):
    """
    Una `Referencia` del XML de un `DteEmitido`, resuelta a otro `DteEmitido`.

    Solo se persisten referencias a documentos tributarios electrónicos
    (`TpoDocRef` con un `TipoDte` conocido) — referencias a otro tipo de
    respaldo (ej. HES, guías en papel) no tienen un código de `TipoDte`
    que resolver y se descartan sin error al construir esta tabla (ver
    `biller._resolver_referencias()`). Es la base de `DteEmitido.libro()`:
    sin esto, una Nota de Crédito que anula una Factura de Compra no
    tendría cómo heredar que también es de compras.
    """

    id = models.BigAutoField(primary_key=True)
    emitido = models.ForeignKey(
        DteEmitido,
        on_delete=models.CASCADE,
        related_name='referencias',
    )
    referencia = models.ForeignKey(
        DteEmitido,
        on_delete=models.PROTECT,
        related_name='referenciado_por',
    )
    tipo_referencia = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            '`CodRef` del XML (1=Anula, 2=Corrige texto, 3=Corrige montos).'
        ),
    )
    razon = models.CharField(max_length=90, blank=True)

    class Meta:
        verbose_name = 'referencia de DTE emitido'
        verbose_name_plural = 'referencias de DTE emitido'
        constraints = [
            models.UniqueConstraint(
                fields=['emitido', 'referencia'],
                name='dte_emitido_referencia_unica',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.emitido} → {self.referencia}'


class DteRecibido(XmlBase64Mixin, models.Model):
    """
    DTE recibido por un contribuyente, emitido por un `Emisor`.

    La unicidad incluye `emisor` (a diferencia de `DteEmitido`, donde
    el folio es del propio contribuyente): el folio es del emisor, y
    dos emisores distintos pueden perfectamente compartir el mismo
    número de folio para sus propios documentos.
    """

    id = models.BigAutoField(primary_key=True)
    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.PROTECT,
        related_name='dtes_recibidos',
    )
    tipo_dte = models.ForeignKey(
        TipoDte,
        on_delete=models.PROTECT,
        related_name='dtes_recibidos',
    )
    emisor = models.ForeignKey(
        Emisor,
        on_delete=models.PROTECT,
        related_name='dtes_recibidos',
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='dtes_recibidos',
    )
    folio = models.BigIntegerField()
    periodo = models.PositiveIntegerField()
    fecha = models.DateField()
    neto = models.BigIntegerField(null=True, blank=True)
    exento = models.BigIntegerField(null=True, blank=True)
    iva = models.BigIntegerField(default=0)
    total = models.BigIntegerField()
    xml_base64 = models.TextField(
        help_text='XML del DTE en base64, tal cual lo entrega la API.',
    )
    fecha_registro_rcv = models.DateTimeField(null=True, blank=True)
    fecha_hora_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'DTE recibido'
        verbose_name_plural = 'DTE recibidos'
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'emisor', 'tipo_dte', 'folio'],
                name='dte_recibido_unico_por_contribuyente_emisor_tipo_dte_y_folio',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.tipo_dte.codigo}-{self.folio} ({self.emisor})'

    def estado_rcv(self) -> str | None:
        """
        Estado de recepción según los eventos RCV registrados.

        Recorre `self.rcv_eventos` en orden: el primer `ERM` deja "Con
        acuse de recibo", el primer reclamo (`RCD`/`RFP`/`RFT`) deja
        "Rechazado" — `ACD` no cambia el estado por sí solo (sin `ERM`
        ni reclamo, se sigue a la regla de los 8 días de todas formas).

        Sin ningún evento de esos, pero con `fecha_registro_rcv`:
        pasados 8 días desde esa fecha sin reclamo se entiende
        recibido tácitamente (Ley 19.983) — "Recibido automáticamente";
        antes de eso, "Pendiente". Sin `fecha_registro_rcv` tampoco,
        `None` (no hay nada que informar todavía).
        """
        for evento in self.rcv_eventos.all():
            if evento.codigo == DteRecibidoRcvEvento.Codigo.ERM:
                return 'Con acuse de recibo'
            if evento.codigo in DteRecibidoRcvEvento.Codigo.reclamos():
                return 'Rechazado'

        if self.fecha_registro_rcv is None:
            return None

        vencido = timezone.now() >= self.fecha_registro_rcv + timedelta(days=8)
        return 'Recibido automáticamente' if vencido else 'Pendiente'


class DteRecibidoRcvEvento(models.Model):
    """
    Una acción registrada en el RCV del SII sobre un `DteRecibido`.

    `codigo` es el que el receptor (o el SII en su representación)
    registra vía "ingresar aceptación/reclamo" del RCV — ver
    `DteRecibido.estado_rcv()`, que deriva el estado de recepción a
    partir de estos eventos. `responsable` es el RUT de quien registró
    el evento (el propio contribuyente, la contraparte, o el SII).
    """

    class Codigo(models.TextChoices):
        ERM = 'ERM', 'Entrega Real de Mercaderías o Servicios'
        ACD = 'ACD', 'Acepta Contenido del Documento'
        RCD = 'RCD', 'Reclamo al Contenido del Documento'
        RFP = 'RFP', 'Reclamo por Falta Parcial de Mercaderías'
        RFT = 'RFT', 'Reclamo por Falta Total de Mercaderías'

        @classmethod
        def reclamos(cls) -> frozenset[str]:
            """Códigos que representan un reclamo (RCD/RFP/RFT)."""
            return frozenset({cls.RCD, cls.RFP, cls.RFT})

    id = models.BigAutoField(primary_key=True)
    dte_recibido = models.ForeignKey(
        DteRecibido,
        on_delete=models.CASCADE,
        related_name='rcv_eventos',
    )
    codigo = models.CharField(max_length=3, choices=Codigo.choices)
    responsable = models.CharField(max_length=12)
    fecha = models.DateTimeField()
    fecha_hora_sincronizado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'evento RCV de DTE recibido'
        verbose_name_plural = 'eventos RCV de DTE recibido'
        constraints = [
            models.UniqueConstraint(
                fields=['dte_recibido', 'codigo', 'responsable', 'fecha'],
                name='dte_recibido_rcv_evento_unico',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.get_codigo_display()} — {self.dte_recibido}'


class Borrador(XmlBase64Mixin, models.Model):
    """
    DTE armado pero sin folio, timbre ni firma.

    `datos` guarda `DocumentBag.document_normalized` (no `.document`):
    es la data cruda tal como la usa el builder para generar el XML
    (con los campos opcionales no usados en `False`, no omitidos) — la
    única forma que sirve para reconstruir el documento después sin
    volver a normalizar (`biller.bill_draft()`, con
    `options={'normalizer': {'normalize': False}}`); usar `.document`
    ahí corrompería la reconstrucción. `extra` guarda
    `DocumentBag.document_extra` tal cual (hoy normalmente `None`: la
    API todavía no expone una forma de pasar datos extra al construir,
    solo al renderizar). `xml_base64` es el XML del borrador (sin
    timbre) — permite previsualizarlo (`document_renderer`) sin volver
    a construirlo.

    `fecha` es la fecha de emisión que trae el propio documento
    (`Encabezado.IdDoc.FchEmis`) — un dato de negocio, puede ser
    pasada o futura; no confundir con `fecha_hora_creacion` (cuándo se
    guardó esta fila, solo se muestra en el detalle, igual que en
    `DteEmitido`). `usuario` es quien lo creó.

    Se elimina al confirmarse — `bill_draft()` no lo actualiza, lo
    reemplaza por un `DteEmitido` y lo borra.
    """

    id = models.BigAutoField(primary_key=True)
    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.PROTECT,
        related_name='borradores',
    )
    tipo_dte = models.ForeignKey(
        TipoDte,
        on_delete=models.PROTECT,
        related_name='borradores',
    )
    receptor = models.ForeignKey(
        Receptor,
        on_delete=models.PROTECT,
        related_name='borradores',
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='borradores',
    )
    fecha = models.DateField()
    datos = models.JSONField()
    extra = models.JSONField(null=True, blank=True)
    xml_base64 = models.TextField(
        help_text='XML del borrador (sin timbre) en base64.',
    )
    neto = models.BigIntegerField(null=True, blank=True)
    exento = models.BigIntegerField(null=True, blank=True)
    iva = models.BigIntegerField(default=0)
    total = models.BigIntegerField()
    fecha_hora_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Borrador'
        verbose_name_plural = 'Borradores'
        ordering = ['-fecha', '-fecha_hora_creacion']

    def __str__(self) -> str:
        return f'Borrador {self.tipo_dte.codigo} — {self.receptor}'

    @property
    def codigo(self) -> str:
        """
        Identificador legible del borrador, ej. `"33-0000042"`.

        No es un folio real — un borrador no tiene folio SII, eso se
        asigna recién al confirmar (ver `biller.bill_draft()`). Es solo
        para identificarlo en la UI mientras tanto, con la misma forma
        que un folio real (mismo espíritu que el pseudo-folio de
        `DteTmp` en el legacy, ej. `"33-A1B2C3D"`, pero derivado del
        `pk` en vez de un hash). Dos borradores vivos del mismo
        `tipo_dte` solo colisionarían si un contribuyente llegara a
        tener más de 10 millones sin confirmar ni descartar a la vez
        — un borrador es efímero, no pasa en la práctica.
        """
        return f'{self.tipo_dte.codigo}-{self.pk % 10_000_000:07d}'
