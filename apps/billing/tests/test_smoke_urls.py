"""
Test de humo: un `GET` autenticado a cada URL nombrada del proyecto.

No verifica contenido ni comportamiento de negocio — cada vista ya
tiene sus propios tests para eso. Esto solo agarra barato lo que un
test unitario no ejercita porque no arma una instancia real de la
vista con datos reales: un `TypeError`/`AttributeError` al construir un
`Form`/`ModelForm` o al renderizar un template (ver el bug real que
esto encontró: `cast('forms.ModelChoiceField[...]', ...)` con el tipo
subscrito sin comillas rompía en cada `GET` a
`/settings/billing/actividades/`, y ningún test lo ejercitaba).

Recorre `django.urls.get_resolver()` completo (todas las apps, no solo
`billing`) — así una app nueva que agregue una vista rota queda
cubierta sin tener que acordarse de sumarla acá. Excluye:

- `admin:*` — administración de Django, no código propio de esta app.
- Las vistas que golpean la API real de LibreDTE Lib sin mockear nada
  (`*_render_html`/`*_descargar_pdf` de emitidos/borradores/recibidos)
  — mismo criterio que el resto de la suite (ver `test_biller.py` y
  similares): nada que llame al SDK real se prueba offline. Si fallan
  por conectividad, no es un bug de esta app.
"""

from __future__ import annotations

import base64

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import URLResolver, get_resolver, reverse

from apps.billing.models import (
    Borrador,
    DteEmitido,
    DteRecibido,
    Emisor,
    Item,
    ItemCategoria,
    Receptor,
    TipoDte,
)
from apps.libredte import tenancy
from apps.libredte.models import (
    Certificado,
    Comuna,
    Contribuyente,
    Pais,
    Sucursal,
)

pytestmark = pytest.mark.django_db

# Vistas que llaman a la API real del SDK sin mockear — fuera del
# alcance de este test offline (ver docstring del módulo).
_EXCLUDED_NAMES = {
    'billing:emitido_render_html',
    'billing:emitido_descargar_pdf',
    'billing:borrador_render_html',
    'billing:borrador_descargar_pdf',
    'billing:recibido_render_html',
    'billing:recibido_descargar_pdf',
    'billing:ventas_periodo_rcv_resumen',
    'billing:ventas_periodo_rcv_detalle',
    'billing:compras_periodo_rcv_resumen',
    'billing:compras_periodo_rcv_detalle',
}


def _xml_base64(xml_text: str) -> str:
    return base64.b64encode(xml_text.encode('iso-8859-1')).decode('ascii')


def _iter_url_names(
    resolver: URLResolver, namespace_path: tuple[str, ...] = ()
) -> list[tuple[str, dict[str, str]]]:
    """`(nombre_completo, {kwarg: tipo_de_converter})` de cada URL nombrada."""
    resultado = []
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            ns = (
                (*namespace_path, pattern.namespace)
                if pattern.namespace
                else namespace_path
            )
            resultado.extend(_iter_url_names(pattern, ns))
        elif pattern.name is not None:
            full_name = ':'.join((*namespace_path, pattern.name))
            if full_name.startswith('admin:') or full_name in _EXCLUDED_NAMES:
                continue
            converters = {
                nombre: type(conv).__name__
                for nombre, conv in pattern.pattern.converters.items()
            }
            resultado.append((full_name, converters))
    return resultado


