"""
Registro de `billing` en los seeders de `core` (comandos `seed`/`seed_demo`).

Importado por `core.apps.CoreConfig.ready()` vía
`autodiscover_modules('seeders')` — el `import` en sí ya registra, nada
de esto se llama a mano. Ver `apps/billing/platform.py` para el mismo
patrón, aplicado a menús/dashboard/perfil en vez de a datos.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import yaml
from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.core.management.color import color_style
from django.utils import timezone

from apps.billing.models import (
    AduanaClausulaVenta,
    AduanaFormaPago,
    AduanaModalidadVenta,
    AduanaMoneda,
    AduanaPuerto,
    AduanaTipoBulto,
    AduanaTransporte,
    AduanaUnidad,
    DteRecibido,
    DteRecibidoRcvEvento,
    FormaPago,
    ImpuestoAdicionalRetencion,
    Item,
    ItemCategoria,
    MedioPago,
    TipoDte,
    Traslado,
)
from apps.billing.services import (
    biller,
    caf_manager,
    document_receiver,
    example_provider,
    repository_provider,
)
from apps.core.registrations import Seeder
from apps.core.registry import register
from apps.libredte.models import (
    ActividadEconomica,
    Comuna,
    Contribuyente,
    ContribuyenteActividadEconomica,
    Sucursal,
)
from apps.libredte.services import certificate_manager
from apps.libredte.services.exceptions import ServiceError

_style = color_style()

DTES_RECIBIDOS_FIXTURE = (
    Path(__file__).resolve().parent / 'fixtures' / 'dte_recibidos.yaml'
)

DEMO_USERNAME = 'demo'
DEMO_PASSWORD = 'Slim123%'

# Catálogos con forma `(codigo, glosa)` idéntica — se cargan todos con
# el mismo bucle genérico (ver `seed()`), en vez de un bloque
# `bulk_create` repetido por cada uno.
_CATALOGOS_CODIGO_GLOSA = [
    (Traslado, repository_provider.load_traslados),
    (FormaPago, repository_provider.load_formas_pago),
    (AduanaFormaPago, repository_provider.load_aduana_formas_pago),
    (MedioPago, repository_provider.load_medios_pago),
    (AduanaTransporte, repository_provider.load_aduana_transportes),
    (AduanaModalidadVenta, repository_provider.load_aduana_modalidades_venta),
    (AduanaClausulaVenta, repository_provider.load_aduana_clausulas_venta),
    (AduanaUnidad, repository_provider.load_aduana_unidades),
    (AduanaPuerto, repository_provider.load_aduana_puertos),
    (AduanaTipoBulto, repository_provider.load_aduana_tipos_bulto),
]

# Los únicos tipos de DTE *electrónicos* — el catálogo de tipos de
# documento trae 68 en total (incluye papel/otros no electrónicos), y
# esta app solo emite estos. No hay un campo en el catálogo que
# distinga "electrónico": se filtra por código.
CODIGOS_DTE_ELECTRONICOS = [33, 34, 39, 41, 46, 52, 56, 61, 110, 111, 112]

_OPERACION_POR_CODIGO = {
    'S': TipoDte.Operacion.SUMA,
    'R': TipoDte.Operacion.RESTA,
}

# Debe cubrir el folio más alto entre los ejemplos de `document.examples`
# (`ExamplesWorker::list()`) — no es siempre "el siguiente" tras el
# último, hay casos con folio manual fuera de secuencia a propósito (ej.
# `033_018_folio_manual_asignado`, folio 123).
FOLIOS_POR_CAF_FICTICIO = 200

# Glosas reales del SII para el estado de un envío, tal como las arma
# `CheckXmlDocumentSentStatusResponse::getReviewStatus()` en
# `libredte-lib-core` (`Package/Billing/Component/Integration`) — no son
# texto propio de esta app. `ESTADO_ACEPTADO` está confirmado literal
# contra el SII real en
# `CheckXmlDocumentSentStatusTest::testUploadStatusEpr()`;
# `ESTADO_CON_REPAROS` es el literal que arma ese mismo método cuando el
# envío tiene reparos, aunque esa rama no tiene un test de integración
# real capturado.
ESTADO_ACEPTADO = 'EPR - Envio Procesado'
ESTADO_CON_REPAROS = 'RLV - DTE Aceptado con Reparos Leves'

# El único ejemplo del demo que queda con reparos — el resto, aceptado
# sin más (ver docstring de `seed_demo()`). Elegido porque el detalle
# que pidió el usuario ("IVA determinado no cuadra con MntNeto") calza
# temáticamente con este caso real de `example_provider`
# (`iva_anticipado`).
EJEMPLO_CON_REPAROS = '033_factura_afecta/033_003_iva_anticipado'
DETALLE_REPARO = 'IVA determinado no cuadra con MntNeto.'

# El certificado digital es de una persona natural (el mandatario que
# firma en representación de la empresa), no de la empresa misma — un
# `Contribuyente` no tiene RUT de persona natural para eso. Por eso el
# certificado ficticio se genera con un RUT propio, distinto al de
# `Contribuyente`.
MANDATARIO_RUT = '12345678-5'
MANDATARIO_NOMBRE = 'Juan Pérez'

# Actividad económica principal del contribuyente de demo — coincide con
# su giro ("Tecnología, Informática y Telecomunicaciones"); la otra
# actividad de `ACTIVIDADES_ECONOMICAS` (telecomunicaciones) queda
# asociada como secundaria.
ACTIVIDAD_ECONOMICA_PRINCIPAL = 620200

# Fecha de la resolución de autorización DTE del contribuyente demo —
# `autorizacion_dte_resolucion_numero` se deja en su default (`0` =
# certificación, ver `Contribuyente.ambiente`), pero la fecha siempre
# debe existir: la biblioteca la necesita para armar la carátula del
# sobre `EnvioDTE` (`document_dispatcher.send()`) — sin ella, ni siquiera lo
# arma. `0` no significa "sin resolución", es la convención real del
# SII para "Resolución N° 0" en certificación.
RESOLUCION_DTE_FECHA = date(2014, 8, 22)

# Un `(dias_atras, codigo_evento)` por estado de `DteRecibido.estado_rcv()`
# — ver `_marcar_estado_rcv()`. `dias_atras=None` deja el documento sin
# `fecha_registro_rcv` (estado_rcv() == None, "aún no se registra en el
# RCV"); `codigo_evento=None` deja el documento sin evento RCV (con solo
# `fecha_registro_rcv`, para probar la regla de los 8 días).
ESTADOS_RCV_DEMO = (
    (None, None),
    (3, None),
    (10, None),
    (5, DteRecibidoRcvEvento.Codigo.ERM),
    (6, DteRecibidoRcvEvento.Codigo.RCD),
)

# Catálogo de ítems del contribuyente demo — coherente con su giro
# ("Tecnología, Informática y Telecomunicaciones"), pero pensado sobre
# todo para que el listado muestre variedad real en cada campo de
# `Item` (no 10 filas con los mismos valores por defecto): distintos
# `codigo_tipo`, descripciones presentes/ausentes, descuento en % y en
# $, un ítem exento, uno con impuesto adicional, uno inactivo, uno con
# precio bruto (IVA incluido). El orden de las categorías es el orden
# en que se crean.
#
# `impuesto_adicional` va como el código del catálogo (int), resuelto
# a la instancia real en `_seed_items()` — el código 15 ("IVA
# retenido") es parte del catálogo SII que carga `seed()`, no algo
# propio de este contribuyente.
ITEMS_DEMO: dict[str, list[dict[str, Any]]] = {
    'Desarrollo de software': [
        {
            'codigo': 'DEV-001',
            'nombre': 'Desarrollo de aplicación web',
            'descripcion': (
                'Incluye diseño, desarrollo y despliegue en la nube.'
            ),
            'unidad': 'UN',
            'precio': 1500000,
        },
        {
            'codigo': 'DEV-002',
            'nombre': 'Desarrollo de aplicación móvil',
            'unidad': 'UN',
            'precio': 2000000,
            'descuento': 10,
            'descuento_tipo': Item.DescuentoTipo.PORCENTAJE,
        },
        {
            'codigo': 'DEV-003',
            'nombre': 'Consultoría en arquitectura de software',
            'descripcion': 'Tarifa por hora, facturada a honorarios.',
            'unidad': 'HR',
            'precio': 80000,
            'impuesto_adicional_codigo': 15,
        },
        {
            'codigo': 'DEV-004',
            'nombre': 'Integración de APIs',
            'codigo_tipo': 'EAN13',
            'unidad': 'UN',
            'precio': 450000,
            'activo': False,
        },
    ],
    'Soporte y mantención': [
        {
            'codigo': 'SOP-001',
            'nombre': 'Soporte técnico mensual',
            'descripcion': 'Mesa de ayuda ilimitada en horario hábil.',
            'unidad': 'MES',
            'precio': 150000,
        },
        {
            'codigo': 'SOP-002',
            'nombre': 'Mantención de servidores',
            'unidad': 'MES',
            'precio': 200000,
            'descuento': 20000,
            'descuento_tipo': Item.DescuentoTipo.MONTO,
        },
        {
            'codigo': 'SOP-003',
            'nombre': 'Capacitación de usuarios',
            'descripcion': 'Exenta de IVA por tratarse de capacitación.',
            'unidad': 'HR',
            'precio': 60000,
            'indicador_exencion': Item.IndicadorExencion.NO_AFECTO,
        },
    ],
    'Hardware y equipamiento': [
        {
            'codigo': 'HW-001',
            'nombre': 'Notebook empresarial',
            'descripcion': 'Incluye garantía de fábrica de 1 año.',
            'unidad': 'UN',
            'precio': 850000,
        },
        {
            'codigo': 'HW-002',
            'nombre': 'Monitor 24 pulgadas',
            'descripcion': 'Precio de lista del proveedor, IVA incluido.',
            'unidad': 'UN',
            'precio': 142800,
            'bruto': True,
            'descuento': 5,
            'descuento_tipo': Item.DescuentoTipo.PORCENTAJE,
        },
        {
            'codigo': 'HW-003',
            'nombre': 'Licencia Windows Server',
            'unidad': 'UN',
            'precio': 350000,
        },
    ],
}


def _operacion(operacion_repositorio: dict[str, Any] | None) -> str:
    """`TipoDte.Operacion` desde el nodo `operacion` del repositorio."""
    if operacion_repositorio is None:
        return ''
    return _OPERACION_POR_CODIGO[operacion_repositorio['codigo']]


def _categoria(categoria_repositorio: dict[str, Any]) -> TipoDte.Categoria:
    """`TipoDte.Categoria` desde el nodo `categoria` del repositorio."""
    if categoria_repositorio['codigo'] == 'T':
        return TipoDte.Categoria.TRIBUTARIO
    return TipoDte.Categoria.INFORMATIVO


def seed() -> None:
    """
    Carga los catálogos de la librería propios de facturación.

    Tipo de documento y los catálogos que usa el formulario de
    emisión: traslado, formas de pago, impuestos adicionales y los
    catálogos de Aduana para exportación. `libredte-lib-core` es la
    única fuente de verdad de tipo de documento — nada acá se
    reinterpreta ni se guarda distinto a como lo entrega el
    repositorio. Comuna/país/actividad económica los carga
    `apps.libredte.seeders.seed()` (corre antes, ver su `priority`) —
    esta función no los toca.
    """
    if TipoDte.objects.exists():
        print(
            _style.ERROR(
                'billing: ya hay tipos de DTE cargados, no se hizo nada.',
            ),
        )
        return

    tipos_dte = repository_provider.load_tipos_dte(CODIGOS_DTE_ELECTRONICOS)
    TipoDte.objects.bulk_create(
        TipoDte(
            codigo=tipo['codigo'],
            glosa=tipo['nombre'],
            glosa_corta=tipo['nombre_corto'],
            categoria=_categoria(tipo['categoria']),
            operacion=_operacion(tipo['operacion']),
            compra=bool(tipo['disponible_en_compras']),
            venta=bool(tipo['disponible_en_ventas']),
            cedible=tipo['es_cedible'],
        )
        for tipo in tipos_dte
    )

    total_catalogos_simples = 0
    for modelo, load in _CATALOGOS_CODIGO_GLOSA:
        items = load()
        # `modelo` es una unión de varios modelos concretos — el
        # plugin de mypy solo sintetiza `.objects` para un modelo
        # puntual, no para `type[Model]` genérico; en tiempo de
        # ejecución siempre es un modelo real registrado.
        cast(Any, modelo).objects.bulk_create(
            modelo(codigo=item['codigo'], glosa=item['glosa'])
            for item in items
        )
        total_catalogos_simples += len(items)

    impuestos = repository_provider.load_impuestos_adicionales()
    ImpuestoAdicionalRetencion.objects.bulk_create(
        ImpuestoAdicionalRetencion(
            codigo=impuesto['codigo'],
            tipo=impuesto['tipo'],
            glosa=impuesto['glosa'],
            tasa=impuesto['tasa'],
        )
        for impuesto in impuestos
    )

    monedas = repository_provider.load_aduana_monedas()
    AduanaMoneda.objects.bulk_create(
        AduanaMoneda(
            codigo=moneda['codigo'],
            glosa=moneda['glosa'],
            codigo_iso=moneda.get('codigo_iso', ''),
        )
        for moneda in monedas
    )

    print(
        _style.SUCCESS(
            f'billing: {len(tipos_dte)} tipos de DTE, '
            f'{total_catalogos_simples} ítems de catálogos de emisión, '
            f'{len(impuestos)} impuestos adicionales, {len(monedas)} '
            f'monedas.',
        ),
    )


def seed_demo() -> None:
    """
    Puebla un escenario de demostración completo para `billing`.

    **Todo lo que es dominio LibreDTE pasa por `services/*`, no se
    inventa acá**: los documentos de ejemplo son los ejemplos reales de
    `example_provider` (mismos casos que usa la suite de tests de
    `libredte-lib-core` — descuentos, impuesto adicional, exportación,
    etc., uno por caso disponible), y se timbran y firman de verdad
    (`biller.draft()` + `biller.bill_draft()` — el mismo camino de dos
    pasos que usará la emisión real) con un certificado/CAF ficticios.
    El XML que queda en `DteEmitido.xml_base64` es un XML real, y
    `neto`/`iva`/`total` son los que devuelve la API, no un cálculo
    hecho acá. El `Receptor` de cada documento también es el que trae
    el ejemplo (no una lista de clientes inventada): `biller.draft()`
    lo busca o crea a partir de esos mismos datos
    (`biller._resolver_receptor()`) — por eso, por ejemplo, casi todos
    los documentos domésticos terminan con el mismo receptor genérico
    (`Servicio de Impuestos Internos`, RUT usado en la mayoría de los
    ejemplos reales), y los de exportación con `Jackie Chan` (RUT/
    receptor fijo que usan esos ejemplos). Esto **requiere red**:
    `services.libredte_backend.get_backend()` necesita poder alcanzar la API de
    LibreDTE Lib configurada.

    Cada ejemplo también queda como `Borrador` de verdad (sin
    confirmar, vía `biller.draft()` de nuevo sobre el mismo
    `input_data`), con fecha del mes actual — para que
    `/billing/borradores` tenga datos reales sin armar uno a mano;
    a diferencia de los `DteEmitido`, estos no necesitan fechas
    repartidas en el pasado (un borrador no tiene periodo/dashboard).

    Lo único genuinamente propio de esta demostración (nada de esto lo
    hace `biller.draft()`/`bill_draft()`, ni lo hará la emisión real):
    las fechas repartidas en los últimos meses para que el dashboard se
    vea creíble, y el estado SII simulado (`track_id`/`revision_estado`/
    `revision_detalle`) — enviar de verdad al SII con un certificado
    ficticio siempre falla, así que ese flujo todavía no está cableado
    en la app.

    Corre dentro de la transacción que ya abrió el comando `seed_demo`
    de `core` (una sola, para todos los seeders de todas las apps): si
    algo falla acá, se revierte todo, no solo lo de `billing`.
    """
    try:
        _seed()
    except ServiceError as error:
        raise CommandError(
            f'billing: no se pudo completar: {error} No se creó nada — '
            f'reintenta el comando cuando se resuelva la causa.',
        ) from error

    print(
        _style.SUCCESS(
            f'billing: listo. Inicia sesión con "{DEMO_USERNAME}" / '
            f'"{DEMO_PASSWORD}".',
        ),
    )


def _seed() -> None:
    """Arma todo el escenario de demostración, o nada (ver `seed_demo()`)."""
    usuario = User.objects.create_user(
        DEMO_USERNAME,
        password=DEMO_PASSWORD,
        is_staff=True,
        is_superuser=True,
    )

    santa_cruz = Comuna.objects.get(codigo='SANTA CRUZ')

    contribuyente = Contribuyente.objects.create(
        usuario=usuario,
        rut=76192083,
        dv='9',
        razon_social='SASCO SpA',
        giro='Tecnología, Informática y Telecomunicaciones',
        direccion='DBG191',
        comuna=santa_cruz,
        autorizacion_dte_resolucion_fecha=RESOLUCION_DTE_FECHA,
    )

    Sucursal.objects.create(
        contribuyente=contribuyente,
        es_matriz=True,
        nombre='Casa matriz',
        direccion=contribuyente.direccion,
        comuna=santa_cruz,
    )

    for actividad in ActividadEconomica.objects.all():
        ContribuyenteActividadEconomica.objects.create(
            contribuyente=contribuyente,
            actividad_economica=actividad,
            es_principal=(actividad.codigo == ACTIVIDAD_ECONOMICA_PRINCIPAL),
        )

    _seed_items(contribuyente)

    tipos_dte = {tipo.codigo: tipo for tipo in TipoDte.objects.all()}

    certificate = certificate_manager.create_fake_certificate(
        MANDATARIO_RUT,
        MANDATARIO_NOMBRE,
        'demo@sasco.example',
    )
    contribuyente.certificado = certificate_manager.save_certificate(
        usuario,
        certificate,
    )
    contribuyente.save()

    for tipo_dte in tipos_dte.values():
        caf = caf_manager.create_fake_caf(
            contribuyente,
            tipo_dte,
            folio_desde=1,
            folio_hasta=FOLIOS_POR_CAF_FICTICIO,
        )
        caf_manager.register_caf(contribuyente, tipo_dte, caf)

    # Todos los ejemplos disponibles para los tipos de DTE que soporta
    # esta app (ver `CODIGOS_DTE_ELECTRONICOS`) — orden tal cual lo
    # entrega la API (`ExamplesWorker::list()` en libredte-lib-core):
    # ya garantiza que cada ejemplo aparece después de los ejemplos de
    # los que depende (`Test.DependsOn`, ej. una Nota de Crédito
    # después de la Factura que anula), no hay que reordenar nada acá.
    ejemplos = [
        resumen
        for resumen in example_provider.list_examples()
        if int(resumen.category[:3]) in tipos_dte
    ]

    hoy = timezone.localdate()
    total_ejemplos = len(ejemplos)
    for indice, resumen in enumerate(ejemplos):
        ejemplo = example_provider.get_example(resumen.id)
        tipo_dte = tipos_dte[int(resumen.category[:3])]

        input_data = ejemplo.example
        # El folio real del ejemplo se reserva tal cual (`caf_manager
        # .reserve_folio()`, vía `bill_draft(folio=)`) — no "el
        # siguiente" del CAF: las referencias entre ejemplos
        # (`Referencia.FolioRef` en el YAML de origen) apuntan a este
        # folio exacto, y sin reproducirlo tal cual
        # `_resolver_referencias()` nunca las resolvería.
        folio = input_data['Encabezado']['IdDoc']['Folio']

        documento = biller.bill_draft(
            biller.draft(contribuyente, tipo_dte, input_data, usuario),
            folio=folio,
        )

        # Fechas repartidas en los últimos meses (documentos más
        # antiguos primero, según el orden estable de arriba) — solo
        # para que el listado se vea creíble, no representa nada del
        # ejemplo real en sí. Ni esto ni el estado SII simulado de
        # abajo los pone `biller.draft()`/`bill_draft()` — son
        # enteramente cosa de esta demostración (ver docstring de
        # `seed_demo()`).
        meses_atras = round(
            (total_ejemplos - 1 - indice) * 5 / max(total_ejemplos - 1, 1),
        )
        fecha = _hace_meses(hoy, meses_atras)
        con_reparos = resumen.id == EJEMPLO_CON_REPAROS

        documento.fecha = fecha
        documento.periodo = fecha.year * 100 + fecha.month
        documento.track_id = int(f'{tipo_dte.codigo}{documento.folio:06d}')
        documento.revision_estado = (
            ESTADO_CON_REPAROS if con_reparos else ESTADO_ACEPTADO
        )
        documento.revision_detalle = DETALLE_REPARO if con_reparos else ''
        documento.save()

        # El mismo ejemplo, además, como `Borrador` de verdad (sin
        # confirmar) con fecha del mes actual — `draft()` de nuevo
        # sobre el mismo `input_data` (`bill_draft()` de arriba no lo
        # mutó: opera sobre los datos normalizados que devuelve la
        # API, no sobre este dict). En folio 0: `draft()` no decide
        # eso por su cuenta (no altera datos de entrada), así que es
        # esta demostración quien lo deja explícito — un borrador de
        # verdad, a diferencia del que ya se confirmó arriba, todavía
        # no tiene folio.
        input_data['Encabezado']['IdDoc']['Folio'] = 0
        borrador = biller.draft(contribuyente, tipo_dte, input_data, usuario)
        dia = 1 + round((hoy.day - 1) * indice / max(total_ejemplos - 1, 1))
        borrador.fecha = hoy.replace(day=dia)
        borrador.save()

    _seed_dtes_recibidos(contribuyente, usuario)


def _hace_meses(fecha: date, meses: int) -> date:
    """Misma fecha, `meses` atrás (día recortado a 28 — evita fin de mes)."""
    total = fecha.year * 12 + (fecha.month - 1) - meses
    anio, mes = divmod(total, 12)
    return date(anio, mes + 1, min(fecha.day, 28))


def _seed_items(contribuyente: Contribuyente) -> None:
    """
    Puebla el catálogo de ítems del contribuyente activo.

    Puramente datos locales (`Item`/`ItemCategoria` no llaman a la
    API) — a diferencia de los ejemplos/DTE recibidos, no hay nada que
    timbrar ni firmar acá. Cada entrada de `ITEMS_DEMO` solo trae las
    llaves que se apartan de los defaults del modelo —
    `impuesto_adicional_codigo` es la única que no es un campo de
    `Item` directo, se resuelve acá a la instancia real.
    """
    for nombre_categoria, items in ITEMS_DEMO.items():
        categoria = ItemCategoria.objects.create(
            contribuyente=contribuyente,
            nombre=nombre_categoria,
        )
        for datos_originales in items:
            datos = dict(datos_originales)
            impuesto_codigo = datos.pop('impuesto_adicional_codigo', None)
            impuesto_adicional = None
            if impuesto_codigo is not None:
                impuesto_adicional = ImpuestoAdicionalRetencion.objects.get(
                    codigo=impuesto_codigo,
                )
            Item.objects.create(
                contribuyente=contribuyente,
                categoria=categoria,
                impuesto_adicional=impuesto_adicional,
                **datos,
            )


def _seed_dtes_recibidos(contribuyente: Contribuyente, usuario: User) -> None:
    """
    Puebla `DteRecibido` a partir de `fixtures/dte_recibidos.yaml`.

    Todos los documentos de un mismo `proveedor` se arman, timbran y
    firman con un CAF y un certificado ficticios de ese proveedor —
    nada de eso se persiste — y se envuelven JUNTOS en un único sobre
    `EnvioDTE` real vía `document_receiver.build_fake_sobre()`
    (`create_many()`), luego procesado con `document_receiver.load_xml()`:
    el mismo camino que
    seguiría un sobre recibido de verdad, no uno armado a mano para el
    demo — incluye el caso de un sobre con 2+ documentos, ya que cada
    proveedor del fixture tiene más de uno. Los eventos RCV sí son
    enteramente cosa de esta demostración (`load_xml()` nunca los
    pone — eso lo haría una sincronización real con el RCV, que
    todavía no existe): `_marcar_estado_rcv()` reparte los 5
    documentos del fixture entre los 5 estados posibles de
    `DteRecibido.estado_rcv()`.
    """
    escenarios = yaml.safe_load(DTES_RECIBIDOS_FIXTURE.read_text())
    receptor = {
        'RUTRecep': f'{contribuyente.rut}-{contribuyente.dv}',
        'RznSocRecep': contribuyente.razon_social,
        'GiroRecep': contribuyente.giro,
        'DirRecep': contribuyente.direccion,
        'CmnaRecep': contribuyente.comuna.glosa,
    }

    indice = 0
    for proveedor in escenarios['proveedores']:
        certificate = certificate_manager.create_fake_certificate(
            proveedor['rut'],
            proveedor['razon_social'],
            'contacto@proveedor.example',
        )
        cafs_por_tipo_dte = {}
        documentos_data = []

        for documento in proveedor['documentos']:
            tipo_dte = TipoDte.objects.get(codigo=documento['tipo_dte'])
            if tipo_dte.codigo not in cafs_por_tipo_dte:
                cafs_por_tipo_dte[tipo_dte.codigo] = (
                    caf_manager.create_fake_caf_for(
                        proveedor['rut'],
                        proveedor['razon_social'],
                        tipo_dte,
                        folio_desde=1,
                        folio_hasta=9999,
                    )
                )

            document_data = {
                'Encabezado': {
                    'IdDoc': {
                        'TipoDTE': tipo_dte.codigo,
                        'Folio': documento['folio'],
                    },
                    'Emisor': {
                        'RUTEmisor': proveedor['rut'],
                        'RznSoc': proveedor['razon_social'],
                        'GiroEmis': proveedor['giro'],
                        'DirOrigen': proveedor['direccion'],
                        'CmnaOrigen': proveedor['comuna'],
                    },
                    'Receptor': receptor,
                },
                'Detalle': documento['detalle'],
            }
            caf = cafs_por_tipo_dte[tipo_dte.codigo]
            documentos_data.append((document_data, caf.xml_base64))

        sobre_xml_base64 = document_receiver.build_fake_sobre(
            documentos_data,
            autorizacion_dte_resolucion_fecha=date.fromisoformat(
                proveedor['autorizacion_dte']['fecha_resolucion'],
            ),
            autorizacion_dte_resolucion_numero=(
                proveedor['autorizacion_dte']['numero_resolucion']
            ),
            certificate=certificate,
        )

        for dte_recibido in document_receiver.load_xml(
            contribuyente,
            sobre_xml_base64,
            usuario,
        ):
            _marcar_estado_rcv(dte_recibido, indice)
            indice += 1


def _marcar_estado_rcv(dte_recibido: DteRecibido, indice: int) -> None:
    """
    Reparte 5 documentos entre los 5 estados de `estado_rcv()`.

    `indice % 5` cae en uno de `ESTADOS_RCV_DEMO`: sin `fecha_
    registro_rcv` (estado `None`), pendiente (dentro de los 8 días),
    recibido automáticamente (fuera de los 8 días, sin eventos), con
    acuse de recibo (evento ERM), rechazado (evento RCD) — ver
    docstring de `DteRecibido.estado_rcv()`.
    """
    dias_atras, codigo_evento = ESTADOS_RCV_DEMO[
        indice % len(ESTADOS_RCV_DEMO)
    ]
    if dias_atras is None:
        return

    dte_recibido.fecha_registro_rcv = timezone.now() - timedelta(
        days=dias_atras,
    )
    dte_recibido.save(update_fields=['fecha_registro_rcv'])

    if codigo_evento is not None:
        contribuyente = dte_recibido.contribuyente
        DteRecibidoRcvEvento.objects.create(
            dte_recibido=dte_recibido,
            codigo=codigo_evento,
            responsable=f'{contribuyente.rut}-{contribuyente.dv}',
            fecha=dte_recibido.fecha_registro_rcv,
        )


register('seed', Seeder(label='Catálogos SII', run=seed, priority=10))
register(
    'seed_demo',
    Seeder(label='Datos de demostración', run=seed_demo, priority=10),
)
