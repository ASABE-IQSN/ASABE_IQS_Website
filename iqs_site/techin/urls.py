# tech_in/urls.py
from django.urls import path
from . import views

app_name = "tech_in"

urlpatterns = [
    path("tech-in/", views.tech_in_overview, name="overview"),
    path(
        "tech-in/team/<int:tractor_event_id>/",
        views.tech_in_team_detail,
        name="team_detail",
    ),
]
