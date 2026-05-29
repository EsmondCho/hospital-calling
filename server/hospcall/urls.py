from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('health/', include('health.urls')),
    path('backoffice/', include('api.backoffice.urls')),
    path('webhook/', include('api.webhook.urls')),
]

if not settings.IS_DEPLOYED:
    urlpatterns += [
        path('admin/', admin.site.urls),
    ]
