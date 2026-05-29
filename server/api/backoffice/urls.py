from django.urls import include, path

urlpatterns = [
    path('hospitals/', include('api.backoffice.hospitals.urls')),
    path('prompts/', include('api.backoffice.prompts.urls')),
    path('schedules/', include('api.backoffice.schedules.urls')),
    path('calls/', include('api.backoffice.calls.urls')),
    path('sourcing/', include('api.backoffice.sourcing.urls')),
    path('chain_keywords/', include('api.backoffice.chain_keywords.urls')),
]
