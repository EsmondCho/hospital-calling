from django.urls import path

from . import views

urlpatterns = [
    path('', views.CallAttemptListView.as_view()),
    path('bulk_delete/', views.CallAttemptBulkDeleteView.as_view()),
    path('<int:pk>/', views.CallAttemptDetailView.as_view()),
    path('<int:pk>/recording/', views.CallRecordingView.as_view()),
    path('<int:call_id>/comments/', views.CallCommentListCreateView.as_view()),
    path(
        '<int:call_id>/comments/<int:pk>/',
        views.CallCommentDetailView.as_view(),
    ),
]
