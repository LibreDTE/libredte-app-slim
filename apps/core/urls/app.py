from django.urls import path

from ..views import app, hub

app_name = 'core'

urlpatterns = [
    path('dashboard/', hub.dashboard, name='dashboard'),
    path('setup/', app.setup, name='setup'),
    path('sudo/', app.sudo, name='sudo'),
]
