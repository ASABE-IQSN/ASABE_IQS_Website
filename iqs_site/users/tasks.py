from celery import shared_task
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
import logging

from users.models import GroupProfile, TeamEmail
from events.models import Team

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3
)
def assign_user_to_teams(self, user_id: int) -> dict:
    """
    Check if user's email matches any team_emails records.
    If matches found, add user to those teams as both member and admin.

    Returns:
        dict: Summary with teams_assigned count and team details
    """
    print("Running Assign user")
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for team assignment")
        return {"error": "User not found", "user_id": user_id}

    # Case-insensitive email matching
    matching_emails = TeamEmail.objects.filter(
        email__iexact=user.email
    ).select_related('team')

    if not matching_emails.exists():
        logger.info(f"No team email matches for {user.email}")
        
        return {
            "user_id": user_id,
            "email": user.email,
            "teams_assigned": 0,
            "teams": []
        }

    teams_assigned = []
    errors = []

    for team_email in matching_emails:
        team = team_email.team
        print(f"Assigning to team:{team.team_name}")
        try:
            with transaction.atomic():
                # Ensure GroupProfile exists (auto-create if missing)
                if not hasattr(team, 'group_profile'):
                    group_name = f"team_{team.pk}_{team.team_name}".replace(" ", "_")
                    group, _ = Group.objects.get_or_create(name=group_name)
                    group_profile = GroupProfile.objects.create(
                        group=group,
                        team=team
                    )
                    logger.info(f"Created GroupProfile for team {team.team_id}")
                else:
                    group_profile = team.group_profile
                    group = group_profile.group

                # Add user to group as member (idempotent)
                if not group.user_set.filter(pk=user.pk).exists():
                    group.user_set.add(user)
                    logger.info(f"Added {user.username} to group {group.name}")

                # Add user as team admin (idempotent)
                if not group_profile.admins.filter(pk=user.pk).exists():
                    group_profile.admins.add(user)
                    logger.info(f"Added {user.username} as admin for team {team.team_id}")

                teams_assigned.append({
                    "team_id": team.team_id,
                    "team_name": team.team_name,
                })

        except Exception as e:
            error_msg = f"Error assigning {user.username} to team {team.team_id}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

    result = {
        "user_id": user_id,
        "email": user.email,
        "username": user.username,
        "teams_assigned": len(teams_assigned),
        "teams": teams_assigned,
    }

    if errors:
        result["errors"] = errors

    logger.info(f"Team assignment complete for {user.username}: {len(teams_assigned)} teams")
    return result
