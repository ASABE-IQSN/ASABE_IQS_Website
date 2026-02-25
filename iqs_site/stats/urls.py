from django.urls import path
from . import views

app_name = "stats"

urlpatterns = [
    path("plot/", views.plot_page, name="plot_page"),
    path("api/test-series/", views.test_series_api, name="test_series_api"),
    path("daily/", views.daily_activity, name="daily_activity"),
    path("location/", views.location_drill, name="location_drill"),
]
