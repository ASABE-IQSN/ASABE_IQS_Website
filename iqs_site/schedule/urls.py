from django.urls import path

from . import views

app_name = "schedule"

urlpatterns = [
    # Public: full event schedule + map
    path("event/<int:event_id>/", views.event_schedule, name="event_schedule"),
    # JSON feed of locations for Leaflet
    path("event/<int:event_id>/locations.json", views.locations_api, name="locations_api"),
    # Authenticated: team-specific schedule + map
    path("event/<int:event_id>/team/", views.team_schedule, name="team_schedule"),
    # Subscription management
    path("subscriptions/", views.manage_subscriptions, name="subscriptions"),
    # Notification actions
    path("notification/<int:notif_id>/read/", views.mark_notification_read, name="mark_read"),
    path("notifications/read-all/", views.mark_all_notifications_read, name="read_all"),
]
