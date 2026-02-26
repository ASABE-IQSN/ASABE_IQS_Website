"""
Remove ScheduleItem and ScheduleItemType from the events app migration state.
These unmanaged models have been moved to the schedule app.
No database changes are made (both models are managed=False).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0020_report_released"),
    ]

    operations = [
        # Remove from events migration state only — no DB changes (managed=False)
        migrations.DeleteModel(name="ScheduleItemType"),
        migrations.DeleteModel(name="ScheduleItem"),
    ]
