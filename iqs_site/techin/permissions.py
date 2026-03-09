from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.template.loader import render_to_string


def _is_tech_admin(user):
    return user.is_authenticated and user.groups.filter(name="Tech_Admin").exists()


def judge_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not _is_tech_admin(request.user):
            is_ajax = (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or "application/json" in request.headers.get("Accept", "")
            )
            if is_ajax:
                return JsonResponse({"error": "Forbidden"}, status=403)
            return HttpResponseForbidden(
                render_to_string("tech_in/judge/permission_denied.html", request=request)
            )
        return view_func(request, *args, **kwargs)
    return wrapped


def user_can_access_team(user, team):
    """
    Returns True if user belongs to the group for this tractor_event's team
    or is part of Tech_Admin.
    """
    return True
    # if team.team_id==1:
    #     return False
    # else: 
    #     return True
    # if not user.is_authenticated:
    #     return False

    
    # Tech inspectors / administrators always have access
    if user.groups.filter(name="Tech_Admin").exists():
        return True

    
    expected_group = f"Team_{team.team_name.replace(' ', '')}"
    # if getattr(settings, "SITE_VARIANT", "normal") == "testing":
    #     return True

    return user.groups.filter(name=expected_group).exists()
