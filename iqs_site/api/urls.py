from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from . import views

app_name = "api"

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────
    path("auth/login/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/register/", views.auth_register, name="register"),
    path("auth/me/", views.auth_me, name="auth_me"),

    # ── Events ────────────────────────────────────────────────────
    path("events/", views.event_list, name="event_list"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("events/<int:event_id>/teams/", views.event_teams, name="event_teams"),
    path("events/<int:event_id>/schedule/", views.event_schedule, name="event_schedule"),
    path("events/<int:event_id>/results/", views.event_results, name="event_results"),
    path("events/<int:event_id>/pulls/", views.event_pulls, name="event_pulls"),
    path("events/<int:event_id>/durability/", views.event_durability, name="event_durability"),
    path("events/<int:event_id>/maneuverability/", views.event_maneuverability, name="event_maneuverability"),

    # ── Teams ─────────────────────────────────────────────────────
    path("teams/", views.team_list, name="team_list"),
    path("teams/<int:team_id>/", views.team_detail, name="team_detail"),
    path("teams/<int:team_id>/events/", views.team_events, name="team_events"),

    # ── Team-Event ────────────────────────────────────────────────
    path("team-events/<int:event_id>/<int:team_id>/", views.team_event_detail, name="team_event_detail"),
    path("team-events/<int:event_id>/<int:team_id>/photos/", views.team_event_photos, name="team_event_photos"),

    # ── Tractors ──────────────────────────────────────────────────
    path("tractors/", views.tractor_list, name="tractor_list"),
    path("tractors/<int:tractor_id>/", views.tractor_detail, name="tractor_detail"),

    # ── Performance Data ──────────────────────────────────────────
    path("pulls/<int:pull_id>/", views.pull_detail, name="pull_detail"),
    path("durability-runs/<int:run_id>/", views.durability_run_detail, name="durability_run_detail"),
    path("maneuverability-runs/<int:run_id>/", views.maneuverability_run_detail, name="maneuverability_run_detail"),

    # ── Photos ────────────────────────────────────────────────────
    path("photos/", views.photo_gallery, name="photo_gallery"),

    # ── Tech Inspection ───────────────────────────────────────────
    path("events/<int:event_id>/techin/", views.techin_overview, name="techin_overview"),
    path("events/<int:event_id>/techin/<int:team_id>/", views.techin_team_detail, name="techin_team_detail"),
]
