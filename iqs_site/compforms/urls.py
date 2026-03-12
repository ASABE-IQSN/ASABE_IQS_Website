from django.urls import path
from . import views

app_name = 'compforms'

urlpatterns = [
    path('<int:event_form_id>/<int:team_id>/', views.submit_form, name='submit_form'),
    path('<int:event_form_id>/<int:team_id>/autosave/', views.autosave_form, name='autosave_form'),
    path('<int:event_form_id>/<int:team_id>/swap/', views.swap_question, name='swap_question'),
    path('<int:event_form_id>/<int:team_id>/extra/', views.extra_question, name='extra_question'),
    path('<int:event_form_id>/responses/', views.form_responses_overview, name='form_responses_overview'),
    path('<int:event_form_id>/review/<int:response_id>/', views.review_response, name='review_response'),
    path('template/<int:form_id>/', views.form_template, name='form_template'),
]
