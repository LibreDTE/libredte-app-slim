"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))

"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.forms import LoginForm
from apps.core.views.hub import (
    profile,
    profile_api_token_delete,
    profile_api_token_generate,
    profile_two_factor_activate,
    profile_two_factor_deactivate,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    # Sobrescribe solo `login/` del include de abajo, por dos razones:
    # con sesión ya iniciada, ir directo a LOGIN_REDIRECT_URL en vez de
    # mostrar el form de nuevo (LoginView no lo hace por defecto,
    # `redirect_authenticated_user=False`); y usar `LoginForm`, que
    # suma el segundo factor al login (ver `apps/core/forms.py`).
    path(
        'accounts/login/',
        LoginView.as_view(
            redirect_authenticated_user=True,
            authentication_form=LoginForm,
        ),
        name='login',
    ),
    # `django.contrib.auth.urls` no trae vista de perfil — la agregamos
    # acá mismo, junto al resto de rutas de `accounts/`.
    path('accounts/profile/', profile, name='profile'),
    # Una URL por operación del perfil, en vez de un `action` que la
    # vista despache: cada una es `POST` y vuelve al perfil (ver
    # `apps/core/views/hub.py::profile`).
    path(
        'accounts/profile/2fa/activate/',
        profile_two_factor_activate,
        name='profile_two_factor_activate',
    ),
    path(
        'accounts/profile/2fa/deactivate/',
        profile_two_factor_deactivate,
        name='profile_two_factor_deactivate',
    ),
    path(
        'accounts/profile/token/generate/',
        profile_api_token_generate,
        name='profile_api_token_generate',
    ),
    path(
        'accounts/profile/token/delete/',
        profile_api_token_delete,
        name='profile_api_token_delete',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('apps.public.urls')),
    path('', include('apps.core.urls.app')),
    path('settings/', include('apps.core.urls.settings')),
    path('libredte/', include('apps.libredte.urls.app')),
    path(
        'settings/libredte/',
        include('apps.libredte.urls.settings'),
    ),
    # Documentación de la API pública. El esquema es el que generan las
    # propias vistas (`@extend_schema`), así que no puede quedar
    # desactualizado respecto del código; Swagger y ReDoc son dos
    # lecturas del mismo esquema (probar llamadas / leer de corrido).
    path('api/schema/', SpectacularAPIView.as_view(), name='api_schema'),
    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(url_name='api_schema'),
        name='api_docs',
    ),
    path(
        'api/redoc/',
        SpectacularRedocView.as_view(url_name='api_schema'),
        name='api_redoc',
    ),
    path('api/v1/', include('apps.libredte.api.urls')),
    path('billing/', include('apps.billing.urls.app')),
    path(
        'settings/billing/',
        include('apps.billing.urls.settings'),
    ),
    path('api/v1/', include('apps.billing.api.urls')),
    path('accounting/', include('apps.accounting.urls.app')),
    path(
        'settings/accounting/',
        include('apps.accounting.urls.settings'),
    ),
    path('human_resources/', include('apps.human_resources.urls')),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
