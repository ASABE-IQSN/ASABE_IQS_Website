# tech_in/urls.py
from django.urls import path
from . import views

app_name = "tech_in"

urlpatterns = [
    path("tech-in/", views.tech_in_overview, name="overview"),
    path(
        "tech-in/et/<int:event_tractor_id>/subcat/<int:subcategory_id>/",
        views.tech_in_detail,
        name="detail",
    ),
]
