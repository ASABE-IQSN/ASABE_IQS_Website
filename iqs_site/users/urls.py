from django.urls import path
from . import views

app_name = "users"

urlpatterns = [
    # ... your other urls ...
    path("account/", views.account, name="account"),
    path(
        "teams/<int:team_id>/members/",
        views.manage_team_members,
        name="manage_team_members",
    ),
    path("signup/", views.signup, name="signup"),
    path("verify-email/<uidb64>/<token>/", views.verify_email, name="verify_email"),
]
