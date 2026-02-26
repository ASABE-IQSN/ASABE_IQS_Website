import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        # events 0021 removes ScheduleItem/ScheduleItemType from events state
        ("events", "0021_move_schedule_models_to_schedule_app"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Unmanaged models (state-only, no DB operations) ───────────────────
        migrations.CreateModel(
            name="ScheduleItemType",
            fields=[
                ("schedule_item_type_id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=45)),
            ],
            options={
                "db_table": "schedule_item_types",
                "managed": False,
            },
        ),
        # Location must be created before ScheduleItem references it
        migrations.CreateModel(
            name="Location",
            fields=[
                ("location_id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True, null=True)),
                ("address", models.CharField(blank=True, max_length=255, null=True)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                (
                    "icon_category",
                    models.CharField(
                        choices=[
                            ("pull_track", "Pull Track"),
                            ("durability", "Durability Course"),
                            ("maneuverability", "Maneuverability Course"),
                            ("registration", "Registration"),
                            ("camping", "Camping"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=30,
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="locations",
                        to="events.event",
                    ),
                ),
            ],
            options={
                "db_table": "schedule_location",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ScheduleItem",
            fields=[
                ("schedule_item_id", models.AutoField(primary_key=True, serialize=False)),
                ("datetime", models.DateTimeField()),
                ("name", models.CharField(max_length=45)),
                (
                    "type",
                    models.ForeignKey(
                        db_column="type",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="items",
                        to="schedule.scheduleitemtype",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        db_column="team",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="schedule_items",
                        to="events.team",
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        db_column="event",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="schedule_items",
                        to="events.event",
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="schedule_items",
                        to="schedule.location",
                    ),
                ),
            ],
            options={
                "db_table": "schedule_items",
                "ordering": ["datetime"],
                "managed": False,
            },
        ),
        # ── Managed models (creates DB tables) ────────────────────────────────
        migrations.CreateModel(
            name="ScheduleSubscription",
            fields=[
                ("subscription_id", models.AutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedule_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        db_column="team_id",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscriptions",
                        to="events.team",
                    ),
                ),
                (
                    "schedule_item_type",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subscriptions",
                        to="schedule.scheduleitemtype",
                    ),
                ),
            ],
            options={
                "db_table": "schedule_subscription",
            },
        ),
        migrations.AddConstraint(
            model_name="schedulesubscription",
            constraint=models.UniqueConstraint(
                fields=["user", "team", "schedule_item_type"],
                name="unique_subscription_user_team_type",
            ),
        ),
        migrations.CreateModel(
            name="ScheduleNotification",
            fields=[
                ("notification_id", models.AutoField(primary_key=True, serialize=False)),
                ("message", models.CharField(max_length=500)),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedule_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "schedule_item",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="notifications",
                        to="schedule.scheduleitem",
                    ),
                ),
            ],
            options={
                "db_table": "schedule_notification",
                "ordering": ["-created_at"],
            },
        ),
    ]
