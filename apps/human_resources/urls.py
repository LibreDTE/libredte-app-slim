"""URLs de `human_resources` (prefijo `/human_resources/`)."""

from django.urls import path

from . import views

app_name = 'human_resources'

urlpatterns = [
    path('calcular/', views.calcular, name='calcular'),
    path('liquidaciones/', views.liquidaciones, name='liquidaciones'),
    path('empleados/', views.empleados, name='empleados'),
]
