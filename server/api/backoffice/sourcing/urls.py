from django.urls import path

from .views import (
    SourcingCitiesView,
    SourcingJobCancelView,
    SourcingJobDetailView,
    SourcingJobEventsView,
    SourcingJobListCreateView,
    SourcingStatesView,
)

urlpatterns = [
    path('jobs/',                            SourcingJobListCreateView.as_view()),
    path('jobs/<int:pk>/',                   SourcingJobDetailView.as_view()),
    path('jobs/<int:pk>/cancel/',            SourcingJobCancelView.as_view()),
    path('jobs/<int:pk>/events/',            SourcingJobEventsView.as_view()),
    path('states/',                          SourcingStatesView.as_view()),
    path('cities/',                          SourcingCitiesView.as_view()),
]
