from django.conf import settings
from django.db import models


class Location(models.Model):
    ICON_CHOICES = [
        ("pull_track",      "Pull Track"),
        ("durability",      "Durability Course"),
        ("maneuverability", "Maneuverability Course"),
        ("registration",    "Registration"),
        ("camping",         "Camping"),
        ("other",           "Other"),
    ]

    location_id   = models.AutoField(primary_key=True)
    name          = models.CharField(max_length=100)
    description   = models.TextField(blank=True, null=True)
    address       = models.CharField(max_length=255, blank=True, null=True)
    latitude      = models.FloatField()
    longitude     = models.FloatField()
    icon_category = models.CharField(max_length=30, choices=ICON_CHOICES, default="other")
    event         = models.ForeignKey(
        "events.Event",
        models.CASCADE,
        related_name="locations",
    )

    class Meta:
        db_table = "schedule_location"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_icon_category_display()})"


class ScheduleItemType(models.Model):
    schedule_item_type_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=45)

    def __str__(self):
        return self.name or f"ScheduleItemType {self.schedule_item_type_id}"

    class Meta:
        managed = False
        db_table = "schedule_item_types"


class ScheduleItem(models.Model):
    schedule_item_id = models.AutoField(primary_key=True)
    datetime = models.DateTimeField()
    name = models.CharField(max_length=45)
    type = models.ForeignKey(
        ScheduleItemType,
        models.DO_NOTHING,
        db_column="type",
        related_name="items",
    )
    team = models.ForeignKey(
        "events.Team",
        models.DO_NOTHING,
        db_column="team",
        related_name="schedule_items",
    )
    event = models.ForeignKey(
        "events.Event",
        models.DO_NOTHING,
        db_column="event",
        related_name="schedule_items",
    )
    # Requires manual ALTER TABLE after running migrations (see README note)
    location = models.ForeignKey(
        Location,
        models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_items",
    )

    def __str__(self):
        return f"{self.name} – {self.team} @ {self.datetime:%Y-%m-%d %H:%M}"

    class Meta:
        managed = False
        db_table = "schedule_items"
        ordering = ["datetime"]


class ScheduleSubscription(models.Model):
    """A user's global subscription to a team (+ optional event type).

    ``schedule_item_type=None`` means the user wants notifications for all
    event types belonging to that team.
    """

    subscription_id    = models.AutoField(primary_key=True)
    user               = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.CASCADE,
        related_name="schedule_subscriptions",
    )
    team               = models.ForeignKey(
        "events.Team",
        models.CASCADE,
        db_column="team_id",
        db_constraint=False,
        related_name="subscriptions",
    )
    schedule_item_type = models.ForeignKey(
        ScheduleItemType,
        models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="subscriptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "schedule_subscription"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "team", "schedule_item_type"],
                name="unique_subscription_user_team_type",
            )
        ]

    def __str__(self):
        type_label = self.schedule_item_type.name if self.schedule_item_type else "All types"
        return f"{self.user.username} → {self.team} ({type_label})"


class ScheduleNotification(models.Model):
    """In-app notification created when a subscribed schedule item is saved."""

    notification_id = models.AutoField(primary_key=True)
    user            = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.CASCADE,
        related_name="schedule_notifications",
    )
    schedule_item   = models.ForeignKey(
        ScheduleItem,
        models.DO_NOTHING,
        db_constraint=False,
        related_name="notifications",
    )
    message    = models.CharField(max_length=500)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "schedule_notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message[:60]}"
