import logging

from celery import shared_task
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def notify_subscribed_users(self, schedule_item_id: int, created: bool) -> dict:
    """Create in-app notifications and send emails to users subscribed to the
    team (and optionally type) of the given ScheduleItem.

    Triggered by the post_save signal on ScheduleItem.
    """
    from .models import ScheduleItem, ScheduleNotification, ScheduleSubscription

    try:
        item = (
            ScheduleItem.objects
            .select_related("team", "type", "event", "location")
            .get(pk=schedule_item_id)
        )
    except ScheduleItem.DoesNotExist:
        logger.error("notify_subscribed_users: ScheduleItem %s not found", schedule_item_id)
        return {"error": "ScheduleItem not found", "schedule_item_id": schedule_item_id}

    subs = (
        ScheduleSubscription.objects
        .filter(team=item.team)
        .filter(
            models.Q(schedule_item_type=item.type)
            | models.Q(schedule_item_type__isnull=True)
        )
        .select_related("user")
    )

    action = "New" if created else "Updated"
    dt_str = item.datetime.strftime("%b %-d, %H:%M")
    default_msg = f"{action}: {item.name} for {item.team.team_name} at {dt_str}"

    notifications_created = 0
    emails_sent = 0

    for sub in subs:
        user = sub.user
        if not user.email:
            continue

        ScheduleNotification.objects.create(
            user=user,
            schedule_item=item,
            message=default_msg,
        )
        notifications_created += 1

        email_body = render_to_string(
            "schedule/emails/subscription_notification.txt",
            {"item": item, "created": created, "user": user},
        )
        send_mail(
            subject=f"IQS Schedule: {item.name}",
            message=email_body,
            from_email="no-reply@internationalquarterscale.com",
            recipient_list=[user.email],
            fail_silently=True,
        )
        emails_sent += 1

    logger.info(
        "notify_subscribed_users: item=%s, notifications=%s, emails=%s",
        schedule_item_id, notifications_created, emails_sent,
    )
    return {
        "schedule_item_id": schedule_item_id,
        "notifications_created": notifications_created,
        "emails_sent": emails_sent,
    }
