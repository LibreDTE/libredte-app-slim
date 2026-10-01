"""Vistas de la API (JSON) de `billing`."""

from __future__ import annotations

import re
from typing import Any

from django.db.models import QuerySet
from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_tabulator import (
    TabulatorFilterBackend,
    TabulatorPagination,
)

from apps.core.api import PublicApiMixin, tabulator_parameters
from apps.libredte.tenancy import (
    get_current_contribuyente,
    require_current_contribuyente,
)

from ..models import (
    Borrador,
    DteEmitido,
    DteRecibido,
    Emisor,
    Item,
    ItemCategoria,
    Receptor,
)
from ..services import purchases_reporter as purchases_service
from ..services import sales_reporter as sales_service
from .serializers import (
    BorradorSerializer,
    DocumentoCompraSerializer,
    DteEmitidoSerializer,
    DteRecibidoSerializer,
    EmisorSerializer,
    ItemCategoriaSerializer,
    ItemSerializer,
    PeriodoComprasSerializer,
    PeriodoVentasSerializer,
    ReceptorSerializer,
)

_EMITIDO_CAMPOS = ['tipo', 'folio', 'receptor', 'fecha', 'total', 'estado']


@extend_schema(
    tags=['Documentos emitidos'],
    summary='Listar documentos emitidos',
    description=(
        'Documentos tributarios electrónicos emitidos por el '
        'contribuyente activo, del más reciente al más antiguo.'
    ),
    parameters=[
        *tabulator_parameters(_EMITIDO_CAMPOS),
        OpenApiParameter(
            'receptor_id',
            OpenApiTypes.INT,
            description='Acota a los documentos de un receptor.',
        ),
        OpenApiParameter(
            'periodo',
            OpenApiTypes.INT,
            description='Acota a un período `AAAAMM`, ej. `202609`.',
        ),
    ],
)
class DteEmitidoListView(PublicApiMixin, ListAPIView[DteEmitido]):
    """
    Documentos emitidos del contribuyente activo, para Tabulator.

    Reemplaza al listado embebido de siempre (`billing.views.documentos`
    volcaba todo el queryset al HTML) — acá Tabulator pide de a una
    página, filtrando/ordenando en el servidor (`TabulatorPagination`/
    `TabulatorFilterBackend`, del paquete `djangorestframework-
    tabulator`).
    """

    serializer_class = DteEmitidoSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    # `tipo`/`receptor`/`estado` son campos calculados del serializer
    # (`tipo_dte.label`, razón social o RUT-DV, la glosa del SII) — no
    # hay un campo del modelo con ese mismo nombre, así que necesitan el
    # mapeo a la ruta ORM real que espera `TabulatorFilterBackend`
    # (ver `djangorestframework-tabulator`, `filterset_fields` como
    # dict). `receptor` busca en nombre y RUT a la vez, `tipo` en glosa
    # y código del DTE (ej. "factura" o "33") — un solo campo de
    # búsqueda para ambos casos, combinados con `OR`.
    _LOOKUP_MAP = {
        'tipo': ['tipo_dte__glosa_corta', 'tipo_dte__codigo'],
        'folio': 'folio',
        'receptor': ['receptor__razon_social', 'receptor__rut'],
        'fecha': 'fecha',
        'total': 'total',
        'estado': 'revision_estado',
    }
    filterset_fields = _LOOKUP_MAP
    ordering_fields = _LOOKUP_MAP

    def get_queryset(self) -> QuerySet[DteEmitido]:
        """
        Documentos del contribuyente activo, más recientes primero.

        `receptor_id`/`periodo` (parámetros fijos, no del contrato de
        Tabulator — ver `ajaxParams` en `documentos.html`/`receptor
        _detalle.html`/`ventas_periodo.html`) acotan a los documentos
        de un receptor o un período (`AAAAMM`) puntual.

        `periodo` además acota a documentos de venta (`DteEmitido.
        libro()`) — es el filtro que usa `ventas_periodo.html`, y una
        Factura de Compra o una Nota de Crédito que la anula no son
        parte de ese reporte (ver `services/sales_reporter.py`). Como el libro
        depende de las referencias del documento y no es una columna
        filtrable, se resuelve en Python y se vuelve a envolver en un
        queryset (`pk__in`) para que seguir pagine/ordene/filtre en
        Tabulator con normalidad.
        """
        contribuyente = get_current_contribuyente(self.request)
        queryset = (
            DteEmitido.objects.filter(contribuyente=contribuyente)
            .select_related('tipo_dte', 'receptor')
            .order_by('-fecha', '-folio')
        )
        receptor_id = self.request.query_params.get('receptor_id')
        if receptor_id:
            queryset = queryset.filter(receptor_id=receptor_id)
        periodo = self.request.query_params.get('periodo')
        if periodo:
            queryset = queryset.filter(periodo=periodo)
            ids_venta = [
                dte.pk
                for dte in queryset.prefetch_related(
                    'referencias__referencia__tipo_dte',
                )
                if dte.libro() == 'ventas'
            ]
            queryset = queryset.filter(pk__in=ids_venta)
        return queryset


