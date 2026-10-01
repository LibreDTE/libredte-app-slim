"""Modelos de `core`."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .fields import EncryptedJSONField, EncryptedTextField


class PluginConfig(models.Model):
    """
    Configuración de un `BasePlugin` para un tenant.

    `tenant` es genérico (`GenericForeignKey`) a propósito: `core`
    nunca importa `Contribuyente` ni ningún otro modelo de tenant —
    quien llama a `resolve()` pasa su propio tenant, sea cual sea.
    `config` va cifrado completo (`EncryptedJSONField`, no por clave
    dentro del JSON): nadie filtra ni consulta `PluginConfig` por su
    contenido (`resolve()` siempre busca por `content_type`/
    `object_id`/`plugin_id`), así que no hay razón para dejarlo
    legible en la base — y cifrar todo evita depender de que cada
    `BasePlugin` marque a mano cuáles de sus propias claves son sensibles.

    `priority` vive acá, no en `config` ni en la clase `BasePlugin`: el
    orden de una cascada (`resolve_all()`) es una decisión por tenant
    (dos tenants con los mismos plugins instalados pueden querer
    probarlos en orden distinto), así que es `core` quien la conoce y
    ordena por ella — sin relación con `BasePlugin.priority`, que solo
    ordena el catálogo estático (`apps/core/plugin/contracts.py`).
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    tenant = GenericForeignKey('content_type', 'object_id')

    plugin_id = models.CharField(max_length=50)
    active = models.BooleanField(default=False)
    priority = models.IntegerField(default=0)
    config = EncryptedJSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'plugin_id'],
                name='unique_plugin_config_per_tenant_and_plugin',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.plugin_id} ({self.tenant})'


class TwoFactorAuth(models.Model):
    """
    Segundo factor (TOTP) de un usuario — existe solo si lo activó.

    Tabla aparte y no un campo en `User` porque el proyecto usa el
    `User` estándar de Django (`AUTH_USER_MODEL` sin reemplazar):
    agregarle una columna obligaría a sustituir el modelo de usuario,
    que es exactamente lo que Django desaconseja hacer con una base ya
    migrada. Que la fila exista *es* el estado "2FA activo" — no hay
    flag aparte que pueda quedar desincronizado del secreto.

    `secret` va cifrado en reposo (`EncryptedTextField`): quien lea la
    columna no puede generar códigos válidos sin `FIELD_ENCRYPTION_KEY`.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='two_factor',
    )
    secret = EncryptedTextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f'2FA de {self.user.get_username()}'
