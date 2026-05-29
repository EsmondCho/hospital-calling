from django.urls import include, path

urlpatterns = [
    path('blandai/', include('api.webhook.blandai.urls')),
]