_RECIBIDO_CAMPOS = ['tipo', 'folio', 'emisor', 'fecha', 'total']


@extend_schema(
    tags=['Documentos recibidos'],
    summary='Listar documentos recibidos',
    description=(
        'Documentos que terceros emitieron al contribuyente activo, '
        'del más reciente al más antiguo.'
    ),
    parameters=[
        *tabulator_parameters(_RECIBIDO_CAMPOS),
        OpenApiParameter(
            'emisor_id',
            OpenApiTypes.INT,
            description='Acota a los documentos de un emisor.',
        ),
    ],
)
class DteRecibidoListView(PublicApiMixin, ListAPIView[DteRecibido]):
    """DTE recibidos del contribuyente activo, para Tabulator."""

    serializer_class = DteRecibidoSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    # `estado` no está acá: `estado_rcv()` es un método derivado de
    # `fecha_registro_rcv`/`rcv_eventos`, no una columna real — no hay
    # forma de filtrarlo/ordenarlo vía ORM (mismo criterio que
    # `es_matriz` en `SucursalListView`).
    _LOOKUP_MAP = {
        'tipo': ['tipo_dte__glosa_corta', 'tipo_dte__codigo'],
        'folio': 'folio',
        'emisor': ['emisor__razon_social', 'emisor__rut'],
        'fecha': 'fecha',
        'total': 'total',
    }
    filterset_fields = _LOOKUP_MAP
    ordering_fields = _LOOKUP_MAP

    def get_queryset(self) -> QuerySet[DteRecibido]:
        """
        Documentos del contribuyente activo, más recientes primero.

        `emisor_id` (parámetro fijo, no del contrato de Tabulator —
        ver `ajaxParams` en `emisor_detalle.html`) acota a los
        documentos recibidos de un emisor puntual.
        """
        contribuyente = get_current_contribuyente(self.request)
        queryset = (
            DteRecibido.objects.filter(contribuyente=contribuyente)
            .select_related('tipo_dte', 'emisor')
            .prefetch_related('rcv_eventos')
            .order_by('-fecha', '-folio')
        )
        emisor_id = self.request.query_params.get('emisor_id')
        if emisor_id:
            queryset = queryset.filter(emisor_id=emisor_id)
        return queryset


_BORRADOR_CAMPOS = ['tipo', 'receptor', 'fecha', 'total', 'usuario', 'codigo']


