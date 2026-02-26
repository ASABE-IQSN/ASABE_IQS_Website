from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="schedule.ScheduleItem")
def schedule_item_saved(sender, instance, created, **kwargs):
    """Fire the notification task whenever a ScheduleItem is created or its
    datetime changes. We check the datetime change via update_fields so that
    bulk-edits that don't touch datetime (e.g. name corrections) are silent.
    """
    update_fields = kwargs.get("update_fields")

    # Always notify on creation; on update only notify when datetime changed.
    if not created and update_fields is not None and "datetime" not in update_fields:
        return

    from .tasks import notify_subscribed_users
    notify_subscribed_users.delay(instance.pk, created=created)
