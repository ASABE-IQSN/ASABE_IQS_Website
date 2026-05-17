"""Signal receivers for the events app.

Currently wires Pull state/run_order changes to the dynamic ETA recompute
Celery task. The task uses .update() (not .save()) when persisting, so
this signal does not refire on its own writes.
"""
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Pull

_TRIGGER_STATES = {
    Pull.States.RUNNING,
    Pull.States.COMPLETED,
    Pull.States.SCRATCHED,
}


@receiver(pre_save, sender=Pull)
def _stash_old_pull(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_state = None
        instance._old_run_order = None
        return
    try:
        old = sender.objects.only("state", "run_order").get(pk=instance.pk)
        instance._old_state = old.state
        instance._old_run_order = old.run_order
    except sender.DoesNotExist:
        instance._old_state = None
        instance._old_run_order = None


@receiver(post_save, sender=Pull)
def _pull_state_changed(sender, instance, created, **kwargs):
    if not instance.hook_id:
        return

    old_state = getattr(instance, "_old_state", None)
    old_order = getattr(instance, "_old_run_order", None)

    state_changed = created or old_state != instance.state
    order_changed = old_order != instance.run_order

    relevant = (
        (state_changed and instance.state in _TRIGGER_STATES)
        or order_changed
    )
    if not relevant:
        return

    # Import here to avoid a circular import at app load.
    from .tasks import recompute_pull_etas

    hook_id = instance.hook_id
    transaction.on_commit(lambda: recompute_pull_etas.delay(hook_id))
