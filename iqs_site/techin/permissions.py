from django.http import HttpResponseForbidden

def user_can_access_team(user, tractor_event):
    """
    Returns True if user belongs to the group for this tractor_event's team
    or is part of Tech_Admin.
    """
    if not user.is_authenticated:
        return False

    # Tech inspectors / administrators always have access
    if user.groups.filter(name="Tech_Admin").exists():
        return True

    team = tractor_event.team
    expected_group = f"Team_{team.team_name.replace(' ', '')}"

    return user.groups.filter(name=expected_group).exists()