class Dataset:
    """Un objeto real de cada modelo que alguna URL necesita por `pk`."""

    def __init__(self) -> None:
        Pais.objects.create(codigo=Pais.CHILE, glosa='Chile')
        comuna = Comuna.objects.create(codigo=13101, glosa='Santiago')

        self.usuario = User.objects.create_user('demo', password='demo12345')
        self.contribuyente = Contribuyente.objects.create(
            usuario=self.usuario,
            rut=76192083,
            dv='9',
            razon_social='SASCO SpA',
            giro='Servicios',
            direccion='Av. Siempre Viva 123',
            comuna=comuna,
            autorizacion_dte_resolucion_fecha='2014-08-22',
            autorizacion_dte_resolucion_numero=0,
        )

        self.tipo_dte = TipoDte.objects.create(
            codigo=33,
            glosa='Factura Electrónica',
            operacion=TipoDte.Operacion.SUMA,
            venta=True,
        )

        self.sucursal = Sucursal.objects.create(
            contribuyente=self.contribuyente,
            es_matriz=True,
            nombre='Casa matriz',
            direccion=self.contribuyente.direccion,
            comuna=comuna,
        )

        self.receptor = Receptor.objects.create(
            contribuyente=self.contribuyente,
            rut=12345678,
            dv='5',
            razon_social='Cliente de prueba',
        )
        self.emisor = Emisor.objects.create(
            contribuyente=self.contribuyente,
            rut=76111222,
            dv='6',
            razon_social='Proveedor de prueba',
        )

        self.categoria = ItemCategoria.objects.create(
            contribuyente=self.contribuyente,
            nombre='General',
        )
        self.item = Item.objects.create(
            contribuyente=self.contribuyente,
            categoria=self.categoria,
            codigo='ITEM-001',
            nombre='Ítem de prueba',
            precio=1000,
        )

        self.certificado = Certificado.objects.create(
            usuario=self.usuario,
            certificado_id='12345678-5',
            x509='-----BEGIN CERTIFICATE-----...',
            clave_privada='-----BEGIN PRIVATE KEY-----...',
        )

        xml = _xml_base64(
            '<?xml version="1.0" encoding="ISO-8859-1"?>'
            '<DTE xmlns:sii="http://www.sii.cl/SiiDte"></DTE>',
        )
        self.dte_emitido = DteEmitido.objects.create(
            contribuyente=self.contribuyente,
            tipo_dte=self.tipo_dte,
            receptor=self.receptor,
            usuario=self.usuario,
            folio=1,
            periodo=202609,
            fecha='2026-09-05',
            total=11_900,
            xml_base64=xml,
        )
        self.dte_recibido = DteRecibido.objects.create(
            contribuyente=self.contribuyente,
            tipo_dte=self.tipo_dte,
            emisor=self.emisor,
            usuario=self.usuario,
            folio=1,
            periodo=202609,
            fecha='2026-09-05',
            total=5_000,
            xml_base64=xml,
        )
        self.borrador = Borrador.objects.create(
            contribuyente=self.contribuyente,
            tipo_dte=self.tipo_dte,
            receptor=self.receptor,
            usuario=self.usuario,
            fecha='2026-09-05',
            datos={},
            xml_base64=xml,
            total=11_900,
        )

    def kwargs_por_nombre(self, nombre: str) -> dict[str, int | str] | None:
        """`kwargs` para `reverse(nombre)`, o `None` si no aplica."""
        mapa: dict[str, dict[str, int | str]] = {
            'billing:emitido_detalle': {'pk': self.dte_emitido.pk},
            'billing:emitido_descargar_xml': {'pk': self.dte_emitido.pk},
            'billing:emitido_enviar_sii': {'pk': self.dte_emitido.pk},
            'billing:emitido_actualizar_estado': {'pk': self.dte_emitido.pk},
            'libredte:certificado_eliminar': {'pk': self.certificado.pk},
            'billing:receptor_detalle': {'pk': self.receptor.pk},
            'billing:receptor_editar': {'pk': self.receptor.pk},
            'billing:receptor_eliminar': {'pk': self.receptor.pk},
            'billing:borrador_detalle': {'pk': self.borrador.pk},
            'billing:borrador_descargar_xml': {'pk': self.borrador.pk},
            'billing:borrador_descargar_json_normalizado': {
                'pk': self.borrador.pk,
            },
            'billing:borrador_descargar_json_extra': {'pk': self.borrador.pk},
            'billing:borrador_confirmar': {'pk': self.borrador.pk},
            'billing:borrador_eliminar': {'pk': self.borrador.pk},
            'billing:recibido_detalle': {'pk': self.dte_recibido.pk},
            'billing:recibido_descargar_xml': {'pk': self.dte_recibido.pk},
            'billing:emitir_masivo_pdf': {'token': 'no-es-un-token'},
            'billing:emitir_masivo_plantilla': {'extension': 'csv'},
            'billing:ventas_periodo': {'periodo': 202609},
            'billing:compras_periodo': {'periodo': 202609},
            'billing:emisor_detalle': {'pk': self.emisor.pk},
            'libredte_settings:sucursal_editar': {'pk': self.sucursal.pk},
            'libredte_settings:sucursal_eliminar': {'pk': self.sucursal.pk},
            'billing_settings:item_editar': {'pk': self.item.pk},
            'billing_settings:item_eliminar': {'pk': self.item.pk},
            'billing_settings:item_categoria_editar': {
                'pk': self.categoria.pk,
            },
            'billing_settings:item_categoria_eliminar': {
                'pk': self.categoria.pk,
            },
            'billing_settings:folio_detalle': {'pk': self.tipo_dte.pk},
            'billing_settings:folio_modificar': {'pk': self.tipo_dte.pk},
            'billing_settings:folio_solicitar_caf_tipo': {
                'pk': self.tipo_dte.pk,
            },
            'billing_settings:folio_reobtener_caf': {'pk': self.tipo_dte.pk},
            'billing_settings:folio_reobtener_caf_cargar': {
                'pk': self.tipo_dte.pk,
            },
            'billing_settings:folio_anular_caf': {'pk': self.tipo_dte.pk},
            'billing_settings:caf_descargar_xml': {'pk': 999999},
            'billing_settings:caf_eliminar': {'pk': 999999},
            'core_settings:plugin_configure': {
                'plugin_id': 'libredte_lib_api',
            },
            'libredte:contribuyente_seleccionar': {
                'rut': self.contribuyente.rut,
            },
            'password_reset_confirm': {'uidb64': 'x', 'token': 'x'},
        }
        return mapa.get(nombre)


@pytest.fixture
def dataset() -> Dataset:
    return Dataset()


@pytest.fixture
def client_autenticado(dataset: Dataset) -> Client:
    client = Client()
    client.force_login(dataset.usuario)
    session = client.session
    session[tenancy._SESSION_KEY] = dataset.contribuyente.pk
    session.save()
    return client


_URL_NAMES = _iter_url_names(get_resolver())


@pytest.mark.parametrize(
    ('nombre', 'converters'),
    _URL_NAMES,
    ids=[nombre for nombre, _ in _URL_NAMES],
)
def test_get_no_rompe(
    nombre: str,
    converters: dict[str, str],
    client_autenticado: Client,
    dataset: Dataset,
) -> None:
    if converters and not dataset.kwargs_por_nombre(nombre):
        pytest.skip(f'{nombre}: sin kwargs de prueba mapeados, se omite.')

    url = reverse(nombre, kwargs=dataset.kwargs_por_nombre(nombre))
    response = client_autenticado.get(url)

    assert response.status_code < 500, (
        f'{nombre} ({url}) respondió {response.status_code}'
    )
