from django.urls import path
from . import views

app_name = 'compforms'

urlpatterns = [
    path('<int:event_form_id>/<int:team_id>/', views.submit_form, name='submit_form'),
    path('<int:event_form_id>/responses/', views.form_responses_overview, name='form_responses_overview'),
    path('template/<int:form_id>/', views.form_template, name='form_template'),
]
