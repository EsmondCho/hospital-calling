from django.urls import path

from . import views

urlpatterns = [
    # Secret is embedded in the URL path (BlandAI doesn't sign webhooks).
    # `views.call_status` constant-time-compares this token to
    # `settings.BLANDAI_WEBHOOK_SECRET` before processing the payload.
    path('call_status/<str:token>/', views.call_status),
]
