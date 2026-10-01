"""
Modelos compartidos: contribuyente, su certificado, y catálogos base.

Nada de esto es específico de un dominio (facturación, contabilidad,
RRHH) — es la identidad de la empresa ante el SII y los catálogos que
cualquier dirección/actividad necesita. `TipoDte` y los catálogos de
detalle de un documento (formas de pago, Aduana, etc.) siguen en
`apps/billing/`: son específicos de facturación, no de esta base.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from PIL import Image

from apps.core.fields import DvField, EncryptedTextField

_LOGO_ANCHO_MAXIMO = 500
_LOGO_ALTO_MAXIMO = 200
_LOGO_BYTES_MAXIMO = 100 * 1024


def _validar_tamano_logo(archivo: File[Any]) -> None:
    """
    El logo no puede pesar más de `_LOGO_BYTES_MAXIMO`.

    El límite es chico a propósito: el logo se embebe en el PDF del
    DTE, que típicamente pesa unos 50 KB en total — un logo del mismo
    orden de tamaño ya sería la mayor parte del archivo.
    """
    if archivo.size > _LOGO_BYTES_MAXIMO:
        raise ValidationError(
            f'El logo pesa {archivo.size / 1024:.0f} KB — el máximo es '
            f'{_LOGO_BYTES_MAXIMO // 1024} KB.',
        )


def _validar_dimensiones_logo(archivo: File[Any]) -> None:
    """El logo no puede superar `_LOGO_ANCHO_MAXIMO`x`_LOGO_ALTO_MAXIMO`."""
    archivo.seek(0)
    with Image.open(archivo) as imagen:
        ancho, alto = imagen.size
    archivo.seek(0)
    if ancho > _LOGO_ANCHO_MAXIMO or alto > _LOGO_ALTO_MAXIMO:
        raise ValidationError(
            f'El logo mide {ancho}x{alto}px — el máximo es '
            f'{_LOGO_ANCHO_MAXIMO}x{_LOGO_ALTO_MAXIMO}px.',
        )


class OverwriteStorage(FileSystemStorage):
    """
    Storage que reemplaza el archivo existente en vez de renombrarlo.

    El `FileSystemStorage` por defecto nunca sobreescribe: si el
    nombre ya existe, le agrega un sufijo aleatorio
    (`get_available_name()`). Con un `upload_to` determinístico
    (ver `_logo_upload_to`) el objetivo es justamente que un archivo
    nuevo reemplace al anterior, así que hay que borrar el que ya
    esté antes de guardar.
    """

    def get_available_name(
        self,
        name: str,
        # `max_length` no se usa acá, pero el nombre del parámetro no
        # es cosmético: `Storage.save()` (Django) llama a este método
        # como `get_available_name(name, max_length=max_length)`, por
        # keyword — renombrarlo (ej. `_max_length`, la convención que
        # usa el resto de este código para un parámetro no usado)
        # rompería esa llamada en tiempo de ejecución.
        max_length: int | None = None,  # noqa: ARG002
    ) -> str:
        if self.exists(name):
            self.delete(name)
        return name


class Pais(models.Model):
    """
    País según la nomenclatura de Aduana usada por el SII.

    `codigo` es el código oficial de Aduana (ej. 997 = Chile). No es la
    primary key: los códigos de catálogos externos se guardan como
    campo único, nunca como PK, para no acoplar la base de datos a una
    codificación que no controlamos.
    """

    CHILE = 997

    id = models.SmallAutoField(primary_key=True)
    codigo = models.PositiveSmallIntegerField(unique=True)
    glosa = models.CharField(max_length=60)

    class Meta:
        verbose_name = 'país'
        verbose_name_plural = 'países'
        ordering = ['glosa']

    def __str__(self) -> str:
        return self.glosa


class Comuna(models.Model):
    """
    Comuna de Chile.

    `codigo` es el identificador que usa el catálogo real de comunas de
    `libredte-lib-core` (ver `seeders.seed()`) — en la práctica, el
    nombre de la comuna en mayúsculas, no un código numérico SII: se
    carga tal cual lo entrega ese catálogo, sin reinterpretarlo. Campo
    único, no primary key.
    """

    id = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=60, unique=True)
    glosa = models.CharField(max_length=60)

    class Meta:
        verbose_name = 'comuna'
        verbose_name_plural = 'comunas'
        ordering = ['glosa']

    def __str__(self) -> str:
        return self.glosa


class ActividadEconomica(models.Model):
    """Actividad económica según el clasificador del SII."""

    id = models.AutoField(primary_key=True)
    codigo = models.PositiveIntegerField(unique=True)
    glosa = models.CharField(max_length=150)
    afecta_iva = models.BooleanField(null=True, blank=True)

    class Meta:
        verbose_name = 'actividad económica'
        verbose_name_plural = 'actividades económicas'
        ordering = ['codigo']

    def __str__(self) -> str:
        return f'{self.codigo} - {self.glosa}'


class Certificado(models.Model):
    """
    Certificado digital subido por un usuario de la plataforma.

    Lo administra el usuario desde su perfil — una entidad de otra app
    (`Contribuyente`, y a futuro cualquiera que firme documentos ante
    el SII) solo enlaza uno de los que su propio usuario ya subió, no
    lo carga directamente. Un mismo certificado puede enlazarse a más
    de una de esas entidades del mismo usuario (ej. un contador que
    firma DTE de varias empresas con su propio certificado de
    mandatario).

    `certificado_id` es el RUT del titular del certificado (no un
    número de serie) — dos certificados con el mismo `certificado_id`
    del mismo usuario son, en la práctica, el mismo certificado
    renovado: subir uno nuevo reemplaza el anterior (`update_or_create`
    en `certificate_manager.save_certificate`), y toda entidad que ya
    lo tuviera enlazado pasa a usar la versión nueva sin más. Otro
    usuario sí puede tener su propio certificado con el mismo
    `certificado_id` — no hay nada raro en que dos personas distintas
    suban un certificado a nombre del mismo RUT.
    """

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='certificados',
    )
    certificado_id = models.CharField(max_length=20)
    nombre = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    issuer = models.CharField(
        max_length=150,
        blank=True,
        help_text='Autoridad certificadora que emitió el certificado.',
    )
    x509 = models.TextField(help_text='Certificado X.509 en PEM.')
    clave_privada = EncryptedTextField(
        help_text='Clave privada en PEM, cifrada en reposo.',
    )
    valido_desde = models.DateTimeField(null=True, blank=True)
    valido_hasta = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'certificado'
        verbose_name_plural = 'certificados'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'certificado_id'],
                name='certificado_unico_por_usuario',
            ),
        ]

    def __str__(self) -> str:
        if self.nombre:
            return f'{self.nombre} ({self.certificado_id})'
        return f'Certificado {self.certificado_id}'

    @property
    def dias_vencimiento(self) -> int | None:
        """Días hasta que venza, o `None` sin vigencia registrada."""
        if not self.valido_hasta:
            return None
        hoy = timezone.localdate()
        return (self.valido_hasta.date() - hoy).days

    @property
    def dias_totales(self) -> int | None:
        """Duración total de vigencia, o `None` sin vigencia registrada."""
        if not self.valido_desde or not self.valido_hasta:
            return None
        return (self.valido_hasta.date() - self.valido_desde.date()).days

    @property
    def is_active(self) -> bool | None:
        """
        Si hoy cae entre `valido_desde` y `valido_hasta`; `None` sin vigencia.

        Se deriva de las fechas en cada lectura — a diferencia del
        `isActive` que entrega la API al momento de cargar el
        certificado, que queda fijo (y por lo tanto obsoleto apenas
        pasa el tiempo). No se guarda nada de la API para esto.
        """
        if not self.valido_desde or not self.valido_hasta:
            return None
        hoy = timezone.localdate()
        return self.valido_desde.date() <= hoy <= self.valido_hasta.date()


def _logo_upload_to(contribuyente: Contribuyente, filename: str) -> str:
    """
    Ruta determinística del logo (ver `ImageField.upload_to`).

    Determinística para que subir uno nuevo reemplace al anterior en
    vez de acumular archivos (ver `Contribuyente.logo`).
    """
    extension = filename.rsplit('.', 1)[-1].lower()
    return (
        f'contribuyentes/{contribuyente.rut}/logo-{contribuyente.rut}'
        f'.{extension}'
    )


class Contribuyente(models.Model):
    """
    Empresa que opera esta plataforma ante el SII.

    Una instancia de la app opera contra un único ambiente del SII (no
    hay columna `ambiente`/`certificacion` en ningún modelo): el
    ambiente se deriva de `autorizacion_dte_resolucion_numero` (`0` =
    certificación/pruebas; cualquier otro valor = producción, y es el
    número de la resolución real). Si se necesitan ambos ambientes, se
    levantan dos instancias separadas de la app, cada una con su propia
    base de datos.

    `usuario` es quien registró el contribuyente — determina qué
    `Certificado` puede enlazar en `certificado` (solo los que ese
    mismo usuario subió desde su perfil; ver `certificate_manager`). No
    se puede borrar un usuario mientras siga siendo dueño de un
    contribuyente (`on_delete=PROTECT`).

    Todos los campos de certificado/resolución son opcionales, igual
    que `autorizacion_dte_resolucion_fecha`: un contribuyente puede
    crearse solo con sus datos básicos (identidad/domicilio) y
    completar el resto después, ya con sesión iniciada — no se pide en
    el alta. `nombre_fantasia`/`logo`/`telefono`/`correo`/`sitio_web`
    también son opcionales — a diferencia de `razon_social`/`giro`/
    `direccion`/`comuna`, no son datos esenciales del contribuyente.
    """

    id = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='contribuyentes',
    )
    rut = models.IntegerField(unique=True)
    dv = DvField()
    razon_social = models.CharField(max_length=100)
    giro = models.CharField(max_length=80)
    direccion = models.CharField(max_length=70)
    comuna = models.ForeignKey(
        Comuna,
        on_delete=models.PROTECT,
        related_name='contribuyentes',
    )
    nombre_fantasia = models.CharField(max_length=100, blank=True)
    logo = models.ImageField(
        upload_to=_logo_upload_to,
        storage=OverwriteStorage(),
        blank=True,
        validators=[_validar_tamano_logo, _validar_dimensiones_logo],
        help_text=(
            f'Máximo {_LOGO_ANCHO_MAXIMO}x{_LOGO_ALTO_MAXIMO}px y '
            f'{_LOGO_BYTES_MAXIMO // 1024} KB.'
        ),
    )
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(max_length=80, blank=True)
    sitio_web = models.URLField(max_length=200, blank=True)
    actividades_economicas = models.ManyToManyField(
        ActividadEconomica,
        through='ContribuyenteActividadEconomica',
        related_name='contribuyentes',
    )
    autorizacion_dte_resolucion_fecha = models.DateField(
        null=True,
        blank=True,
    )
    autorizacion_dte_resolucion_numero = models.PositiveIntegerField(
        default=0,
    )
    certificado = models.ForeignKey(
        Certificado,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contribuyentes',
    )

    CERTIFICACION = 'Certificación'
    PRODUCCION = 'Producción'

    class Meta:
        verbose_name = 'contribuyente'
        verbose_name_plural = 'contribuyentes'

    def __str__(self) -> str:
        return f'{self.rut}-{self.dv} {self.razon_social}'

    @property
    def ambiente(self) -> str:
        """Ambiente SII derivado de `autorizacion_dte_resolucion_numero`."""
        if self.autorizacion_dte_resolucion_numero == 0:
            return self.CERTIFICACION
        return self.PRODUCCION

    @property
    def actividad_economica_principal(self) -> ActividadEconomica | None:
        """La actividad económica marcada `es_principal`, si hay alguna."""
        actividad = self.actividades.filter(es_principal=True).first()
        return actividad.actividad_economica if actividad else None


class ContribuyenteActividadEconomica(models.Model):
    """
    Actividad económica asociada a un contribuyente.

    Un contribuyente puede tener varias; a lo más una marcada como
    `es_principal` (impuesto vía constraint condicional, no en código).
    """

    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.CASCADE,
        related_name='actividades',
    )
    actividad_economica = models.ForeignKey(
        ActividadEconomica,
        on_delete=models.PROTECT,
        related_name='contribuyentes_actividades',
    )
    es_principal = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'actividad económica de contribuyente'
        verbose_name_plural = 'actividades económicas de contribuyente'
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'actividad_economica'],
                name='actividad_unica_por_contribuyente',
            ),
            models.UniqueConstraint(
                fields=['contribuyente'],
                condition=models.Q(es_principal=True),
                name='una_actividad_principal_por_contribuyente',
            ),
        ]

    def __str__(self) -> str:
        marca = ' (principal)' if self.es_principal else ''
        return f'{self.contribuyente} / {self.actividad_economica}{marca}'


class Sucursal(models.Model):
    """
    Sucursal de un contribuyente, incluida la casa matriz.

    El SII asigna código de sucursal también a la casa matriz (no queda
    exenta), por eso no se modela aparte de `Sucursal` — se marca con
    `es_matriz`. No hay FK desde ningún documento: qué sucursal emitió
    un documento es un dato que queda en el documento mismo, no hace
    falta duplicarlo acá.
    """

    contribuyente = models.ForeignKey(
        Contribuyente,
        on_delete=models.CASCADE,
        related_name='sucursales',
    )
    codigo_sii = models.PositiveIntegerField(null=True, blank=True)
    es_matriz = models.BooleanField(default=False)
    nombre = models.CharField(max_length=20, blank=True)
    direccion = models.CharField(max_length=70)
    comuna = models.ForeignKey(
        Comuna,
        on_delete=models.PROTECT,
        related_name='sucursales',
    )
    ciudad = models.CharField(max_length=20, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(max_length=80, blank=True)

    class Meta:
        verbose_name = 'sucursal'
        verbose_name_plural = 'sucursales'
        constraints = [
            models.UniqueConstraint(
                fields=['contribuyente', 'codigo_sii'],
                name='sucursal_unica_por_contribuyente_y_codigo_sii',
            ),
            models.UniqueConstraint(
                fields=['contribuyente'],
                condition=models.Q(es_matriz=True),
                name='una_matriz_por_contribuyente',
            ),
        ]

    def __str__(self) -> str:
        return self.nombre or f'Sucursal {self.codigo_sii or self.pk}'
