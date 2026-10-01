"""Contratos de las capabilities que `libredte` provee para sus plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from libredte_lib_sdk import LibreDTE

from apps.core.plugin.base import BasePluginCapability

if TYPE_CHECKING:
    from ..models import Contribuyente


class LibredteBackend(LibreDTE):
    """El backend que arma un plugin de la capability `libredte.backend`."""


class LibredteBackendPluginCapabilityDefinition(BasePluginCapability, ABC):
    """
    Reemplaza `apps/libredte/services/libredte_backend.py::get_backend()`.

    El resto del SDK (`backend.billing.document.builder`, etc.) sigue
    siendo el mismo — lo único que un plugin de esta capability puede
    cambiar es cómo se construye el backend raíz, nunca su jerarquía
    interna.
    """

    id: ClassVar[str] = 'libredte.backend'
    label: ClassVar[str] = 'Backend de LibreDTE'
    description: ClassVar[str] = (
        'Provee el backend que LibreDTE Slim necesita para funcionar.'
    )

    @abstractmethod
    def get_backend(self) -> LibredteBackend:
        """Un `LibredteBackend` listo."""


class SiiBackendError(Exception):
    """`sii.backend` no pudo completar la operación contra el SII."""


class SiiBackendAuthError(SiiBackendError):
    """`sii.backend` intentó una operación sin la credencial que necesita."""


class SiiBackend(ABC):
    """
    Contrato de operaciones de `sii.backend` — sin lógica propia.

    Agnóstico a `apigatewaycl`: declara qué operaciones existen, nunca
    cómo se resuelven. Un método abstracto por operación, agregados de
    a uno a medida que se necesitan — no existen todos los recursos de
    la API, solo los que LibreDTE Slim usa de verdad.

    Cada operación exige un tipo de credencial del contribuyente
    distinto (RUT/clave o certificado digital), indicado entre
    paréntesis en su resumen — quien la llama sin tenerla configurada
    recibe `SiiBackendAuthError`. Ninguna expone `certificacion` como
    parámetro: el ambiente SII (producción/certificación) es fijo por
    `Contribuyente` (`Contribuyente.ambiente`), no algo que decida cada
    llamada.

    Todos los ejemplos de este archivo usan datos ficticios, salvo el
    RUT/razón social de SASCO SpA (`76192083-9`), la única cuenta real
    con la que se validó cada método en vivo — cualquier otro RUT,
    nombre, correo, folio o monto que aparezca abajo es inventado.
    """

    @abstractmethod
    def sii_contribuyentes_situacion_tributaria(
        self, rut: str
    ) -> dict[str, Any]:
        """
        Situación tributaria pública de `rut` (sin credencial).

        Sirve para cualquier RUT, no solo el propio — es el recurso
        pensado para autocompletar un Receptor al emitir.

        Uso::

            backend.sii_contribuyentes_situacion_tributaria('76192083-9')

        Respuesta (ejemplo)::

            {
              "data": {
                "razon_social": "SASCO SPA",
                "pro_pyme": true,
                "moneda_extranjera": false,
                "obligacion_dte": true,
                "actividades": [
                  {"codigo": "620200", "glosa": "PROGRAMACION",
                   "categoria": 1, "afecta": true, "fecha": "2012-06-08"}
                ],
                "documentos_timbrados": [
                  {"documento": "Factura Electronica", "codigo": 33}
                ],
                "observaciones": {
                  "no_habido": false, "termino_giro": false, "...": "..."
                }
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_actividades_economicas_listado(
        self, categoria: int | None = None
    ) -> dict[str, Any]:
        """
        Catálogo de actividades económicas (sin credencial).

        `categoria`: `1` (primera categoría) o `2` (segunda categoría),
        opcional — sin filtro trae ambas.

        Uso::

            backend.sii_actividades_economicas_listado(categoria=1)

        Respuesta (ejemplo, agrupada por rubro y giro)::

            {
              "data": {
                "Actividades de programacion informatica": {
                  "Programacion informatica": [
                    {"codigo": "620200",
                     "actividad_economica": "Programacion informatica",
                     "afecta_iva": true, "categoria": 1,
                     "internet": true}
                  ]
                }
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_dte_contribuyentes_datos(self) -> dict[str, Any]:
        """
        Datos privados del contribuyente (`auth.cert` o `auth.pass`).

        Resolución de autorización, correos y software de facturación
        declarados ante el SII.

        Uso::

            backend.sii_dte_contribuyentes_datos()

        Respuesta (ejemplo)::

            {
              "data": {
                "rut": "76192083-9",
                "razon_social": "SASCO SPA",
                "resolucion": {"numero": 80, "fecha": "2014-08-22"},
                "emails": {
                  "administrador": "admin@example.com",
                  "sii": "sii@example.com",
                  "intercambio": "intercambio@example.com"
                },
                "software": {"nombre": "MI SOFTWARE", "url": "example.com"}
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_dte_contribuyentes_autorizacion(self, rut: str) -> dict[str, Any]:
        """
        Estado de autorización DTE de `rut` (sin credencial).

        Sirve para cualquier RUT, no solo el propio.

        Uso::

            backend.sii_dte_contribuyentes_autorizacion('76192083-9')

        Respuesta (ejemplo, truncada)::

            {
              "data": {
                "rut": "76192083-9",
                "autorizado": true,
                "razon_social": "SASCO SPA",
                "direccion_regional": "VI",
                "documentos": [
                  {"codigo": 33, "descripcion": "FACTURA ELECTRONICA",
                   "autorizado": "2015-09-01", "desautorizado": null}
                ]
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_dte_contribuyentes_autorizacion_certificado(
        self,
    ) -> dict[str, Any]:
        """
        Estado de autorización DTE, con email de intercambio (`cert`).

        Mismo contenido que `sii_dte_contribuyentes_autorizacion()`
        para el propio contribuyente, más `emails.intercambio` — solo
        disponible con certificado.

        Uso::

            backend.sii_dte_contribuyentes_autorizacion_certificado()

        Respuesta (ejemplo, truncada)::

            {
              "data": {
                "rut": "76192083-9",
                "autorizado": true,
                "razon_social": "SASCO SPA",
                "emails": {"intercambio": "intercambio@example.com"},
                "documentos": ["..."]
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_dte_contribuyentes_autorizados(
        self,
        dia: str | None = None,
        formato: str | None = None,
    ) -> dict[str, Any] | bytes:
        """
        Descarga masiva de contribuyentes DTE-habilitados (`cert`).

        ⚠️ Descarga la base completa del SII (~1 millón de registros,
        cientos de MB, hasta 15 min — en la práctica ~4 min en la
        prueba real). `formato=None` (por defecto) trae el CSV oficial
        del SII sin transformar → devuelve `bytes`. Con
        `formato='json'` devuelve un `dict` ya decodificado (más lento
        de generar del lado de la API).

        Uso::

            backend.sii_dte_contribuyentes_autorizados()  # bytes (CSV)
            backend.sii_dte_contribuyentes_autorizados(
                formato='json'
            )  # dict

        Respuesta con `formato='json'` (ejemplo, un registro)::

            {
              "data": [
                {"rut": "76192083-9", "razon_social": "SASCO SPA",
                 "resolucion_numero": "80", "email": "dte@example.com"}
              ],
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_rcv_compras_resumen(
        self, periodo: str, estado: str = 'REGISTRO'
    ) -> dict[str, Any]:
        """
        Resumen del Registro de Compras del período (`auth.pass`).

        `periodo` en formato `AAAAMM`. `estado`: `'REGISTRO'`
        (default), `'PENDIENTE'`, `'NO_INCLUIR'` o `'RECLAMADO'`.

        Uso::

            backend.sii_rcv_compras_resumen('202609')

        Respuesta (ejemplo, un tipo de documento)::

            {
              "data": {
                "respEstado": {"codRespuesta": 0, "msgeRespuesta": null},
                "data": [
                  {"rsmnTipoDocInteger": 33,
                   "dcvNombreTipoDoc": "Factura Electronica",
                   "rsmnMntNeto": 100000, "rsmnMntIVA": 19000,
                   "rsmnMntTotal": 119000, "rsmnTotDoc": 1}
                ]
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_rcv_compras_detalle(
        self,
        periodo: str,
        dte: int = 0,
        estado: str = 'REGISTRO',
        tipo: str | None = None,
    ) -> dict[str, Any]:
        """
        Detalle del Registro de Compras del período (`auth.pass`).

        `dte=0` trae todos los tipos de documento. Cada elemento de
        `data.data` es un documento, con ~50 campos `det*` (rut/folio
        del emisor, montos, fechas de recepción/acuse/reclamo,
        `detTipoTransaccion` vigente, etc. — el detalle completo solo
        se entiende leyendo un caso real, no vale la pena listarlo
        acá).

        Uso::

            backend.sii_rcv_compras_detalle('202609', dte=33)

        Respuesta (ejemplo, un documento, campos más usados)::

            {
              "data": {
                "respEstado": {"codRespuesta": 0},
                "data": [
                  {"detTipoDoc": 33, "detRutDoc": 11111111, "detDvDoc": "1",
                   "detRznSoc": "PROVEEDOR EJEMPLO SPA", "detNroDoc": 100,
                   "detMntNeto": 100000, "detMntIVA": 19000,
                   "detMntTotal": 119000, "detTipoTransaccion": 1,
                   "descTipoTransaccion": "Del Giro",
                   "cambiarTipoTran": true}
                ]
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_rcv_compras_async_solicitar(
        self, periodo: str, dte: int = 0, estado: str = 'REGISTRO'
    ) -> dict[str, Any]:
        """
        Solicita el detalle asíncrono de compras del período (`pass`).

        Para volúmenes grandes: solicitar → sondear
        `sii_rcv_compras_async_estado()` hasta `estado == 'TERMINADO'`
        → `sii_rcv_compras_async_detalle()`. En la práctica, para un
        período normal termina en segundos.

        Uso::

            r = backend.sii_rcv_compras_async_solicitar('202609', dte=33)
            id_solicitud = str(r['data']['id'])

        Respuesta (ejemplo)::

            {
              "data": {"id": 123456789, "uuid": "...", "dte": 33,
                       "estado": "CREADO", "creada": "24/09/2026 00:00:00",
                       "terminada": null, "seccion": "REGISTRO",
                       "registros": 0},
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_rcv_compras_async_estado(
        self,
        periodo: str,
        id_solicitud: str,
        dte: int = 0,
        estado: str = 'REGISTRO',
    ) -> dict[str, Any]:
        """
        Estado de una solicitud asíncrona de compras (`auth.pass`).

        Mismo `id_solicitud` que devolvió
        `sii_rcv_compras_async_solicitar()`. Sondear hasta
        `data.estado == 'TERMINADO'`.

        Uso::

            backend.sii_rcv_compras_async_estado(
                '202609', '123456789', dte=33
            )

        Respuesta (ejemplo, ya terminada)::

            {
              "data": {"id": 123456789, "estado": "TERMINADO",
                       "terminada": "24/09/2026 00:00:15",
                       "registros": 23},
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_rcv_compras_async_detalle(
        self,
        periodo: str,
        id_solicitud: str,
        dte: int = 0,
        estado: str = 'REGISTRO',
    ) -> dict[str, Any]:
        """
        Detalle de una solicitud asíncrona de compras ya lista (`pass`).

        Solo tiene datos una vez que `sii_rcv_compras_async_estado()`
        reporta `'TERMINADO'`. Misma forma de respuesta que
        `sii_rcv_compras_detalle()` (lista de documentos `det*`).

        Uso::

            backend.sii_rcv_compras_async_detalle(
                '202609', '123456789', dte=33
            )
        """

    @abstractmethod
    def sii_rcv_ventas_resumen(self, periodo: str) -> dict[str, Any]:
        """
        Resumen del Registro de Ventas del período (`auth.pass`).

        Mismo patrón que `sii_rcv_compras_resumen()`, del lado de
        ventas — `periodo` en formato `AAAAMM`.

        Uso::

            backend.sii_rcv_ventas_resumen('202609')

        Respuesta (ejemplo, un tipo de documento)::

            {
              "data": {
                "respEstado": {"codRespuesta": 0},
                "data": [
                  {"rsmnTipoDocInteger": 33,
                   "dcvNombreTipoDoc": "Factura Electronica",
                   "rsmnMntNeto": 500000, "rsmnMntIVA": 95000,
                   "rsmnMntTotal": 595000, "rsmnTotDoc": 5}
                ]
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_rcv_ventas_detalle(
        self, periodo: str, dte: int = 0, tipo: str | None = None
    ) -> dict[str, Any]:
        """
        Detalle del Registro de Ventas del período (`auth.pass`).

        Mismo patrón que `sii_rcv_compras_detalle()`, del lado de
        ventas (documentos con RUT/nombre del receptor en vez del
        emisor, montos, `indicador_servicio`, etc.).

        Uso::

            backend.sii_rcv_ventas_detalle('202609', dte=33)
        """

    @abstractmethod
    def sii_rcv_ventas_async_solicitar(
        self, periodo: str, dte: int = 0
    ) -> dict[str, Any]:
        """
        Solicita el detalle asíncrono de ventas del período (`pass`).

        Mismo patrón que `sii_rcv_compras_async_solicitar()`, del lado
        de ventas.

        Uso::

            backend.sii_rcv_ventas_async_solicitar('202609', dte=33)
        """

    @abstractmethod
    def sii_rcv_ventas_async_estado(
        self, periodo: str, id_solicitud: str, dte: int = 0
    ) -> dict[str, Any]:
        """
        Estado de una solicitud asíncrona de ventas (`auth.pass`).

        Mismo patrón que `sii_rcv_compras_async_estado()`, del lado de
        ventas.

        Uso::

            backend.sii_rcv_ventas_async_estado(
                '202609', '123456789', dte=33
            )
        """

    @abstractmethod
    def sii_rcv_ventas_async_detalle(
        self, periodo: str, id_solicitud: str, dte: int = 0
    ) -> dict[str, Any]:
        """
        Detalle de una solicitud asíncrona de ventas ya lista (`pass`).

        Mismo patrón que `sii_rcv_compras_async_detalle()`, del lado
        de ventas.

        Uso::

            backend.sii_rcv_ventas_async_detalle(
                '202609', '123456789', dte=33
            )
        """

    @abstractmethod
    def sii_caf_estado_timbraje(self, dte: int) -> dict[str, Any]:
        """
        Folios timbrables y observaciones del SII (`auth.cert`).

        Solo consulta — nunca solicita folios. `dte`: código de tipo
        de documento (33 factura, 39 boleta, etc.).

        Uso::

            backend.sii_caf_estado_timbraje(39)

        Respuesta (ejemplo)::

            {
              "data": {
                "dte": {"codigo": 39, "limitado": false,
                        "maximo_autorizado": null,
                        "folios_disponibles": null,
                        "timbraje_permitido": null},
                "contribuyente": {"observado": false, "glosa": null,
                                  "observaciones": []}
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_caf_xml(
        self,
        dte: int,
        folio_inicial: int,
        folio_final: int,
        fecha_autorizacion: str,
    ) -> bytes:
        """
        XML de un CAF ya autorizado (`auth.cert`).

        `fecha_autorizacion` en formato `AAAA-MM-DD`. El rango de
        folios y la fecha deben corresponder a un CAF real ya
        solicitado — se obtienen de `sii_caf_solicitudes()`.

        Uso::

            backend.sii_caf_xml(39, 100, 109, '2026-09-24')

        Respuesta: `bytes` con el XML `<AUTORIZACION><CAF>...`
        (incluye la llave privada del CAF — nunca loguear ni exponer
        esta respuesta tal cual).
        """

    @abstractmethod
    def sii_caf_estado(
        self,
        dte: int,
        folio: int,
        formato: str | None = None,
    ) -> dict[str, Any]:
        """
        Estado de un folio ante el SII (`auth.cert`).

        Uso::

            backend.sii_caf_estado(39, 100)

        Respuesta (ejemplo)::

            {
              "data": {"estado": "recibido",
                       "estado_glosa": "Documento recibido por el SII",
                       "track_id": "00000000000"},
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_caf_solicitudes(
        self,
        dte: int,
        pagina: int,
        formato: str | None = None,
    ) -> dict[str, Any]:
        """
        Listado paginado de solicitudes de CAF (`auth.cert`).

        `pagina` parte en `1` — usar `metadata.siguiente_pagina` de la
        respuesta (`null` si es la última) para paginar. Útil para
        descubrir rangos de folios reales antes de llamar
        `sii_caf_xml()`/`sii_caf_estado()`.

        Uso::

            backend.sii_caf_solicitudes(39, 1)

        Respuesta (ejemplo, una solicitud)::

            {
              "data": [
                {"inicial": 100, "final": 109, "cantidad": 10,
                 "fecha": "2026-09-24",
                 "mandatario": "NOMBRE DEL MANDATARIO"}
              ],
              "metadata": {"siguiente_pagina": null, "timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_caf_estados(
        self, dte: int, folio_inicial: int, folio_final: int, estado: str
    ) -> dict[str, Any]:
        """
        Estados de un rango de folios, agrupados por tramos (`cert`).

        `estado` es plural y exacto — `'recibidos'`, `'anulados'` o
        `'pendientes'` (`'recibido'` en singular falla con
        `ApiException`, confirmado en vivo).

        Uso::

            backend.sii_caf_estados(39, 100, 109, 'recibidos')

        Respuesta (ejemplo, agrupado en un solo tramo)::

            {
              "data": [{"inicial": 100, "final": 109, "cantidad": 10}],
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_dte_contribuyentes_usuarios(self) -> dict[str, Any]:
        """
        Usuarios autorizados ante el SII para DTE (`auth.cert`).

        Uso::

            backend.sii_dte_contribuyentes_usuarios()

        Respuesta (ejemplo, un usuario)::

            {
              "data": [
                {"run": "11111111-1", "nombre": "JUAN PEREZ EJEMPLO",
                 "permisos": {"administrador": true,
                              "solicitar_folios": true,
                              "anular_folios": true, "firmar": true,
                              "enviar": true, "consultar": true}}
              ],
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_dte_contribuyentes_set_datos(
        self, datos: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Actualiza software/emails declarados ante el SII (`auth.cert`).

        `datos` lleva `emails` (`administrador`/`sii`/`intercambio`) y
        `software` (`nombre`/`url`) — los campos que no se envíen
        quedan en blanco, no se conserva lo anterior; mandar siempre
        el objeto completo (leído antes con
        `sii_dte_contribuyentes_datos()`, no solo el campo a cambiar).

        Uso::

            datos = {
                'emails': {'administrador': 'admin@example.com',
                           'sii': 'sii@example.com',
                           'intercambio': 'intercambio@example.com'},
                'software': {'nombre': 'MI SOFTWARE',
                             'url': 'example.com'},
            }
            backend.sii_dte_contribuyentes_set_datos(datos)

        Respuesta (ejemplo)::

            {
              "data": {
                "rut": "76192083-9", "razon_social": "SASCO SPA",
                "emails": {"administrador": "admin@example.com"},
                "software": {"nombre": "MI SOFTWARE"}
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_dte_contribuyentes_set_usuario(
        self, usuario: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Asigna/actualiza permisos de un usuario (`auth.cert`).

        `usuario` lleva `run` y `permisos` (`administrador`,
        `solicitar_folios`, `anular_folios`, `firmar`, `enviar`,
        `consultar`, todos booleanos). No existe un recurso separado
        para "eliminar" un usuario — dejar los 6 permisos en `false`
        lo elimina de verdad de `sii_dte_contribuyentes_usuarios()`
        (no queda con permisos vacíos, desaparece de la lista;
        confirmado en vivo).

        La respuesta es la **lista completa** de usuarios vigentes
        (misma forma que `sii_dte_contribuyentes_usuarios()`), no solo
        el usuario recién actualizado — así siempre se ve el estado
        final real, no una vista parcial de lo que acaba de cambiar.

        Uso::

            usuario = {
                'run': '11111111-1',
                'permisos': {
                    'administrador': False, 'solicitar_folios': False,
                    'anular_folios': False, 'firmar': False,
                    'enviar': False, 'consultar': True,
                },
            }
            backend.sii_dte_contribuyentes_set_usuario(usuario)

        Respuesta (ejemplo, lista completa tras el cambio)::

            {
              "data": [
                {"run": "11111111-1", "nombre": "JUAN PEREZ EJEMPLO",
                 "permisos": {"administrador": false,
                              "solicitar_folios": false,
                              "anular_folios": false, "firmar": false,
                              "enviar": false, "consultar": true}}
              ],
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_rcv_compras_set_tipo_transaccion(
        self, periodo: str, documento: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Asigna tipo de transacción a una compra del RCV (`auth.pass`).

        Un solo `documento` por llamada — debe estar de verdad en el
        Registro de Compras del período (usar
        `sii_rcv_compras_detalle()` para encontrarlo). Lleva `emisor`,
        `dte` (33, 34, 43, 46, 56 o 61), `folio`, `tipo_transaccion`
        (1 a 7) y `codigo_iva` (el permitido según
        `tipo_transaccion` — ver la spec para la tabla completa de
        combinaciones válidas).

        Uso::

            documento = {
                'emisor': '11111111-1', 'dte': 33, 'folio': 100,
                'tipo_transaccion': 1, 'codigo_iva': 1,
            }
            backend.sii_rcv_compras_set_tipo_transaccion(
                '202609', documento
            )

        Respuesta (ejemplo, éxito)::

            {
              "data": {
                "codigo": 0,
                "mensaje": "Carga de cambios de tipo de compra "
                           "realizada satisfactoriamente",
                "estado": "ok", "reparos": [], "errores": []
              },
              "metadata": {"timestamp": "..."}
            }
        """

    @abstractmethod
    def sii_caf_solicitar(self, dte: int, cantidad: int) -> bytes:
        """
        Solicita folios NUEVOS al SII — timbraje real (`auth.cert`).

        ⚠️ Consume folios de verdad de la numeración del contribuyente
        (aunque sea en ambiente de certificación) — no es una
        simulación. Usar `sii_caf_anular()` después si el rango
        solicitado fue solo de prueba.

        Uso::

            xml_bytes = backend.sii_caf_solicitar(dte=39, cantidad=10)

        Respuesta: `bytes` con el XML `<AUTORIZACION><CAF>...` del CAF
        recién autorizado (mismo formato que `sii_caf_xml()`, incluye
        la llave privada — no loguear ni exponer tal cual). El rango
        de folios asignado viene en `<CAF><DA><RNG><D>`/`<H>`.
        """

    @abstractmethod
    def sii_caf_anular(
        self,
        dte: int,
        folio_inicial: int,
        folio_final: int,
        formato: str | None = None,
    ) -> dict[str, Any]:
        """
        Anula un rango de folios ya solicitados (`auth.cert`).

        ⚠️ Irreversible en el SII — una vez anulado, un folio no se
        puede volver a habilitar.

        Uso::

            backend.sii_caf_anular(
                dte=39, folio_inicial=100, folio_final=109
            )

        Respuesta (ejemplo)::

            {
              "data": {
                "emisor": "76192083-9", "fecha_anulacion": "2026-09-24",
                "dte": 39, "folio_inicial": 100, "folio_final": 109,
                "usuario": "11111111-1"
              },
              "metadata": {"timestamp": "..."}
            }
        """


class SiiBackendPluginCapabilityDefinition(BasePluginCapability, ABC):
    """
    Backend único para las operaciones contra el SII vía apigateway.cl.

    Agrupa lo que hoy serían 5 capabilities separadas (búsqueda de
    contribuyente, perfil SII, contribuyentes autorizados, RCV, CAF) en
    una sola: hoy existe un único implementador (`apigatewaycl`), y esa
    librería en sí ya expone sus recursos como clases independientes,
    no un solo cliente raíz — separar en 5 capabilities no daría
    flexibilidad real todavía.
    """

    id: ClassVar[str] = 'sii.backend'
    label: ClassVar[str] = 'Backend de operaciones SII'
    description: ClassVar[str] = (
        'Provee el cliente para consultar y operar contra el SII '
        '(contribuyentes, RCV, CAF).'
    )

    @abstractmethod
    def get_backend(self, contribuyente: Contribuyente) -> SiiBackend | None:
        """Un `SiiBackend` listo, o `None` si falta token (propio o global)."""
