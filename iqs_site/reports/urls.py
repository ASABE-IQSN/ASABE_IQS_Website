from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("analysis/", views.analysis_dashboard, name="analysis_dashboard"),
    path("analysis/status/<int:job_id>/", views.analysis_job_status, name="analysis_job_status"),
    path("matches/<int:report_id>/", views.report_matches, name="report_matches"),
    path("page-match/<int:page_match_id>/", views.page_match_detail, name="page_match_detail"),
    path("<int:report_id>", views.report_download, name="report_download"),
]
