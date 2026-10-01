"""Contratos de las capabilities que `human_resources` provee a sus plugins."""

from __future__ import annotations

from typing import ClassVar

from apps.core.plugin.base import BasePluginCapability


class PayslipRendererPluginCapabilityDefinition(BasePluginCapability):
    """
    Renderiza una liquidación de sueldo a HTML/PDF para mostrarla.

    Sin `abstractmethod` ni `ABC` todavía — nadie la implementa aún,
    no hay nada que forzar. Se agrega cuando se diseñe el contrato.
    """

    id: ClassVar[str] = 'human_resources.payslip_renderer'
    label: ClassVar[str] = 'Renderizador de liquidaciones'
    description: ClassVar[str] = (
        'Renderiza una liquidación de sueldo a HTML/PDF para mostrarla.'
    )
