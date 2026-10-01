"""Implementación de `sii.backend` que provee este plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from apigatewaycl.api_client import ApiException
from apigatewaycl.api_client.sii.actividades_economicas import (
    ActividadesEconomicas,
)
from apigatewaycl.api_client.sii.caf import Caf
from apigatewaycl.api_client.sii.contribuyentes import (
    Contribuyentes as ContribuyentesPublico,
)
from apigatewaycl.api_client.sii.dte import Contribuyentes as DteContribuyentes
from apigatewaycl.api_client.sii.rcv import Rcv

from apps.libredte.plugins.contracts import (
    SiiBackend,
    SiiBackendAuthError,
    SiiBackendError,
    SiiBackendPluginCapabilityDefinition,
)

from .config_resolver import resolve_api_token, resolve_base_url

if TYPE_CHECKING:
    from apps.libredte.models import Contribuyente


class ApiGatewayClSiiBackend(SiiBackend):
    """`SiiBackend` armado con la config del plugin y el contribuyente."""

    def __init__(
        self,
        config: dict[str, Any],
        contribuyente: Contribuyente,
    ) -> None:
        """Guarda `config` del plugin y el `contribuyente` a operar."""
        self.config = config
        self.contribuyente = contribuyente

    @property
    def _rut(self) -> str:
        return f'{self.contribuyente.rut}-{self.contribuyente.dv}'

    @property
    def _api_token(self) -> str:
        """Ya lo validó `get_backend()` antes de construir esto."""
        token = resolve_api_token(self.config)
        assert token is not None
        return token

    @property
    def _api_url(self) -> str:
        return resolve_base_url(self.config)

    def _pass_kwargs(self, metodo: str) -> dict[str, str]:
        """`identificador`/`clave` por RUT/clave, o `SiiBackendAuthError`."""
        clave_sii = self.config.get('sii_auth_clave')
        if not clave_sii:
            raise SiiBackendAuthError(
                f'{metodo} requiere sii_auth_clave configurada.'
            )
        return {'identificador': self._rut, 'clave': clave_sii}

    def _cert_kwargs(self, metodo: str) -> dict[str, str]:
        """`identificador`/`clave` por certificado, o `SiiBackendAuthError`."""
        certificado = self.contribuyente.certificado
        if certificado is None:
            raise SiiBackendAuthError(
                f'{metodo} requiere un certificado digital enlazado al '
                'contribuyente.'
            )
        return {
            'identificador': certificado.x509,
            'clave': certificado.clave_privada,
        }

    def _cert_or_pass_kwargs(self, metodo: str) -> dict[str, str]:
        """Certificado si hay, si no RUT/clave, si no `SiiBackendAuthError`."""
        if self.contribuyente.certificado is not None:
            return self._cert_kwargs(metodo)
        if self.config.get('sii_auth_clave'):
            return self._pass_kwargs(metodo)
        raise SiiBackendAuthError(
            f'{metodo} requiere certificado digital o sii_auth_clave '
            'configurada.'
        )

    @property
    def _certificacion(self) -> str:
        """`'1'`/`'0'` según el ambiente SII fijo de `contribuyente`."""
        if self.contribuyente.ambiente == self.contribuyente.CERTIFICACION:
            return '1'
        return '0'

    @property
    def _certificacion_bool(self) -> bool:
        """Igual que `_certificacion`, para los métodos con `bool`."""
        return self.contribuyente.ambiente == self.contribuyente.CERTIFICACION

    @staticmethod
    def _as_dict(respuesta: Any) -> dict[str, Any]:
        """
        Achica el retorno de `apigatewaycl` al contrato de `SiiBackend`.

        `apigatewaycl` tipa sus respuestas JSON como `ApiResponse[T]`
        (o uniones más específicas según el método), no como `Any` —
        pero `SiiBackend` es agnóstico del cliente concreto que la
        implementa, así que igual se achica a `dict[str, Any]` acá en
        vez de filtrar el tipo del cliente hacia la interfaz.
        """
        return cast('dict[str, Any]', respuesta)

    @staticmethod
    def _as_bytes(respuesta: Any) -> bytes:
        """
        Achica el retorno de `apigatewaycl` al contrato de `SiiBackend`.

        Mismo motivo que `_as_dict()`, para las respuestas binarias.
        """
        return cast('bytes', respuesta)

    def sii_contribuyentes_situacion_tributaria(
        self, rut: str
    ) -> dict[str, Any]:
        """Situación tributaria pública de `rut` (sin credencial)."""
        contribuyentes = ContribuyentesPublico(
            api_token=self._api_token, api_url=self._api_url
        )
        return self._as_dict(contribuyentes.situacion_tributaria(rut))

    def sii_actividades_economicas_listado(
        self, categoria: int | None = None
    ) -> dict[str, Any]:
        """Catálogo de actividades económicas (sin credencial)."""
        actividades = ActividadesEconomicas(
            api_token=self._api_token, api_url=self._api_url
        )
        return self._as_dict(actividades.listado(categoria))

    def sii_dte_contribuyentes_datos(self) -> dict[str, Any]:
        """Datos privados del contribuyente (`auth.cert` o `auth.pass`)."""
        contribuyentes = DteContribuyentes(
            **self._cert_or_pass_kwargs('sii_dte_contribuyentes_datos'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        try:
            respuesta = contribuyentes.datos(
                self._rut, certificacion=self._certificacion
            )
        except ApiException as error:
            raise SiiBackendError(str(error)) from error
        return self._as_dict(respuesta)

    def sii_dte_contribuyentes_autorizacion(self, rut: str) -> dict[str, Any]:
        """Estado de autorización DTE de `rut` (sin credencial)."""
        contribuyentes = DteContribuyentes(
            api_token=self._api_token, api_url=self._api_url
        )
        return self._as_dict(
            contribuyentes.autorizacion(
                rut, certificacion=self._certificacion_bool
            )
        )

    def sii_dte_contribuyentes_autorizacion_certificado(
        self,
    ) -> dict[str, Any]:
        """Estado de autorización DTE, con email de intercambio (`cert`)."""
        contribuyentes = DteContribuyentes(
            **self._cert_kwargs(
                'sii_dte_contribuyentes_autorizacion_certificado'
            ),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            contribuyentes.autorizacion_certificado(
                self._rut, certificacion=self._certificacion
            )
        )

    def sii_dte_contribuyentes_autorizados(
        self,
        dia: str | None = None,
        formato: str | None = None,
    ) -> dict[str, Any] | bytes:
        """Descarga masiva de contribuyentes DTE-habilitados (`cert`)."""
        contribuyentes = DteContribuyentes(
            **self._cert_kwargs('sii_dte_contribuyentes_autorizados'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return cast(
            'dict[str, Any] | bytes',
            contribuyentes.autorizados(
                certificacion=self._certificacion, dia=dia, formato=formato
            ),
        )

    def sii_rcv_compras_resumen(
        self, periodo: str, estado: str = 'REGISTRO'
    ) -> dict[str, Any]:
        """Resumen del Registro de Compras del período (`auth.pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_compras_resumen'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.compras_resumen(
                self._rut,
                periodo,
                estado=estado,
                certificacion=self._certificacion,
            )
        )

    def sii_rcv_compras_detalle(
        self,
        periodo: str,
        dte: int = 0,
        estado: str = 'REGISTRO',
        tipo: str | None = None,
    ) -> dict[str, Any]:
        """Detalle del Registro de Compras del período (`auth.pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_compras_detalle'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.compras_detalle(
                self._rut,
                periodo,
                dte=dte,
                estado=estado,
                tipo=tipo,
                certificacion=self._certificacion,
            )
        )

    def sii_rcv_compras_async_solicitar(
        self, periodo: str, dte: int = 0, estado: str = 'REGISTRO'
    ) -> dict[str, Any]:
        """Solicita el detalle asíncrono de compras del período (`pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_compras_async_solicitar'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.compras_async_solicitar(
                self._rut,
                periodo,
                dte=dte,
                estado=estado,
                certificacion=self._certificacion,
            )
        )

    def sii_rcv_compras_async_estado(
        self,
        periodo: str,
        id_solicitud: str,
        dte: int = 0,
        estado: str = 'REGISTRO',
    ) -> dict[str, Any]:
        """Estado de una solicitud asíncrona de compras (`auth.pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_compras_async_estado'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.compras_async_estado(
                self._rut,
                periodo,
                id_solicitud,
                dte=dte,
                estado=estado,
                certificacion=self._certificacion,
            )
        )

    def sii_rcv_compras_async_detalle(
        self,
        periodo: str,
        id_solicitud: str,
        dte: int = 0,
        estado: str = 'REGISTRO',
    ) -> dict[str, Any]:
        """Detalle de una solicitud asíncrona de compras ya lista (`pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_compras_async_detalle'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.compras_async_detalle(
                self._rut,
                periodo,
                id_solicitud,
                dte=dte,
                estado=estado,
                certificacion=self._certificacion,
            )
        )

    def sii_rcv_ventas_resumen(self, periodo: str) -> dict[str, Any]:
        """Resumen del Registro de Ventas del período (`auth.pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_ventas_resumen'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.ventas_resumen(
                emisor=self._rut,
                periodo=periodo,
                certificacion=self._certificacion,
            )
        )

    def sii_rcv_ventas_detalle(
        self, periodo: str, dte: int = 0, tipo: str | None = None
    ) -> dict[str, Any]:
        """Detalle del Registro de Ventas del período (`auth.pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_ventas_detalle'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.ventas_detalle(
                self._rut,
                periodo,
                dte=dte,
                tipo=tipo,
                certificacion=self._certificacion,
            )
        )

    def sii_rcv_ventas_async_solicitar(
        self, periodo: str, dte: int = 0
    ) -> dict[str, Any]:
        """Solicita el detalle asíncrono de ventas del período (`pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_ventas_async_solicitar'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.ventas_async_solicitar(
                self._rut,
                periodo,
                dte=dte,
                certificacion=self._certificacion,
            )
        )

    def sii_rcv_ventas_async_estado(
        self, periodo: str, id_solicitud: str, dte: int = 0
    ) -> dict[str, Any]:
        """Estado de una solicitud asíncrona de ventas (`auth.pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_ventas_async_estado'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.ventas_async_estado(
                self._rut,
                periodo,
                id_solicitud,
                dte=dte,
                certificacion=self._certificacion,
            )
        )

    def sii_rcv_ventas_async_detalle(
        self, periodo: str, id_solicitud: str, dte: int = 0
    ) -> dict[str, Any]:
        """Detalle de una solicitud asíncrona de ventas ya lista (`pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_ventas_async_detalle'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.ventas_async_detalle(
                self._rut,
                periodo,
                id_solicitud,
                dte=dte,
                certificacion=self._certificacion,
            )
        )

    def sii_caf_estado_timbraje(self, dte: int) -> dict[str, Any]:
        """Folios timbrables y observaciones del SII (`auth.cert`)."""
        caf = Caf(
            **self._cert_kwargs('sii_caf_estado_timbraje'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            caf.estado_timbraje(
                self._rut, dte, certificacion=self._certificacion
            )
        )

    def sii_caf_xml(
        self,
        dte: int,
        folio_inicial: int,
        folio_final: int,
        fecha_autorizacion: str,
    ) -> bytes:
        """XML de un CAF ya autorizado (`auth.cert`)."""
        caf = Caf(
            **self._cert_kwargs('sii_caf_xml'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_bytes(
            caf.xml(
                self._rut,
                dte,
                folio_inicial,
                folio_final,
                fecha_autorizacion,
                certificacion=self._certificacion,
            )
        )

    def sii_caf_estado(
        self,
        dte: int,
        folio: int,
        formato: str | None = None,
    ) -> dict[str, Any]:
        """Estado de un folio ante el SII (`auth.cert`)."""
        caf = Caf(
            **self._cert_kwargs('sii_caf_estado'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            caf.estado(
                self._rut,
                dte,
                folio,
                certificacion=self._certificacion,
                formato=formato,
            )
        )

    def sii_caf_solicitudes(
        self,
        dte: int,
        pagina: int,
        formato: str | None = None,
    ) -> dict[str, Any]:
        """Listado paginado de solicitudes de CAF (`auth.cert`)."""
        caf = Caf(
            **self._cert_kwargs('sii_caf_solicitudes'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            caf.solicitudes(
                self._rut,
                dte,
                pagina,
                certificacion=self._certificacion,
                formato=formato,
            )
        )

    def sii_caf_estados(
        self, dte: int, folio_inicial: int, folio_final: int, estado: str
    ) -> dict[str, Any]:
        """Estados de un rango de folios, agrupados por tramos (`cert`)."""
        caf = Caf(
            **self._cert_kwargs('sii_caf_estados'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            caf.estados(
                self._rut,
                dte,
                folio_inicial,
                folio_final,
                estado,
                certificacion=self._certificacion,
            )
        )

    def sii_dte_contribuyentes_usuarios(self) -> dict[str, Any]:
        """Usuarios autorizados ante el SII para DTE (`auth.cert`)."""
        contribuyentes = DteContribuyentes(
            **self._cert_kwargs('sii_dte_contribuyentes_usuarios'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        try:
            respuesta = contribuyentes.usuarios(
                rut=self._rut, certificacion=self._certificacion
            )
        except ApiException as error:
            raise SiiBackendError(str(error)) from error
        return self._as_dict(respuesta)

    def sii_dte_contribuyentes_set_datos(
        self, datos: dict[str, Any]
    ) -> dict[str, Any]:
        """Actualiza software/emails declarados ante el SII (`auth.cert`)."""
        contribuyentes = DteContribuyentes(
            **self._cert_kwargs('sii_dte_contribuyentes_set_datos'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        respuesta = self._as_dict(
            contribuyentes.set_datos(
                self._rut, datos, certificacion=self._certificacion
            )
        )
        return self._sin_data_doblemente_anidado(respuesta)

    @staticmethod
    def _sin_data_doblemente_anidado(
        respuesta: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Aplana el `data` doblemente anidado que hoy devuelve `set_datos`.

        `apigatewaycl` responde `{"data": {"data": {...}}}` para este
        recurso en particular, a diferencia de todos los demás
        (`{"data": {...}}`) — reportado al programador que lo
        mantiene. Mientras no lo corrija, se normaliza acá para que
        quien llama siempre reciba la misma forma; si el día de
        mañana la API ya viene aplanada, esto no encuentra un `data`
        anidado y no hace nada.
        """
        data = respuesta.get('data')
        if isinstance(data, dict) and isinstance(data.get('data'), dict):
            respuesta = {**respuesta, 'data': data['data']}
        return respuesta

    def sii_dte_contribuyentes_set_usuario(
        self, usuario: dict[str, Any]
    ) -> dict[str, Any]:
        """Asigna/actualiza permisos de un usuario (`auth.cert`)."""
        contribuyentes = DteContribuyentes(
            **self._cert_kwargs('sii_dte_contribuyentes_set_usuario'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            contribuyentes.set_usuario(
                self._rut, usuario, certificacion=self._certificacion
            )
        )

    def sii_rcv_compras_set_tipo_transaccion(
        self, periodo: str, documento: dict[str, Any]
    ) -> dict[str, Any]:
        """Asigna tipo de transacción a una compra del RCV (`auth.pass`)."""
        rcv = Rcv(
            **self._pass_kwargs('sii_rcv_compras_set_tipo_transaccion'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            rcv.compras_set_tipo_transaccion(
                self._rut,
                periodo,
                documento,
                certificacion=self._certificacion,
            )
        )

    def sii_caf_solicitar(self, dte: int, cantidad: int) -> bytes:
        """Solicita folios NUEVOS al SII — timbraje real (`auth.cert`)."""
        caf = Caf(
            **self._cert_kwargs('sii_caf_solicitar'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_bytes(
            caf.solicitar(
                self._rut, dte, cantidad, certificacion=self._certificacion
            )
        )

    def sii_caf_anular(
        self,
        dte: int,
        folio_inicial: int,
        folio_final: int,
        formato: str | None = None,
    ) -> dict[str, Any]:
        """Anula un rango de folios ya solicitados (`auth.cert`)."""
        caf = Caf(
            **self._cert_kwargs('sii_caf_anular'),
            api_token=self._api_token,
            api_url=self._api_url,
        )
        return self._as_dict(
            caf.anular(
                self._rut,
                dte,
                folio_inicial,
                folio_final,
                certificacion=self._certificacion,
                formato=formato,
            )
        )


class SiiBackendPluginCapability(SiiBackendPluginCapabilityDefinition):
    """Implementación de `sii.backend` de `apigatewaycl`."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Guarda `config` (`base_url`/`api_token`/`sii_auth_clave`)."""
        self.config = config

    def get_backend(self, contribuyente: Contribuyente) -> SiiBackend | None:
        """`ApiGatewayClSiiBackend`, o `None` sin token (propio ni global)."""
        if not resolve_api_token(self.config):
            return None
        return ApiGatewayClSiiBackend(self.config, contribuyente)
