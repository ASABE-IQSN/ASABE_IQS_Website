# tech_in/urls.py
from django.urls import path
from . import views

app_name = "tech_in"

urlpatterns = [
    #path("tech-in/", views.tech_in_overview, name="overview"),
    # path(
    #     "team/<int:tractor_event_id>/",
    #     views.tech_in_team_detail,
    #     name="team_detail",
    # ),
   path(
        "event/<int:event_id>/",
        views.event_tech_in_overview,
        name="overview",
    ),

    # Team-level drilldown for that event
    path(
        "event/<int:event_id>/team/<int:team_id>/",
        views.team_tech_overview,
        name="team_tech_overview",
    ),
    path(
        "event/<int:event_id>/team/<int:team_id>/subcategory/<int:subcategory_id>/",
        views.team_subcategory_detail,
        name="team_subcategory_detail",
    ),
    path(
        "event/<int:event_id>/team/<int:team_id>/rule/<int:rule_id>/",
        views.team_rule_detail,
        name="team_rule_detail",
    ),
    path(
        "event/<int:event_id>/category/<int:category_id>",
        views.category_view,
        name="rule_category_detail",
    ),
    # Judge views
    path("judge/event/<int:event_id>/", views.judge_event_overview, name="judge_event_overview"),
    path("judge/event/<int:event_id>/category/<int:category_id>/", views.judge_category_teams, name="judge_category_teams"),
    path("judge/event/<int:event_id>/category/<int:category_id>/team/<int:team_id>/", views.judge_team_subcategories, name="judge_team_subcategories"),
    path("judge/event/<int:event_id>/category/<int:category_id>/team/<int:team_id>/subcategory/<int:subcategory_id>/", views.judge_subcategory_rules, name="judge_subcategory_rules"),
    path("judge/event/<int:event_id>/category/<int:category_id>/team/<int:team_id>/rule/<int:rule_id>/photos/", views.judge_rule_photos, name="judge_rule_photos"),
    # Judge AJAX
    path("judge/ajax/update-status/", views.judge_update_status, name="judge_update_status"),
    path("judge/ajax/update-comment/", views.judge_update_comment, name="judge_update_comment"),
    path("judge/ajax/upload-photo/", views.judge_upload_photo, name="judge_upload_photo"),
    path("judge/ajax/delete-media/<int:media_id>/", views.judge_delete_media, name="judge_delete_media"),
]
