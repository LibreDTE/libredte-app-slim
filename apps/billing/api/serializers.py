"""Serializers de la API (JSON) de `billing`."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import serializers

from apps.core.utils import action_buttons

from ..models import (
    Borrador,
    DteEmitido,
    DteRecibido,
    Emisor,
    Item,
    ItemCategoria,
    Receptor,
)
from ..services.purchases_reporter import DocumentoCompra, PeriodoCompras
from ..services.sales_reporter import PeriodoVentas


class DteEmitidoSerializer(serializers.ModelSerializer[DteEmitido]):
    """Fila de "Documentos emitidos", para el listado de Tabulator."""

    tipo = serializers.CharField(source='tipo_dte.label', read_only=True)
    receptor = serializers.SerializerMethodField()
    estado = serializers.SerializerMethodField()

    class Meta:
        model = DteEmitido
        fields = [
            'id',
            'tipo',
            'folio',
            'receptor',
            'fecha',
            'total',
            'estado',
        ]

    def get_receptor(self, documento: DteEmitido) -> str:
        """Razón social, o RUT-DV si no la tiene — mismo criterio que la UI."""
        receptor = documento.receptor
        return receptor.razon_social or f'{receptor.rut}-{receptor.dv}'

    def get_estado(self, documento: DteEmitido) -> str:
        """Glosa del SII, o un guion si todavía no hay información."""
        return documento.revision_estado or '—'


class DteRecibidoSerializer(serializers.ModelSerializer[DteRecibido]):
    """Fila de "DTE recibidos", para el listado de Tabulator."""

    tipo = serializers.CharField(source='tipo_dte.label', read_only=True)
    emisor = serializers.SerializerMethodField()
    estado = serializers.SerializerMethodField()

    class Meta:
        model = DteRecibido
        fields = [
            'id',
            'tipo',
            'folio',
            'emisor',
            'fecha',
            'total',
            'estado',
        ]

    def get_emisor(self, documento: DteRecibido) -> str:
        """Razón social, o RUT-DV si no la tiene — mismo criterio que la UI."""
        emisor = documento.emisor
        return emisor.razon_social or f'{emisor.rut}-{emisor.dv}'

    def get_estado(self, documento: DteRecibido) -> str:
        """`estado_rcv()`, o un guion si todavía no se registra en el RCV."""
        return documento.estado_rcv() or '—'


class BorradorSerializer(serializers.ModelSerializer[Borrador]):
    """
    Fila de "Borradores", para el listado de Tabulator.

    Un solo botón ("Ver", igual que `DteEmitidoSerializer`) — confirmar
    y descartar viven en el detalle, no en la lista.
    """

    tipo = serializers.CharField(source='tipo_dte.label', read_only=True)
    codigo = serializers.CharField(read_only=True)
    receptor = serializers.SerializerMethodField()
    usuario: serializers.StringRelatedField[User] = (
        serializers.StringRelatedField()
    )

    class Meta:
        model = Borrador
        fields = [
            'id',
            'tipo',
            'codigo',
            'receptor',
            'fecha',
            'total',
            'usuario',
        ]

    def get_receptor(self, borrador: Borrador) -> str:
        """Razón social, o RUT-DV si no la tiene — mismo criterio que la UI."""
        receptor = borrador.receptor
        return receptor.razon_social or f'{receptor.rut}-{receptor.dv}'


class ReceptorSerializer(serializers.ModelSerializer[Receptor]):
    """
    Fila de "Receptores", para el listado de Tabulator.

    Sin `acciones`: la lista solo permite "Ver" (mismo criterio que
    `DteEmitidoSerializer`/`BorradorSerializer` — el botón se arma en
    el template vía JS sobre `id`). Editar/Eliminar viven en el
    detalle del receptor, no en la lista.
    """

    rut = serializers.SerializerMethodField()
    ubicacion = serializers.SerializerMethodField()

    class Meta:
        model = Receptor
        fields = [
            'id',
            'rut',
            'codigo_interno',
            'razon_social',
            'giro',
            'ubicacion',
            'correo',
        ]

    def get_rut(self, receptor: Receptor) -> str:
        """`RUT-DV`, como en el resto de la app."""
        return f'{receptor.rut}-{receptor.dv}'

    def get_ubicacion(self, receptor: Receptor) -> str:
        """Comuna si es nacional, ciudad si es extranjero."""
        return receptor.comuna.glosa if receptor.comuna else receptor.ciudad


class EmisorSerializer(serializers.ModelSerializer[Emisor]):
    """
    Fila de "Emisores", para el listado de Tabulator.

    Sin `acciones`: la lista solo permite "Ver" (mismo criterio que
    `ReceptorSerializer`) — no hay editar/eliminar, un `Emisor` no
    tiene CRUD manual (ver docstring del modelo).
    """

    rut = serializers.SerializerMethodField()
    ubicacion = serializers.SerializerMethodField()

    class Meta:
        model = Emisor
        fields = [
            'id',
            'rut',
            'codigo_interno',
            'razon_social',
            'giro',
            'ubicacion',
            'correo',
        ]

    def get_rut(self, emisor: Emisor) -> str:
        """`RUT-DV`, como en el resto de la app."""
        return f'{emisor.rut}-{emisor.dv}'

    def get_ubicacion(self, emisor: Emisor) -> str:
        """Comuna si es nacional, ciudad si es extranjero."""
        return emisor.comuna.glosa if emisor.comuna else emisor.ciudad


class ItemCategoriaSerializer(serializers.ModelSerializer[ItemCategoria]):
    """Fila de "Categorías", para el listado de Tabulator."""

    activa = serializers.SerializerMethodField()
    acciones = serializers.SerializerMethodField()

    class Meta:
        model = ItemCategoria
        fields = ['id', 'nombre', 'activa', 'acciones']

    def get_activa(self, categoria: ItemCategoria) -> str:
        """Sí/No — mismo criterio que `SucursalSerializer.get_es_matriz`."""
        return 'Sí' if categoria.activa else 'No'

    def get_acciones(self, categoria: ItemCategoria) -> str:
        """Editar / eliminar."""
        return action_buttons(
            (
                'Editar',
                'pen',
                reverse(
                    'billing_settings:item_categoria_editar',
                    args=[categoria.pk],
                ),
                'primary',
            ),
            (
                'Eliminar',
                'trash',
                reverse(
                    'billing_settings:item_categoria_eliminar',
                    args=[categoria.pk],
                ),
                'danger',
            ),
        )


class ItemSerializer(serializers.ModelSerializer[Item]):
    """Fila de "Productos y/o servicios", para el listado de Tabulator."""

    categoria = serializers.CharField(
        source='categoria.nombre',
        read_only=True,
        default='—',
    )
    bruto = serializers.SerializerMethodField()
    activo = serializers.SerializerMethodField()
    acciones = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            'id',
            'codigo',
            'nombre',
            'categoria',
            'precio',
            'bruto',
            'activo',
            'acciones',
        ]

    def get_bruto(self, item: Item) -> str:
        """Sí/No — mismo criterio que `SucursalSerializer.get_es_matriz`."""
        return 'Sí' if item.bruto else 'No'

    def get_activo(self, item: Item) -> str:
        """Sí/No — mismo criterio que `SucursalSerializer.get_es_matriz`."""
        return 'Sí' if item.activo else 'No'

    def get_acciones(self, item: Item) -> str:
        """Editar / eliminar."""
        return action_buttons(
            (
                'Editar',
                'pen',
                reverse('billing_settings:item_editar', args=[item.pk]),
                'primary',
            ),
            (
                'Eliminar',
                'trash',
                reverse('billing_settings:item_eliminar', args=[item.pk]),
                'danger',
            ),
        )


class PeriodoVentasSerializer(serializers.Serializer[PeriodoVentas]):
    """
    Fila de "Ventas" (índice de períodos), para el listado de Tabulator.

    `services/sales_reporter.py::periodos()` no es un `QuerySet` — es una
    agregación resuelta en Python (`DteEmitido.libro()` depende de
    resolver referencias recursivamente, no es una columna filtrable),
    así que este serializer no es un `ModelSerializer`.
    """

    periodo_glosa = serializers.CharField()
    documentos = serializers.IntegerField()
    total = serializers.IntegerField()
    acciones = serializers.SerializerMethodField()

    def get_acciones(self, fila: PeriodoVentas) -> str:
        """Ver el detalle del período."""
        return action_buttons(
            (
                'Ver',
                'eye',
                reverse('billing:ventas_periodo', args=[fila.periodo]),
                'primary',
            ),
        )


class PeriodoComprasSerializer(serializers.Serializer[PeriodoCompras]):
    """Fila de "Compras" (índice de períodos), para el listado de Tabulator."""

    periodo_glosa = serializers.CharField()
    documentos = serializers.IntegerField()
    total = serializers.IntegerField()
    acciones = serializers.SerializerMethodField()

    def get_acciones(self, fila: PeriodoCompras) -> str:
        """Ver el detalle del período."""
        return action_buttons(
            (
                'Ver',
                'eye',
                reverse('billing:compras_periodo', args=[fila.periodo]),
                'primary',
            ),
        )


class DocumentoCompraSerializer(serializers.Serializer[DocumentoCompra]):
    """
    Fila de "Documentos del período" de compras, para Tabulator.

    Une `DteEmitido` (tipo 46 y derivados) con `DteRecibido` — `origen`
    (`'emitido'`/`'recibido'`) es lo que permite armar el enlace "Ver"
    correcto para cada fila, ninguno de los dos comparte detalle.
    """

    tipo = serializers.CharField()
    folio = serializers.IntegerField()
    contraparte = serializers.CharField()
    fecha = serializers.DateField()
    total = serializers.IntegerField()
    estado = serializers.CharField()
    acciones = serializers.SerializerMethodField()

    def get_acciones(self, documento: DocumentoCompra) -> str:
        """Ver el detalle del documento — emitido o recibido, según origen."""
        return action_buttons(
            (
                'Ver',
                'eye',
                reverse(
                    'billing:emitido_detalle'
                    if documento.origen == 'emitido'
                    else 'billing:recibido_detalle',
                    args=[documento.pk],
                ),
                'primary',
            ),
        )
