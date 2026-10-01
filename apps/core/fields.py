"""Campos de modelo: cifrado en reposo y dígito verificador del RUT."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.db.models.expressions import Expression

    _EncryptedTextFieldBase = models.TextField[Any, Any]
    _DvFieldBase = models.CharField[Any, Any]
else:
    # `Field` no es `Generic` en tiempo de ejecución (solo en los
    # stubs de `django-stubs`) — subscribir `models.TextField[...]`
    # directo como base real lanzaría `TypeError: not subscriptable`
    # al importar el módulo.
    _EncryptedTextFieldBase = models.TextField
    _DvFieldBase = models.CharField


def _fernet() -> Fernet:
    return Fernet(settings.FIELD_ENCRYPTION_KEY)


class EncryptedTextField(_EncryptedTextFieldBase):
    """
    `TextField` cifrado en reposo (Fernet, `FIELD_ENCRYPTION_KEY`).

    Cifra/descifra en `get_prep_value`/`from_db_value` — quien lea o
    escriba el campo en Python siempre ve el texto plano, nunca el
    valor cifrado; solo la fila en la base de datos queda cifrada.
    """

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        if not value:
            return value
        return _fernet().encrypt(value.encode()).decode()

    def from_db_value(
        self,
        value: str | None,
        _expression: Expression,
        _connection: BaseDatabaseWrapper,
    ) -> str | None:
        if not value:
            return value
        return _fernet().decrypt(value.encode()).decode()


class EncryptedJSONField(EncryptedTextField):
    """
    `EncryptedTextField` que además serializa/deserializa JSON.

    Para columnas que guardan un valor JSON que puede contener
    credenciales (ej. `PluginConfig.config`) — cifra el blob completo,
    no campo por campo dentro del JSON: nadie filtra ni consulta por
    su contenido, así que no hay razón para dejarlo legible en la
    base, y cifrar todo evita depender de que cada consumidor marque a
    mano cuáles de sus propias claves son sensibles.
    """

    # `django-stubs` tipa el `set`/`get` de cualquier `TextField` como
    # `str | Combinable`/`str` (ver `_pyi_private_set_type`/
    # `_pyi_private_get_type` en su stub — el plugin de mypy los lee
    # como anotaciones de clase, no infiere el tipo real a partir de
    # `get_prep_value`/`from_db_value`). Sin esto, `Modelo.objects
    # .create(campo=un_dict)` marcaría error de tipo pese a que
    # `get_prep_value()` acepta cualquier valor serializable a JSON.
    # `dict[str, Any]` (el tipo real) no sirve acá: mypy lo rechaza como
    # violación de Liskov contra el `str | Combinable` que ya fijó
    # `TextField` — `Any` es lo único que amplía sin chocar.
    _pyi_private_set_type: Any
    _pyi_private_get_type: Any

    def get_prep_value(self, value: Any) -> Any:
        if value is None:
            return value
        return super().get_prep_value(json.dumps(value))

    def from_db_value(
        self,
        value: str | None,
        _expression: Expression,
        _connection: BaseDatabaseWrapper,
    ) -> Any:
        value = super().from_db_value(value, _expression, _connection)
        if value is None:
            return value
        return json.loads(value)


class DvField(_DvFieldBase):
    """
    Dígito verificador del RUT, siempre en mayúscula (`K`, nunca `k`).

    Normaliza al guardar y al filtrar (`get_prep_value`), así que da lo
    mismo cómo llegue (`k` de un formulario, `K` de un DTE) y una consulta
    por `dv` encuentra la fila sea cual sea la mayúscula del valor buscado.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Un solo carácter, salvo que se indique otro largo."""
        kwargs.setdefault('max_length', 1)
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple[str, str, Sequence[Any], dict[str, Any]]:
        name, path, args, kwargs = super().deconstruct()
        # `max_length=1` es parte del campo: no se repite en las migraciones.
        kwargs.pop('max_length', None)
        return name, path, args, kwargs

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        return value.upper() if isinstance(value, str) else value

    def pre_save(self, model_instance: models.Model, add: bool) -> Any:
        value = super().pre_save(model_instance, add)
        if isinstance(value, str):
            # La instancia queda igual que la fila: ya en mayúscula.
            value = value.upper()
            setattr(model_instance, self.attname, value)
        return value
