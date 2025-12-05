# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models
from datetime import datetime


class TeamClass(models.Model):
    team_class_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "team_class"

    def __str__(self):
        return self.name or f"TeamClass {self.team_class_id}"


class Event(models.Model):
    event_id = models.AutoField(primary_key=True)
    event_name = models.CharField(max_length=255, blank=True, null=True)
    event_datetime = models.DateTimeField(blank=True, null=True)

    # Convenience many-to-many – all tractors in this event
    tractors = models.ManyToManyField(
        "Tractor",
        through="TractorEvent",
        related_name="events",
    )

    class Meta:
        managed = False
        db_table = "events"

    def __str__(self):
        return self.event_name or f"Event {self.event_id}"


class Team(models.Model):
    team_id = models.AutoField(primary_key=True)
    team_name = models.CharField(max_length=255)
    team_number = models.CharField(max_length=255)

    team_class = models.ForeignKey(
        TeamClass,
        models.DO_NOTHING,
        db_column="team_class_id",
        related_name="teams",
        blank=True,
        null=True,
    )

    # Convenience many-to-many – all tractors this team has used
    tractors = models.ManyToManyField(
        "Tractor",
        through="TractorEvent",
        related_name="teams",
    )

    class Meta:
        managed = False
        db_table = "teams"

    def __str__(self):
        return f"{self.team_name} ({self.team_number})"


class Tractor(models.Model):
    tractor_id = models.AutoField(primary_key=True)
    tractor_name = models.CharField(max_length=255, blank=True, null=True)

    original_team = models.ForeignKey(
        Team,
        models.DO_NOTHING,
        db_column="original_team_id",
        related_name="original_tractors",
        blank=True,
        null=True,
    )

    # tractor_events M2M via explicit through model is handled below

    class Meta:
        managed = False
        db_table = "tractors"

    def __str__(self):
        return self.tractor_name or f"Tractor {self.tractor_id}"


class TractorEvent(models.Model):
    tractor_event_id = models.AutoField(primary_key=True)

    tractor = models.ForeignKey(
        Tractor,
        models.DO_NOTHING,
        db_column="tractor_id",
        related_name="tractor_events",
    )
    team = models.ForeignKey(
        Team,
        models.DO_NOTHING,
        db_column="team_id",
        related_name="tractor_events",
    )
    event = models.ForeignKey(
        Event,
        models.DO_NOTHING,
        db_column="event_id",
        related_name="tractor_events",
    )

    class Meta:
        managed = False
        db_table = "tractor_events"
        constraints = [
            models.UniqueConstraint(
                fields=["tractor", "team", "event"],
                name="uix_tractor_team_event",
            )
        ]

    def __str__(self):
        return f"TractorEvent #{self.tractor_event_id}"


class Hook(models.Model):
    hook_id = models.AutoField(primary_key=True)
    event = models.ForeignKey(
        Event,
        models.DO_NOTHING,
        db_column="event_id",
        related_name="hooks",
    )
    hook_name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "hooks"

    def __str__(self):
        return f"Hook {self.hook_id} (Event {self.event_id})"


class Pull(models.Model):
    pull_id = models.AutoField(primary_key=True)
    final_distance = models.FloatField(blank=True, null=True)

    team = models.ForeignKey(
        Team,
        models.DO_NOTHING,
        db_column="team_id",
        related_name="pulls",
    )
    event = models.ForeignKey(
        Event,
        models.DO_NOTHING,
        db_column="event_id",
        related_name="pulls",
        blank=True,
        null=True,
    )
    hook = models.ForeignKey(
        Hook,
        models.DO_NOTHING,
        db_column="hook_id",
        related_name="pulls",
        blank=True,
        null=True,
    )
    tractor = models.ForeignKey(
        Tractor,
        models.DO_NOTHING,
        db_column="tractor_id",
        related_name="pulls",
        blank=True,
        null=True,
    )

    class Meta:
        managed = False
        db_table = "pulls"
        ordering = ["-final_distance"]  # roughly matches order_by in SQLAlchemy

    def __str__(self):
        return f"Pull {self.pull_id} – {self.team} ({self.final_distance or 0:.2f} ft)"


class PullData(models.Model):
    data_id = models.AutoField(primary_key=True)

    pull = models.ForeignKey(
        Pull,
        models.DO_NOTHING,
        db_column="pull_id",
        related_name="pull_data",
    )

    chain_force = models.FloatField(blank=True, null=True)
    speed = models.FloatField(blank=True, null=True)
    distance = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "pull_data"

    def __str__(self):
        return f"PullData {self.data_id} for Pull {self.pull_id}"


class EventTeam(models.Model):
    event_team_id = models.AutoField(primary_key=True)

    event = models.ForeignKey(
        Event,
        models.DO_NOTHING,
        db_column="event_id",
        related_name="event_teams",
    )
    team = models.ForeignKey(
        Team,
        models.DO_NOTHING,
        db_column="team_id",
        related_name="event_teams",
    )

    total_score = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "event_teams"
        ordering = ["-total_score"]

    def __str__(self):
        return f"{self.event} – {self.team} (score {self.total_score})"


class EventTeamPhoto(models.Model):
    event_team_photo_id = models.AutoField(primary_key=True)

    event_team = models.ForeignKey(
        EventTeam,
        models.DO_NOTHING,
        db_column="event_team_id",
        related_name="photos",
    )

    submitted_from_ip = models.CharField(max_length=255, blank=True, null=True)
    # path relative to /static, e.g. "team_photos/iowa_state_2026_1.jpg"
    photo_path = models.CharField(max_length=255)
    caption = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(default=datetime.utcnow)
    approved = models.BooleanField()

    class Meta:
        managed = False
        db_table = "event_team_photos"

    def __str__(self):
        return f"Photo {self.event_team_photo_id} for {self.event_team}"