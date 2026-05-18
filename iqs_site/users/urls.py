from django.urls import path
from . import views

app_name = "users"

urlpatterns = [
    # ... your other urls ...
    path("account/", views.account, name="account"),
    path("account/edit/", views.edit_profile, name="edit_profile"),
    path(
        "teams/<int:team_id>/members/",
        views.manage_team_members,
        name="manage_team_members",
    ),
    path(
        "team-requests/",
        views.review_team_requests,
        name="review_team_requests",
    ),
    path("admin-tools/", views.admin_tools, name="admin_tools"),
    path("signup/", views.signup, name="signup"),
    path("verify-email/<uidb64>/<token>/", views.verify_email, name="verify_email"),
    path("auth-status/", views.auth_status, name="auth_status"),
]
