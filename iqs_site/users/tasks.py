from celery import shared_task
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.core.mail import send_mail
from django.template.loader import render_to_string
import logging

from users.models import GroupProfile, TeamEmail, TeamEnrollmentRequest
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


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def notify_team_admins_of_request(self, request_id: int) -> dict:
    """
    Send email notification to all team admins when a user requests to join.

    Returns:
        dict: Summary with emails sent count
    """
    try:
        enrollment_request = TeamEnrollmentRequest.objects.select_related(
            'user', 'team', 'team__group_profile'
        ).get(request_id=request_id)
    except TeamEnrollmentRequest.DoesNotExist:
        logger.error(f"TeamEnrollmentRequest {request_id} not found")
        return {"error": "Request not found", "request_id": request_id}

    team = enrollment_request.team
    user = enrollment_request.user

    # Get team admins
    group_profile = getattr(team, 'group_profile', None)
    if not group_profile:
        logger.warning(f"Team {team.team_id} has no group_profile")
        return {"error": "No group profile", "team_id": team.team_id}

    admins = group_profile.admins.all()

    if not admins.exists():
        logger.warning(f"Team {team.team_id} has no admins")
        return {"error": "No admins found", "team_id": team.team_id}

    # Prepare email
    subject = f"New team enrollment request for {team.team_name}"

    manage_url = f"https://iqsconnect.org/user/teams/{team.team_id}/members/"

    message = render_to_string("emails/team_enrollment_request.txt", {
        "team": team,
        "user": user,
        "message": enrollment_request.message,
        "requested_at": enrollment_request.requested_at,
        "manage_url": manage_url,
    })

    # Send to all admins
    admin_emails = [admin.email for admin in admins if admin.email]

    if not admin_emails:
        logger.warning(f"No admin emails found for team {team.team_id}")
        return {"error": "No admin emails", "team_id": team.team_id}

    send_mail(
        subject,
        message,
        "no-reply@internationalquarterscale.com",
        admin_emails,
        fail_silently=False,
    )

    logger.info(f"Sent enrollment notification to {len(admin_emails)} admins for team {team.team_id}")

    return {
        "request_id": request_id,
        "team_id": team.team_id,
        "emails_sent": len(admin_emails),
        "recipients": admin_emails,
    }
