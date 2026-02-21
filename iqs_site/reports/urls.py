from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("<int:report_id>", views.report_download, name="team_event_edit"),
]
