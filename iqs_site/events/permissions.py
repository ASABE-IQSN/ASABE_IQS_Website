from django.http import HttpResponseForbidden

from django.conf import settings

def can_edit_team(user, team):
    """
    Returns True if user belongs to the group for this team or is an admin
    """
    if not user.is_authenticated:
        return False
    
    if user.groups.filter(name="Admin").exists():
        return True

    if user.is_superuser:
        return True

    expected_group = f"team_{team.team_id}_{team.team_name.replace(' ', '_')}"
   

    return user.groups.filter(name=expected_group).exists()

def can_edit_tractor(user, tractor) -> bool:
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    # Specific permission (recommended)
    if user.has_perm("events.change_tractorinfo"):
        return True

    # Your existing admin group pattern
    if user.groups.filter(name="Admin").exists():
        return True

    # If tractors should be editable by the owning/original team group:
    # (Adjust this to match your actual ownership model)
    if getattr(tractor, "original_team_id", None):
        expected_group = f"team_{tractor.original_team.team_id}_{tractor.original_team.team_name.replace(" ","_")}"
        return user.groups.filter(name=expected_group).exists()

    return False