@extend_schema(
    tags=['Borradores'],
    summary='Listar borradores',
    description=(
        'Documentos preparados y todavía no emitidos ante el SII. No '
        'tienen folio: se identifican por su código.'
    ),
    parameters=tabulator_parameters(_BORRADOR_CAMPOS),
)
class BorradorListView(PublicApiMixin, ListAPIView[Borrador]):
    """Borradores del contribuyente activo, para Tabulator."""

    serializer_class = BorradorSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    # `codigo` no está acá: es un `@property` derivado del `pk` (ver
    # `Borrador.codigo`), no una columna real — `TabulatorFilterBackend`
    # solo sabe traducir a un lookup ORM (`campo__lookup=valor`), así
    # que ese filtro se resuelve a mano en `get_queryset()`.
    _LOOKUP_MAP = {
        'tipo': ['tipo_dte__glosa_corta', 'tipo_dte__codigo'],
        'receptor': ['receptor__razon_social', 'receptor__rut'],
        'fecha': 'fecha',
        'total': 'total',
        'usuario': 'usuario__username',
    }
    filterset_fields = _LOOKUP_MAP
    ordering_fields = _LOOKUP_MAP

    # Mismo formato `filter[i][field]`/`filter[i][value]` que usa
    # `TabulatorFilterBackend` (ver `rest_framework_tabulator.filters`)
    # — se reimplementa acá, acotado a un solo campo, en vez de
    # depender de sus helpers privados.
    _FILTER_FIELD_RE = re.compile(r'^filter\[(\d+)\]\[field\]$')

    def get_queryset(self) -> QuerySet[Borrador]:
        """Borradores del contribuyente activo, más recientes primero."""
        contribuyente = get_current_contribuyente(self.request)
        queryset = (
            Borrador.objects.filter(contribuyente=contribuyente)
            .select_related('tipo_dte', 'receptor', 'usuario')
            .order_by('-fecha', '-fecha_hora_creacion')
        )
        return self._filtrar_por_codigo(queryset)

    def _filtrar_por_codigo(
        self, queryset: QuerySet[Borrador]
    ) -> QuerySet[Borrador]:
        """
        Filtra por `codigo` (ej. `"33-0000100"`) buscándolo a mano.

        Sirve tanto para el código completo (`"33-0000100"`) como para
        solo los últimos 7 dígitos (`"0000100"`, o incluso `"100"`): al
        ser una búsqueda de substring sobre el código ya armado, un
        valor sin ceros a la izquierda igual matchea (`"100"` es
        substring de `"0000100"`). El volumen de borradores de un
        mismo contribuyente es chico (son efímeros — se borran al
        confirmarse o descartarse), así que resolverlo comparando en
        Python, sin traducción a SQL, es aceptable acá.
        """
        valor = self._valor_filtro_codigo()
        if not valor:
            return queryset
        valor = valor.strip().lower()
        ids = [
            borrador.pk
            for borrador in queryset
            if valor in borrador.codigo.lower()
        ]
        return queryset.filter(pk__in=ids)

    def _valor_filtro_codigo(self) -> str | None:
        """El `value` del filtro cuyo `field` sea `"codigo"`, si hay uno."""
        params = self.request.query_params
        for key, value in params.items():
            match = self._FILTER_FIELD_RE.match(key)
            if match and value == 'codigo':
                return params.get(f'filter[{match.group(1)}][value]')
        return None


_RECEPTOR_CAMPOS = [
    'rut',
    'codigo_interno',
    'razon_social',
    'giro',
    'ubicacion',
    'correo',
]


@extend_schema(
    tags=['Receptores'],
    summary='Listar receptores',
    description='Clientes a los que el contribuyente activo les emite.',
    parameters=tabulator_parameters(_RECEPTOR_CAMPOS),
)
class ReceptorListView(PublicApiMixin, ListAPIView[Receptor]):
    """Receptores del contribuyente activo, para Tabulator."""

    serializer_class = ReceptorSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    # `rut`/`ubicacion`/`acciones` son calculados del serializer (`RUT-
    # DV`, comuna o ciudad, botones) — mapeo a la ruta ORM real, mismo
    # mecanismo que `DteEmitidoListView`.
    _LOOKUP_MAP = {
        'rut': 'rut',
        'codigo_interno': 'codigo_interno',
        'razon_social': 'razon_social',
        'giro': 'giro',
        'ubicacion': ['comuna__glosa', 'ciudad'],
        'correo': 'correo',
    }
    filterset_fields = _LOOKUP_MAP
    ordering_fields = _LOOKUP_MAP

    def get_queryset(self) -> QuerySet[Receptor]:
        """Receptores del contribuyente activo."""
        contribuyente = get_current_contribuyente(self.request)
        return (
            Receptor.objects.filter(contribuyente=contribuyente)
            .select_related('comuna', 'pais')
            .order_by('razon_social')
        )


