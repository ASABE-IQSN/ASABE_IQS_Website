from django.urls import path
from . import views

app_name = "live"

urlpatterns = [
    path('', views.live_landing, name='landing'),
    path('pull', views.live_pull, name='pull'),
    path('maneuverability', views.live_maneuverability, name='maneuverability'),
    path('overlay',views.overlay,name="pull_overlay"),
]
