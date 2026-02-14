from rest_framework.permissions import BasePermission
from events.permissions import can_edit_team, can_edit_tractor


class IsTeamMember(BasePermission):
    """
    Requires the view to set `self.team` before permission check.
    """

    def has_permission(self, request, view):
        team = getattr(view, "team", None)
        if team is None:
            return False
        return can_edit_team(request.user, team)


class CanEditTractor(BasePermission):
    """
    Requires the view to set `self.tractor` before permission check.
    """

    def has_permission(self, request, view):
        tractor = getattr(view, "tractor", None)
        if tractor is None:
            return False
        return can_edit_tractor(request.user, tractor)
