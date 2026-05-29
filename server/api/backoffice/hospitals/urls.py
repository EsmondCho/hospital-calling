from django.urls import path

from . import views

urlpatterns = [
    path('', views.HospitalListCreateView.as_view()),
    path('bulk_delete/', views.HospitalBulkDeleteView.as_view()),
    path('<int:pk>/', views.HospitalDetailView.as_view()),
]
