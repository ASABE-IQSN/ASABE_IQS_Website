from django.urls import path
from . import views

app_name = 'engagement'

urlpatterns = [
    # Staff hub
    path('staff/', views.staff_hub, name='staff_hub'),

    # Feature 1 – Crowd Submission
    path('submit/', views.submit_form, name='submit'),
    path('producer/submissions/', views.producer_queue, name='producer_queue'),
    path('producer/submissions/<int:submission_id>/approve/', views.approve_submission, name='approve_submission'),
    path('producer/submissions/<int:submission_id>/reject/', views.reject_submission, name='reject_submission'),

    # Feature 2 – Emoji Reactions
    path('react/', views.react, name='react'),

    # Feature 3 – Live Polls
    path('polls/manage/', views.poll_manage, name='poll_manage'),
    path('polls/create/', views.poll_create, name='poll_create'),
    path('polls/<int:poll_id>/activate/', views.poll_activate, name='poll_activate'),
    path('polls/<int:poll_id>/close/', views.poll_close, name='poll_close'),
    path('polls/<int:poll_id>/vote/', views.poll_vote, name='poll_vote'),

    # Feature 10 – Fan Vote
    path('vote/', views.fan_vote_ballot, name='fan_vote_ballot'),
    path('vote/cast/', views.fan_vote_cast, name='fan_vote_cast'),
    path('vote/results/', views.fan_vote_results, name='fan_vote_results'),
]
