from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("analysis/", views.reports_overview, name="reports_overview"),
    path("analysis/dashboard/", views.analysis_dashboard, name="analysis_dashboard"),
    path("analysis/event/<int:event_id>/", views.event_analysis, name="event_analysis"),
    path("analysis/coverage/", views.report_coverage, name="report_coverage"),
    path("analysis/status/<int:job_id>/", views.analysis_job_status, name="analysis_job_status"),
    path("overview/<int:report_id>/", views.report_overview, name="report_overview"),
    path("matches/<int:report_id>/", views.report_matches, name="report_matches"),
    path("image-matches/<int:report_id>/", views.report_image_matches, name="report_image_matches"),
    path("image-match/<int:image_match_id>/", views.image_match_detail, name="image_match_detail"),
    path("image/<int:image_id>/", views.image_serve, name="image_serve"),
    path("extracted/<int:report_id>/", views.report_extracted, name="report_extracted"),
    path("page-match/<int:page_match_id>/", views.page_match_detail, name="page_match_detail"),
    path("ai-detection/<int:report_id>/", views.report_ai_detection, name="report_ai_detection"),
    path("ai-detection/<int:report_id>/run/", views.retrigger_ai_detection, name="retrigger_ai_detection"),
    path("<int:report_id>", views.report_download, name="report_download"),
]
