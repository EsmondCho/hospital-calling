from django.urls import path

from . import views

urlpatterns = [
    path('', views.CallScheduleListCreateView.as_view()),
    path('bulk_delete/', views.CallScheduleBulkDeleteView.as_view()),
    path('<int:pk>/', views.CallScheduleDetailView.as_view()),
]
