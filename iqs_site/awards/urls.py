from django.urls import path
from . import views

app_name = 'awards'

urlpatterns = [
    path('', views.award_history, name='award_history'),
    path('event/<int:event_id>/', views.awards_by_event, name='awards_by_event'),
    path('type/<int:award_type_id>/', views.award_type_history, name='award_type_history'),
]