@extend_schema(
    tags=['Receptores'],
    summary='Buscar un receptor',
    description=(
        'Sin parámetros devuelve la lista completa de receptores del '
        'contribuyente activo, pensada para autocompletar. Con uno de '
        '`codigo_interno`, `rut` o `razon_social` devuelve los datos '
        'de ESE receptor. Si llega más de uno se prioriza en ese '
        'orden. Responde `404` si no hay coincidencia.'
    ),
    parameters=[
        OpenApiParameter(
            'codigo_interno',
            OpenApiTypes.STR,
            description='Código interno exacto del receptor.',
        ),
        OpenApiParameter(
            'rut',
            OpenApiTypes.STR,
            description='RUT con dígito verificador, ej. `76192083-9`.',
        ),
        OpenApiParameter(
            'razon_social',
            OpenApiTypes.STR,
            description='Razón social exacta del receptor.',
        ),
    ],
    responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
class ReceptorBuscarView(PublicApiMixin, APIView):
    """
    Autocompletar el receptor al emitir (`emitir.html`).

    Sin parámetros: la lista de receptores del contribuyente activo,
    para los `<datalist>` que ofrecen sugerencias mientras se escribe
    (uno por campo — RUT, código interno, razón social — ver
    `emitir.html`). Con uno de `codigo_interno`/`rut`/`razon_social`:
    los datos de ESE receptor, ya en el shape que espera
    `DocumentoForm`. Si viene más de un parámetro a la vez (no debería
    pasar desde el JS, cada campo dispara su propia búsqueda), se
    prioriza en ese orden — mismo criterio que
    `biller._resolver_receptor()`.
    """

    def get(self, request: Request) -> Response:
        contribuyente = get_current_contribuyente(request)
        codigo_interno = request.query_params.get('codigo_interno')
        rut = request.query_params.get('rut')
        razon_social = request.query_params.get('razon_social')

        if not codigo_interno and not rut and not razon_social:
            receptores = Receptor.objects.filter(
                contribuyente=contribuyente,
            ).order_by('razon_social')
            return Response(
                [
                    {
                        'rut': f'{receptor.rut}-{receptor.dv}',
                        'codigo_interno': receptor.codigo_interno,
                        'razon_social': receptor.razon_social,
                    }
                    for receptor in receptores
                ]
            )

        queryset = Receptor.objects.filter(contribuyente=contribuyente)
        receptor = None
        if codigo_interno:
            receptor = queryset.filter(codigo_interno=codigo_interno).first()
        if receptor is None and rut:
            rut_partes = _rut_dv(rut)
            if rut_partes is not None:
                receptor = queryset.filter(
                    rut=rut_partes[0],
                    dv=rut_partes[1],
                ).first()
        if receptor is None and razon_social:
            receptor = (
                queryset.filter(razon_social__iexact=razon_social)
                .order_by('razon_social')
                .first()
            )
        if receptor is None:
            raise Http404

        return Response(_receptor_form_payload(receptor))


def _rut_dv(rut_con_dv: str) -> tuple[int, str] | None:
    """
    `(rut, dv)` desde un RUT con el formato `NNNNNNNN-D` del DTE.

    `None` si `rut_con_dv` no tiene ese formato — puede llegar
    incompleto (el usuario todavía escribiendo) o mal tipeado; no es
    un caso para levantar un error, simplemente no hay nada que
    buscar por RUT todavía.
    """
    try:
        rut, dv = rut_con_dv.split('-')
        return int(rut), dv
    except ValueError:
        return None


def _receptor_form_payload(receptor: Receptor) -> dict[str, str]:
    """
    El shape que espera `DocumentoForm` para los campos del receptor.

    `CmnaRecep` responde `comuna.glosa` porque eso es lo que
    `DocumentoForm.CmnaRecep` usa hoy como `value` de cada opción del
    `<select>` (`(c.glosa, c.glosa)`, ver `forms.py`) — es una
    coincidencia de la implementación actual, no una regla: si ese
    `value` pasa a ser un código en el futuro, esto también debe
    actualizarse.
    """
    return {
        'RUTRecep': f'{receptor.rut}-{receptor.dv}',
        'RznSocRecep': receptor.razon_social,
        'GiroRecep': receptor.giro,
        'CdgIntRecep': receptor.codigo_interno,
        'Contacto': receptor.telefono,
        'CorreoRecep': receptor.correo,
        'DirRecep': receptor.direccion,
        'CmnaRecep': receptor.comuna.glosa if receptor.comuna else '',
        'CiudadRecep': receptor.ciudad,
        'Nacionalidad': str(receptor.pais.codigo) if receptor.pais else '',
        'NumId': receptor.numero_identificacion,
    }


_EMISOR_CAMPOS = _RECEPTOR_CAMPOS


@extend_schema(
    tags=['Emisores'],
    summary='Listar emisores',
    description=(
        'Proveedores que le emiten documentos al contribuyente activo.'
    ),
    parameters=tabulator_parameters(_EMISOR_CAMPOS),
)
class EmisorListView(PublicApiMixin, ListAPIView[Emisor]):
    """Emisores del contribuyente activo, para Tabulator."""

    serializer_class = EmisorSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    _LOOKUP_MAP = {
        'rut': 'rut',
        'codigo_interno': 'codigo_interno',
        'razon_social': 'razon_social',
        'giro': 'giro',
        'ubicacion': ['comuna__glosa', 'ciudad'],
        'correo': 'correo',
    }
    filterset_fields = _LOOKUP_MAP
    ordering_fields = _LOOKUP_MAP

    def get_queryset(self) -> QuerySet[Emisor]:
        """Emisores del contribuyente activo."""
        contribuyente = get_current_contribuyente(self.request)
        return (
            Emisor.objects.filter(contribuyente=contribuyente)
            .select_related('comuna', 'pais')
            .order_by('razon_social')
        )


@extend_schema(
    tags=['Ítems'],
    summary='Listar categorías de ítems',
    description='Categorías con las que se agrupa el catálogo de ítems.',
    parameters=tabulator_parameters(['nombre']),
)
class ItemCategoriaListView(PublicApiMixin, ListAPIView[ItemCategoria]):
    """Categorías de ítems del contribuyente activo, para Tabulator."""

    serializer_class = ItemCategoriaSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    # `activa` no es filtrable — mismo criterio que `es_matriz` en
    # `SucursalListView` (booleano, sin valor de texto que le calce).
    _LOOKUP_MAP = {'nombre': 'nombre'}
    filterset_fields = _LOOKUP_MAP
    ordering_fields = {**_LOOKUP_MAP, 'activa': 'activa'}

    def get_queryset(self) -> QuerySet[ItemCategoria]:
        """Categorías del contribuyente activo."""
        contribuyente = get_current_contribuyente(self.request)
        return ItemCategoria.objects.filter(contribuyente=contribuyente)


_ITEM_CAMPOS = ['codigo', 'nombre', 'categoria', 'precio']


@extend_schema(
    tags=['Ítems'],
    summary='Listar ítems del catálogo',
    description=(
        'Catálogo de productos y servicios del contribuyente activo, '
        'con su precio y su categoría.'
    ),
    parameters=tabulator_parameters(_ITEM_CAMPOS),
)
class ItemListView(PublicApiMixin, ListAPIView[Item]):
    """Ítems del contribuyente activo, para Tabulator."""

    serializer_class = ItemSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    # `categoria`/`acciones` son calculados del serializer (glosa de la
    # FK, botones); `activo` no es filtrable — mismo criterio que
    # `es_matriz` en `SucursalListView`.
    _LOOKUP_MAP = {
        'codigo': 'codigo',
        'nombre': 'nombre',
        'categoria': 'categoria__nombre',
        'precio': 'precio',
    }
    filterset_fields = _LOOKUP_MAP
    ordering_fields = {**_LOOKUP_MAP, 'activo': 'activo'}

    def get_queryset(self) -> QuerySet[Item]:
        """Ítems del contribuyente activo."""
        contribuyente = get_current_contribuyente(self.request)
        return (
            Item.objects.filter(contribuyente=contribuyente)
            .select_related('categoria')
            .order_by('nombre')
        )


@extend_schema(
    tags=['Ítems'],
    summary='Buscar un ítem',
    description=(
        'Sin `codigo` devuelve el catálogo completo de ítems activos, '
        'sin paginar, pensado para autocompletar. Con `codigo` '
        'devuelve los datos de ESE ítem. Responde `404` si no hay '
        'coincidencia.'
    ),
    parameters=[
        OpenApiParameter(
            'codigo',
            OpenApiTypes.STR,
            description='Código del ítem en el catálogo.',
        ),
        OpenApiParameter(
            'codigo_tipo',
            OpenApiTypes.STR,
            description=('Desempata cuando dos ítems comparten `codigo`.'),
        ),
    ],
    responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
class ItemBuscarView(PublicApiMixin, APIView):
    """
    Autocompletar un ítem al emitir (`_emitir_fila_item.html`).

    Sin `codigo`: la lista de ítems activos del contribuyente activo,
    para el `<datalist>` que ofrece sugerencias mientras se escribe
    (ver `items.html` — mismo catálogo, sin paginar: son pocas filas y
    hace falta la lista completa para filtrar en el navegador, no una
    página a la vez). Con `codigo` (y opcionalmente `codigo_tipo` — si
    no viene se busca por `codigo` a secas, `Item` ya tiene
    `ordering = ['nombre']` así que el resultado es determinístico si
    hay más de una coincidencia): los datos de ESE ítem, ya en el
    shape que espera `ItemForm`.
    """

    def get(self, request: Request) -> Response:
        contribuyente = get_current_contribuyente(request)
        codigo = request.query_params.get('codigo')

        if not codigo:
            items = Item.objects.filter(
                contribuyente=contribuyente,
                activo=True,
            ).order_by('nombre')
            return Response(
                [
                    {
                        'codigo': item.codigo,
                        'codigo_tipo': item.codigo_tipo,
                        'nombre': item.nombre,
                        'descripcion': item.descripcion,
                    }
                    for item in items
                ]
            )

        queryset = Item.objects.filter(
            contribuyente=contribuyente,
            activo=True,
            codigo=codigo,
        )
        codigo_tipo = request.query_params.get('codigo_tipo')
        if codigo_tipo:
            queryset = queryset.filter(codigo_tipo=codigo_tipo)

        item = queryset.select_related('impuesto_adicional').first()
        if item is None:
            raise Http404

        return Response(_item_form_payload(item))


def _item_form_payload(item: Item) -> dict[str, str | int]:
    """El shape que espera `ItemForm` para una fila del `Detalle`."""
    return {
        'TpoCodigo': item.codigo_tipo,
        'VlrCodigo': item.codigo,
        'NmbItem': item.nombre,
        'DscItem': item.descripcion,
        'IndExe': (
            str(item.indicador_exencion)
            if item.indicador_exencion is not None
            else '0'
        ),
        'UnmdItem': item.unidad,
        'PrcItem': item.precio_neto,
        'CodImpAdic': (
            str(item.impuesto_adicional.codigo)
            if item.impuesto_adicional
            else ''
        ),
        'ValorDR': str(item.descuento_neto),
        'TpoValor': item.descuento_tipo,
    }


_PERIODO_CAMPOS = ['periodo_glosa', 'documentos', 'total']


@extend_schema(
    tags=['Ventas'],
    summary='Listar períodos de venta',
    description=(
        'Un registro por período (`AAAAMM`) con documentos de venta, '
        'con cuántos documentos tiene y su total.'
    ),
    parameters=tabulator_parameters(_PERIODO_CAMPOS),
)
class VentasPeriodosListView(PublicApiMixin, ListAPIView[Any]):
    """
    Períodos con documentos de venta, para Tabulator.

    `get_queryset()` no devuelve un `QuerySet` —
    `services/sales_reporter.py::periodos()` es una agregación ya
    resuelta en Python — así que `TabulatorFilterBackend`/
    `TabulatorPagination` filtran/paginan sobre esa lista directamente
    (soportan ambos, ver
    `rest_framework_tabulator.filters`). Parametrizado `[Any]`: el tipo
    genérico de `ListAPIView` exige un `Model` de Django, y
    `PeriodoVentas` (lo que esta vista realmente lista) no lo es.
    """

    serializer_class = PeriodoVentasSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    # `periodo_glosa` busca tanto por el texto ("Septiembre 2026") como
    # por el período crudo (`202609`) a la vez — pero solo el crudo
    # sirve para ordenar cronológicamente (el texto ordenaría
    # alfabético, no por fecha).
    filterset_fields = {
        'periodo_glosa': ['periodo_glosa', 'periodo'],
        'documentos': 'documentos',
        'total': 'total',
    }
    ordering_fields = {
        'periodo_glosa': 'periodo',
        'documentos': 'documentos',
        'total': 'total',
    }

    def get_queryset(self) -> Any:
        """Períodos de venta del contribuyente activo."""
        contribuyente = require_current_contribuyente(self.request)
        return sales_service.periodos(contribuyente)


@extend_schema(
    tags=['Compras'],
    summary='Listar períodos de compra',
    description=(
        'Un registro por período (`AAAAMM`) con documentos de compra, '
        'con cuántos documentos tiene y su total.'
    ),
    parameters=tabulator_parameters(_PERIODO_CAMPOS),
)
class ComprasPeriodosListView(PublicApiMixin, ListAPIView[Any]):
    """
    Períodos con documentos de compra, para Tabulator.

    Ver `VentasPeriodosListView` — mismo criterio (no es un `QuerySet`,
    parametrizado `[Any]` por el mismo motivo).
    """

    serializer_class = PeriodoComprasSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    filterset_fields = {
        'periodo_glosa': ['periodo_glosa', 'periodo'],
        'documentos': 'documentos',
        'total': 'total',
    }
    ordering_fields = {
        'periodo_glosa': 'periodo',
        'documentos': 'documentos',
        'total': 'total',
    }

    def get_queryset(self) -> Any:
        """Períodos de compra del contribuyente activo."""
        contribuyente = require_current_contribuyente(self.request)
        return purchases_service.periodos(contribuyente)


_COMPRA_DOC_CAMPOS = [
    'tipo',
    'folio',
    'contraparte',
    'fecha',
    'total',
    'estado',
]


@extend_schema(
    tags=['Compras'],
    summary='Listar documentos de un período de compra',
    description=(
        'Documentos de compra de un período, mezclando los recibidos '
        'de terceros con los que el propio contribuyente emitió y '
        'también son compra (ej. una factura de compra).'
    ),
    parameters=[
        *tabulator_parameters(_COMPRA_DOC_CAMPOS),
        OpenApiParameter(
            'periodo',
            OpenApiTypes.INT,
            required=True,
            description='Período `AAAAMM`, ej. `202609`.',
        ),
    ],
)
class ComprasPeriodoDocumentosListView(PublicApiMixin, ListAPIView[Any]):
    """
    Documentos de compra (`DteEmitido` + `DteRecibido`) de un período.

    A diferencia de `DteEmitidoListView`/`DteRecibidoListView`, acá no
    hay un único `QuerySet` posible —
    `services/purchases_reporter.py::documentos_periodo()` ya arma la
    lista mezclando ambos modelos, y `TabulatorFilterBackend`/
    `TabulatorPagination` filtran/paginan sobre esa lista directamente
    (ver `rest_framework_tabulator
    .filters`). Parametrizado `[Any]` por el mismo motivo que
    `VentasPeriodosListView`.
    """

    serializer_class = DocumentoCompraSerializer
    pagination_class = TabulatorPagination
    filter_backends = [TabulatorFilterBackend]

    filterset_fields = {
        'tipo': 'tipo',
        'folio': 'folio',
        'contraparte': 'contraparte',
        'fecha': 'fecha',
        'total': 'total',
        'estado': 'estado',
    }
    ordering_fields = filterset_fields

    def get_queryset(self) -> Any:
        """
        Documentos de compra de `periodo` — requiere el parámetro.

        `periodo` es obligatorio (no un filtro opcional como
        `receptor_id`/`periodo` en `DteEmitidoListView`): sin él,
        `documentos_periodo()` no sabe qué período traer.
        """
        contribuyente = require_current_contribuyente(self.request)
        periodo = self.request.query_params.get('periodo')
        if not periodo:
            return []
        return purchases_service.documentos_periodo(
            contribuyente,
            int(periodo),
        )
