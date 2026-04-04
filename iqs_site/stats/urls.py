from django.urls import path
from . import views

app_name = "stats"

urlpatterns = [
    path("plot/", views.plot_page, name="plot_page"),
    path("explore/", views.explore_page, name="explore_page"),
    path("api/test-series/", views.test_series_api, name="test_series_api"),
    path("api/explore/data/", views.explore_data_api, name="explore_data_api"),
    path("api/explore/configs/", views.explore_configs_api, name="explore_configs_api"),
    path("api/explore/configs/<int:config_id>/use/", views.explore_config_use_api, name="explore_config_use_api"),
    path("api/explore/configs/<int:config_id>/hide/", views.explore_config_hide_api, name="explore_config_hide_api"),
    path("daily/", views.daily_activity, name="daily_activity"),
    path("pages/", views.page_overview, name="page_overview"),
    path("page/", views.page_drill, name="page_drill"),
    path("location/", views.location_drill, name="location_drill"),
    path("ip/", views.ip_drill, name="ip_drill"),
    path("ips/", views.ip_list, name="ip_list"),
    path("team-pages/", views.team_page_activity, name="team_page_activity"),
    path("user/", views.user_activity, name="user_activity"),
    path("server-error/<int:error_id>/", views.server_error_detail, name="server_error_detail"),
    path("nginx/status/", views.nginx_status_drill, name="nginx_status_drill"),
    # Page-time tracking
    path("pv/start/", views.pv_start, name="pv_start"),
    path("pv/ping/", views.pv_ping, name="pv_ping"),
    path("pv/end/", views.pv_end, name="pv_end"),
]
