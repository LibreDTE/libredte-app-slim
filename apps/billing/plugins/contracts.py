"""Contratos de las capabilities que `billing` provee para sus plugins."""

from __future__ import annotations

from typing import ClassVar

from apps.core.plugin.base import BasePluginCapability


class DocumentRendererPluginCapabilityDefinition(BasePluginCapability):
    """
    Renderiza un DTE a HTML/PDF para mostrarlo.

    Sin `abstractmethod` ni `ABC` todavía — nadie la implementa aún,
    no hay nada que forzar. Se agrega cuando se diseñe el contrato.
    """

    id: ClassVar[str] = 'billing.document_renderer'
    label: ClassVar[str] = 'Renderizador de documentos'
    description: ClassVar[str] = 'Renderiza un DTE a HTML/PDF para mostrarlo.'
