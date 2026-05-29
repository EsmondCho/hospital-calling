from django.urls import path

from .views import ChainKeywordListView

urlpatterns = [
    path('', ChainKeywordListView.as_view()),
]
