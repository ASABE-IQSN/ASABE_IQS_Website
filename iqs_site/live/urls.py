from django.urls import path
from . import views

app_name = "live"

urlpatterns = [
    path('', views.live_landing, name='landing'),
    path('api/leaderboard.json', views.live_leaderboard_json, name='api_leaderboard'),
    path('api/runs.json', views.live_runs_json, name='api_runs'),
    path('api/techin.json', views.live_techin_json, name='api_techin'),
    path('pull', views.live_pull, name='pull'),
    path('maneuverability', views.live_maneuverability, name='maneuverability'),
    path('durability', views.live_durability, name='durability'),
    path('overlay', views.overlay, name="pull_overlay"),
    path('overlay/producer', views.overlay_producer, name="overlay_producer"),
    path('producer/pull', views.producer_pull, name="producer_pull"),
    path('announcer/pull', views.announcer_pull, name="announcer_pull"),
    path('announcer/maneuverability', views.announcer_maneuverability, name="announcer_maneuverability"),
    path('announcer/durability', views.announcer_durability, name="announcer_durability"),
    path('overlay/scenes/', views.overlay_scene_list, name="overlay_scene_list"),
    path('overlay/scenes/<int:scene_id>/editor/', views.overlay_scene_editor, name="overlay_scene_editor"),
    path('overlay/scenes/<int:scene_id>/save/', views.overlay_scene_save, name="overlay_scene_save"),
]
