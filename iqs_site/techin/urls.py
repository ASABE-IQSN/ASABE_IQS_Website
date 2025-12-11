# tech_in/urls.py
from django.urls import path
from . import views

app_name = "tech_in"

urlpatterns = [
    path("tech-in/", views.tech_in_overview, name="overview"),
    path(
        "team/<int:tractor_event_id>/",
        views.tech_in_team_detail,
        name="team_detail",
    ),
   path(
        "event/<int:event_id>/",
        views.tech_in_overview,
        name="overview",
    ),

    # Team-level drilldown for that event
    path(
        "event/<int:event_id>/team/<int:tractor_event_id>/",
        views.team_tech_overview,
        name="team_tech_overview",
    ),
    path(
        "event/<int:event_id>/team/<int:tractor_event_id>/subcategory/<int:subcategory_id>/",
        views.team_subcategory_detail,
        name="team_subcategory_detail",
    ),
    path(
        "event/<int:event_id>/team/<int:tractor_event_id>/rule/<int:rule_id>/",
        views.team_rule_detail,
        name="team_rule_detail",
    ),
]
