from django.urls import path
from . import views

app_name = "events"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("events/", views.event_list, name="event_list"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("teams/", views.team_list, name="team_list"),
    path("teams/<int:team_id>/", views.team_detail, name="team_detail"),
    path("team-event/<int:event_id>/<int:team_id>/upload-photo/", views.upload_team_photo, name="upload_team_photo"),
    path("pulls/<int:pull_id>/", views.pull_detail, name="pull_detail"),  # stub for Charts/Data link
    path("tractors/", views.tractor_list, name="tractor_list"),
    path("tractors/<int:tractor_id>", views.tractor_detail, name="tractor_detail"),
    path("privacy/", views.privacy, name="privacy"),
    path("team-event/<int:event_id>/<int:team_id>/", views.team_event_detail, name="team_event_detail"),

]
