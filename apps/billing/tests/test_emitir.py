"""
Tests para `/billing/emitir` — `DocumentoForm`/`ItemFormSet`/etc.

No llaman a la API real: `biller.draft_from_form()` se mockea en los
casos que la alcanzan (éxito/`ServiceError`) — lo que se prueba acá es
la vista y los `Form`/`FormSet` (validación, "sticky" en caso de
error, el `dict` que se arma para `draft_from_form()`), no
`form.estandar` en sí.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.test import Client
from django.urls import reverse

from apps.billing.models import Borrador, TipoDte
from apps.libredte import tenancy
from apps.libredte.models import Comuna, Contribuyente, Pais
from apps.libredte.services.exceptions import ServiceError

pytestmark = pytest.mark.django_db


def _autenticar(client: Client, contribuyente: Contribuyente) -> None:
    """Login + deja `contribuyente` activo en la sesión del cliente."""
    client.force_login(contribuyente.usuario)
    session = client.session
    session[tenancy._SESSION_KEY] = contribuyente.pk
    session.save()


@pytest.fixture(autouse=True)
def chile() -> Pais:
    """`Receptor.save()` necesita a Chile disponible (país por defecto)."""
    return Pais.objects.create(codigo=Pais.CHILE, glosa='Chile')


@pytest.fixture
def comuna() -> Comuna:
    return Comuna.objects.create(codigo=13101, glosa='Santiago')


@pytest.fixture
def usuario() -> User:
    return User.objects.create_user('demo', password='demo12345')


@pytest.fixture
def contribuyente(comuna: Comuna, usuario: User) -> Contribuyente:
    return Contribuyente.objects.create(
        usuario=usuario,
        rut=76192083,
        dv='9',
        razon_social='SASCO SpA',
        giro='Servicios',
        direccion='Av. Siempre Viva 123',
        comuna=comuna,
        autorizacion_dte_resolucion_fecha='2014-08-22',
        autorizacion_dte_resolucion_numero=0,
    )


@pytest.fixture
def tipo_factura() -> TipoDte:
    return TipoDte.objects.create(codigo=33, glosa='Factura Electrónica')


def _management_form(prefix: str, total: int) -> dict[str, str]:
    return {
        f'{prefix}-TOTAL_FORMS': str(total),
        f'{prefix}-INITIAL_FORMS': '0',
        f'{prefix}-MIN_NUM_FORMS': '0',
        f'{prefix}-MAX_NUM_FORMS': '1000',
    }


def _datos_minimos_validos(tipo_dte: TipoDte) -> dict[str, str | int]:
    """
    POST mínimo que pasa `documento_form.is_valid()`/formsets.

    Un segundo ítem (`items-1`) queda sin llenar a propósito — pero
    con los mismos valores por defecto que manda un navegador real
    para una fila sin tocar (`QtyItem`/`IndExe` con su `initial`,
    el resto vacío) — sirve para probar que una fila así se descarta
    (`empty_permitted`), no que se manda igual como un segundo ítem.
    """
    return {
        'tipo_dte': tipo_dte.pk,
        'FchEmis': '2026-09-13',
        'RUTRecep': '76192083-9',
        'RznSocRecep': 'Cliente de prueba',
        **_management_form('items', 2),
        'items-0-NmbItem': 'Servicio',
        'items-0-PrcItem': '10000',
        'items-0-QtyItem': '1',
        'items-0-IndExe': '0',
        'items-1-QtyItem': '1',
        'items-1-IndExe': '0',
        **_management_form('referencias', 0),
        **_management_form('pagos', 0),
    }


def test_emitir_get_defaults_fecha_emision_to_today(
    client: Client,
    contribuyente: Contribuyente,
) -> None:
    _autenticar(client, contribuyente)

    response = client.get(reverse('billing:emitir'))

    assert response.status_code == 200
    assert response.context['documento_form'].initial['FchEmis'] is not None


def test_emitir_post_with_missing_required_field_is_sticky(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """
    Sin `RznSocRecep`, la vista nunca llama a `draft_from_form()` — la
    falla es puramente de `Form`, y lo ya tipeado (`RUTRecep`, el
    ítem) queda en la respuesta.
    """
    _autenticar(client, contribuyente)
    datos = _datos_minimos_validos(tipo_factura)
    datos['RznSocRecep'] = ''

    with mock.patch('apps.billing.views.app.biller.draft_from_form') as draft:
        response = client.post(reverse('billing:emitir'), datos)

    draft.assert_not_called()
    assert response.status_code == 200
    assert not Borrador.objects.exists()

    documento_form = response.context['documento_form']
    assert documento_form['RznSocRecep'].errors
    assert documento_form['RUTRecep'].value() == '76192083-9'
    items_formset = response.context['items_formset']
    assert items_formset[0]['NmbItem'].value() == 'Servicio'


def test_emitir_post_success_calls_draft_from_form_and_redirects(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    borrador_creado = mock.Mock(pk=42)

    with mock.patch(
        'apps.billing.views.app.biller.draft_from_form',
        return_value=borrador_creado,
    ) as draft:
        _autenticar(client, contribuyente)
        response = client.post(
            reverse('billing:emitir'),
            _datos_minimos_validos(tipo_factura),
        )

    assert response.status_code == 302
    assert isinstance(response, HttpResponseRedirect)
    assert response.url == reverse(
        'billing:borrador_detalle',
        args=[borrador_creado.pk],
    )

    draft.assert_called_once()
    _contribuyente, tipo_dte, datos_formulario, _usuario = draft.call_args.args
    assert tipo_dte == tipo_factura
    assert 'tipo_dte' not in datos_formulario
    assert datos_formulario['RUTRecep'] == '76192083-9'
    assert datos_formulario['FchEmis'] == '2026-09-13'
    # `items-1` quedó completamente vacío — se descarta, no se manda
    # como un segundo ítem en blanco.
    assert datos_formulario['NmbItem'] == ['Servicio']
    assert datos_formulario['PrcItem'] == ['10000']
    assert 'TpoDocRef' not in datos_formulario
    assert 'FchPago' not in datos_formulario


def test_emitir_post_manda_los_datos_de_traslado_de_la_guia(
    client: Client,
    contribuyente: Contribuyente,
) -> None:
    """Los campos de traslado llegan con el nombre que espera la API."""
    tipo_guia = TipoDte.objects.create(
        codigo=52, glosa='Guía de Despacho Electrónica'
    )
    datos = _datos_minimos_validos(tipo_guia)
    datos.update(
        {
            'Patente': 'ABCD12',
            'PatenteCarro': 'EFGH34',
            'FchSalida': '2026-05-04',
            'HraSalida': '08:30',
            'FchLlegada': '2026-05-05',
        }
    )

    with mock.patch(
        'apps.billing.views.app.biller.draft_from_form',
        return_value=mock.Mock(pk=42),
    ) as draft:
        _autenticar(client, contribuyente)
        response = client.post(reverse('billing:emitir'), datos)

    assert response.status_code == 302
    _contribuyente, _tipo_dte, datos_formulario, _usuario = (
        draft.call_args.args
    )
    assert datos_formulario['Patente'] == 'ABCD12'
    assert datos_formulario['PatenteCarro'] == 'EFGH34'
    assert datos_formulario['FchSalida'] == '2026-05-04'
    assert datos_formulario['HraSalida'] == '08:30'
    assert datos_formulario['FchLlegada'] == '2026-05-05'


@pytest.mark.parametrize(
    'campo', ['RUTRecep', 'RUTSolicita', 'RUTTrans', 'RUTChofer']
)
def test_emitir_post_con_rut_invalido_no_llama_a_la_api(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    campo: str,
) -> None:
    """Un RUT sin dígito verificador queda como error del campo."""
    _autenticar(client, contribuyente)
    datos = _datos_minimos_validos(tipo_factura)
    datos[campo] = '19550156156'

    with mock.patch('apps.billing.views.app.biller.draft_from_form') as draft:
        response = client.post(reverse('billing:emitir'), datos)

    draft.assert_not_called()
    assert response.status_code == 200
    assert response.context['documento_form'][campo].errors


def test_emitir_post_normaliza_los_rut_antes_de_llamar_a_la_api(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """Con o sin puntos, el RUT llega a la API como `12345678-5`."""
    datos = _datos_minimos_validos(tipo_factura)
    datos.update(
        {
            'RUTRecep': '76.192.083-9',
            'RUTTrans': '2-7',
            'RUTChofer': '1-9',
        }
    )

    with mock.patch(
        'apps.billing.views.app.biller.draft_from_form',
        return_value=mock.Mock(pk=42),
    ) as draft:
        _autenticar(client, contribuyente)
        response = client.post(reverse('billing:emitir'), datos)

    assert response.status_code == 302
    _contribuyente, _tipo_dte, datos_formulario, _usuario = (
        draft.call_args.args
    )
    assert datos_formulario['RUTRecep'] == '76192083-9'
    assert datos_formulario['RUTTrans'] == '2-7'
    assert datos_formulario['RUTChofer'] == '1-9'


def _referencia(tpo_doc_ref: str) -> dict[str, str]:
    """Una fila de referencia completa, con `tpo_doc_ref` como tipo."""
    return {
        **_management_form('referencias', 1),
        'referencias-0-TpoDocRef': tpo_doc_ref,
        'referencias-0-FolioRef': '123',
        'referencias-0-FchRef': '2026-09-13',
    }


@pytest.mark.parametrize('tpo_doc_ref', ['33', '801', 'HES'])
def test_emitir_post_acepta_tipos_de_referencia_de_hasta_3_caracteres(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
    tpo_doc_ref: str,
) -> None:
    """`TpoDocRef` es texto: un tipo DTE u otro respaldo (OC, HES)."""
    datos = {
        **_datos_minimos_validos(tipo_factura),
        **_referencia(tpo_doc_ref),
    }

    with mock.patch(
        'apps.billing.views.app.biller.draft_from_form',
        return_value=mock.Mock(pk=42),
    ) as draft:
        _autenticar(client, contribuyente)
        response = client.post(reverse('billing:emitir'), datos)

    assert response.status_code == 302
    _contribuyente, _tipo_dte, datos_formulario, _usuario = (
        draft.call_args.args
    )
    assert datos_formulario['TpoDocRef'] == [tpo_doc_ref]


def test_emitir_post_rechaza_un_tipo_de_referencia_de_mas_de_3_caracteres(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    _autenticar(client, contribuyente)
    datos = {**_datos_minimos_validos(tipo_factura), **_referencia('1234')}

    with mock.patch('apps.billing.views.app.biller.draft_from_form') as draft:
        response = client.post(reverse('billing:emitir'), datos)

    draft.assert_not_called()
    assert response.status_code == 200
    assert response.context['referencias_formset'][0]['TpoDocRef'].errors


def test_emitir_post_ignores_a_row_removed_with_the_quitar_button(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """
    El botón "Quitar" tilda `DELETE` y oculta la fila — no la saca del
    DOM (ver el comentario en `emitir.html` sobre por qué) — así que
    sus otros campos siguen llegando en el POST, pero vacíos/con su
    valor por defecto (`QtyItem=1`/`IndExe=0`, sin llenar el resto).
    Sin `can_delete=True` esta fila fallaría la validación (`NmbItem`/
    `PrcItem` faltantes) aunque el usuario ya la haya quitado.
    """
    datos = _datos_minimos_validos(tipo_factura)
    datos['items-TOTAL_FORMS'] = '2'
    datos['items-1-DELETE'] = 'on'
    datos['items-1-QtyItem'] = '1'
    datos['items-1-IndExe'] = '0'
    borrador_creado = mock.Mock(pk=42)

    with mock.patch(
        'apps.billing.views.app.biller.draft_from_form',
        return_value=borrador_creado,
    ) as draft:
        _autenticar(client, contribuyente)
        response = client.post(reverse('billing:emitir'), datos)

    assert response.status_code == 302
    _contribuyente, _tipo_dte, datos_formulario, _usuario = (
        draft.call_args.args
    )
    assert datos_formulario['NmbItem'] == ['Servicio']


def test_emitir_calcular_devuelve_subtotales_y_totales(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """
    El `index` de cada ítem es su posición en el formset, no en la
    lista ya filtrada que devuelve `calculate_totals_from_form()` —
    así el JS sabe a qué fila del DOM corresponde cada subtotal (ver
    `_filled_row_indexes()`).
    """
    datos = _datos_minimos_validos(tipo_factura)
    resultado_mockeado = {
        'detalle': [{'MontoItem': 10000}],
        'totales': {
            'MntNeto': 10000,
            'MntExe': 0,
            'IVA': 1900,
            'MntTotal': 11900,
        },
    }

    with mock.patch(
        'apps.billing.views.app.biller.calculate_totals_from_form',
        return_value=resultado_mockeado,
    ) as calculate:
        _autenticar(client, contribuyente)
        response = client.post(reverse('billing:emitir_calcular'), datos)

    assert response.status_code == 200
    assert response.json() == {
        'items': [{'index': 0, 'MontoItem': 10000}],
        'totales': resultado_mockeado['totales'],
    }
    calculate.assert_called_once()
    _contribuyente, tipo_dte, datos_formulario = calculate.call_args.args
    assert tipo_dte == tipo_factura
    assert datos_formulario['RUTRecep'] == '76192083-9'


def test_emitir_calcular_mapea_el_indice_original_saltando_filas_vacias(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """
    Con `items-0` vacío/quitado e `items-1` con datos, el único ítem
    que llega a `calculate_totals_from_form()` debe reportar `index: 1`,
    no `0`.
    """
    datos = _datos_minimos_validos(tipo_factura)
    datos['items-0-NmbItem'] = ''
    datos['items-0-PrcItem'] = ''
    datos['items-1-NmbItem'] = 'Servicio 2'
    datos['items-1-PrcItem'] = '5000'
    resultado_mockeado = {
        'detalle': [{'MontoItem': 5000}],
        'totales': {
            'MntNeto': 5000,
            'MntExe': 0,
            'IVA': 950,
            'MntTotal': 5950,
        },
    }

    with mock.patch(
        'apps.billing.views.app.biller.calculate_totals_from_form',
        return_value=resultado_mockeado,
    ):
        _autenticar(client, contribuyente)
        response = client.post(reverse('billing:emitir_calcular'), datos)

    assert response.status_code == 200
    assert response.json()['items'] == [{'index': 1, 'MontoItem': 5000}]


def test_emitir_calcular_responde_400_si_el_formulario_es_invalido(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """
    Formulario a medio llenar (esperable en vivo, nunca llega a llamar
    al SDK) — igual es un error real (400 con los campos que fallan),
    nunca un `null` silencioso.
    """
    datos = _datos_minimos_validos(tipo_factura)
    datos['RznSocRecep'] = ''

    with mock.patch(
        'apps.billing.views.app.biller.calculate_totals_from_form',
    ) as calculate:
        _autenticar(client, contribuyente)
        response = client.post(reverse('billing:emitir_calcular'), datos)

    calculate.assert_not_called()
    assert response.status_code == 400
    cuerpo = response.json()
    assert cuerpo['detail'] == 'El formulario todavía no está completo.'
    assert 'RznSocRecep' in cuerpo['errors']


def test_emitir_calcular_devuelve_el_error_si_el_servicio_falla(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """
    Un `ServiceError` real (ej. la API del SII rechazó los datos) se
    responde como error de verdad — nunca se oculta en un `null`
    silencioso, para que el JS lo pueda dejar en consola.
    """
    datos = _datos_minimos_validos(tipo_factura)

    with mock.patch(
        'apps.billing.views.app.biller.calculate_totals_from_form',
        side_effect=ServiceError('No se pudo calcular.'),
    ):
        _autenticar(client, contribuyente)
        response = client.post(reverse('billing:emitir_calcular'), datos)

    assert response.status_code == 500
    assert response.json() == {'detail': 'No se pudo calcular.'}


def test_emitir_post_service_error_is_sticky(
    client: Client,
    contribuyente: Contribuyente,
    tipo_factura: TipoDte,
) -> None:
    """Un `ServiceError` de la API deja el formulario "sticky" también."""
    with mock.patch(
        'apps.billing.views.app.biller.draft_from_form',
        side_effect=ServiceError('El SII rechazó el documento.'),
    ):
        _autenticar(client, contribuyente)
        response = client.post(
            reverse('billing:emitir'),
            _datos_minimos_validos(tipo_factura),
        )

    assert response.status_code == 200
    assert not Borrador.objects.exists()
    assert (
        response.context['documento_form']['RUTRecep'].value() == '76192083-9'
    )
    mensajes = [str(mensaje) for mensaje in response.context['messages']]
    assert any(
        'El SII rechazó el documento.' in mensaje for mensaje in mensajes
    )
