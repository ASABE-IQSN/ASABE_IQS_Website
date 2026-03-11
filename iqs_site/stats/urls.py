from django.urls import path
from . import views

app_name = "stats"

urlpatterns = [
    path("plot/", views.plot_page, name="plot_page"),
    path("api/test-series/", views.test_series_api, name="test_series_api"),
    path("daily/", views.daily_activity, name="daily_activity"),
    path("pages/", views.page_overview, name="page_overview"),
    path("page/", views.page_drill, name="page_drill"),
    path("location/", views.location_drill, name="location_drill"),
    path("ip/", views.ip_drill, name="ip_drill"),
    path("ips/", views.ip_list, name="ip_list"),
]
