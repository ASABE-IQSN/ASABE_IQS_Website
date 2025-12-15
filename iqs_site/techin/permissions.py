from django.http import HttpResponseForbidden

from django.conf import settings




def user_can_access_team(user, team):
    """
    Returns True if user belongs to the group for this tractor_event's team
    or is part of Tech_Admin.
    """
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
