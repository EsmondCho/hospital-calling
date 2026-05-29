from django.urls import path

from . import views

# `versions/` reads the prompt name from a `?name=` query parameter rather
# than a path segment — a free-form name (spaces, non-ASCII) in a path would
# need URL-encoding and could clash with the greedy `<str:...>` routing.
urlpatterns = [
    path('', views.PromptListCreateView.as_view()),
    path('bulk_delete/', views.PromptBulkDeleteView.as_view()),
    path('versions/', views.PromptVersionListView.as_view()),
    path('<int:pk>/', views.PromptDetailView.as_view()),
]
