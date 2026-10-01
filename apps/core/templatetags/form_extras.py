"""
Filtro `add_class` para estilar widgets de formularios de Django.

Necesario para los forms que no son nuestros (`AuthenticationForm`,
`UserCreationForm`): no podemos declarar `Meta.widgets` ahí como en
`ContribuyenteForm`, así que la clase Bootstrap se agrega en el
template.
"""

from __future__ import annotations

from django import template
from django.forms import BoundField
from django.utils.safestring import SafeString

register = template.Library()


@register.filter(name='add_class')
def add_class(field: BoundField, css_class: str) -> SafeString:
    """Renderiza `field` agregando `css_class` a su widget."""
    return field.as_widget(attrs={'class': css_class})
