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
    event_active = models.BooleanField(blank=False,null=False)
    techin_released = models.BooleanField(blank=False,null=False)
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
    
    def  get_absolute_url(self):
        return f"/event/{self.event_id}"


class Team(models.Model):
    team_id = models.AutoField(primary_key=True,db_column="team_id")
    team_name = models.CharField(max_length=255)
    team_number = models.CharField(max_length=255)
    team_abbreviation=models.CharField(max_length=255)
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
    
    def get_absolute_url(self):
        return f"/teams/{self.team_id}"


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
    year=models.IntegerField()
    # tractor_events M2M via explicit through model is handled below

    class Meta:
        managed = False
        db_table = "tractors"

    def __str__(self):
        return self.tractor_name or f"Tractor {self.tractor_id}"
    
    def get_absolute_url(self):
        return f"/tractors/{self.tractor_id}"
    
    @property
    def nickname(self) -> str | None:
        # If you add related_name="infos" to the FK, use self.infos.filter(...)
        ti = TractorInfo.objects.filter(
            tractor=self,
            info_type=TractorInfo.InfoTypes.NICKNAME,
        ).only("info").first()
        return ti.info if ti and ti.info else None

    @property
    def display_name(self) -> str:
        return self.nickname or self.tractor_name  # replace tractor_name with your real field


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
    
class PullMedia(models.Model):
    pull_media_id=models.AutoField(primary_key=True)
    pull=models.ForeignKey(
        Pull,
        models.DO_NOTHING,
        db_column="pull_id",
        related_name="pull_media",
        blank=True,
        null=True
    )
    class types(models.IntegerChoices):
        YOUTUBE_VIDEO=1
        IMAGE=2

    class Meta:
        managed = False
        db_table = "pull_media"

    pull_media_type=models.IntegerField(choices=types)
    link=models.CharField(max_length=255)

class PerformanceEventMedia(models.Model):
    media_id = models.AutoField(primary_key=True)

    class EventTypes(models.IntegerChoices):
        PULL = 1, "Pull"
        MANEUVERABILITY = 2, "Maneuverability"
        DURABILITY = 3, "Durability"

    class MediaTypes(models.IntegerChoices):
        YOUTUBE_VIDEO = PullMedia.types.YOUTUBE_VIDEO
        IMAGE = PullMedia.types.IMAGE

    media_type = models.IntegerField(choices=MediaTypes.choices, blank=True, null=True)
    link = models.CharField(max_length=255, blank=True, null=True)
    performance_event_id = models.IntegerField(blank=True, null=True)
    performance_event_type = models.IntegerField(choices=EventTypes.choices, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "performance_event_media"




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
    
    def get_absolute_url(self):
        return f"/team-event/{self.event.event_id}/{self.team.team_id}"


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
        
        permissions = [
            ("can_auto_approve_team_photos", "Can auto-approve uploaded team photos"),
        ]

    def __str__(self):
        return f"Photo {self.event_team_photo_id} for {self.event_team}"
    
class ScheduleItemType(models.Model):
    schedule_item_type_id=models.AutoField(primary_key=True)
    name=models.CharField(max_length=45)

    class Meta:
        managed=False
        db_table="schedule_item_types"



class ScheduleItem(models.Model):
    schedule_item_id=models.AutoField(primary_key=True)
    datetime=models.DateTimeField()
    name=models.CharField(max_length=45)
    type=models.ForeignKey(
        ScheduleItemType,
        models.DO_NOTHING,
        db_column="type",
        related_name="items"
    )
    team=models.ForeignKey(
        Team,
        models.DO_NOTHING,
        db_column="team",
        related_name="schedule_items"
    )
    event=models.ForeignKey(
        Event,
        models.DO_NOTHING,
        db_column="event",
        related_name="schedule_items"
    )
    class Meta:
        managed=False
        db_table="schedule_items"

class ScoreCategory(models.Model):
    score_category_id=models.AutoField(primary_key=True)
    category_name=models.CharField(max_length=45)

    def __str__(self):
        return self.category_name

    class Meta:
        managed=False
        db_table="score_categories"

class ScoreSubCategory(models.Model):
    score_subcategory_id=models.AutoField(primary_key=True)
    subcategory_name=models.CharField(max_length=45)

    def __str__(self):
        return self.subcategory_name

    class Meta:
        managed=False
        db_table="score_subcategories"

class ScoreCategoryInstance(models.Model):
    score_category_instance_id=models.AutoField(primary_key=True)
    score_category=models.ForeignKey(ScoreCategory,models.DO_NOTHING,db_column="score_category_id",related_name="instances")
    event=models.ForeignKey(Event,models.DO_NOTHING,db_column="event_id",related_name="score_category_instances",to_field="event_id",)
    max_points=models.IntegerField()
    released=models.BooleanField()
    def __str__(self):
        return f"{self.event} - {self.score_category}"
    class Meta:
        managed=False
        db_table="score_category_instances"

class ScoreSubCategoryInstance(models.Model):
    score_subcategory_instance_id=models.AutoField(primary_key=True)
    score_subcategory=models.ForeignKey(ScoreSubCategory,models.DO_NOTHING,db_column="score_subcategory_id",related_name="instances")
    event=models.ForeignKey(Event,models.DO_NOTHING,db_column="event_id",related_name="score_subcategory_instances")
    max_points=models.IntegerField()
    released=models.BooleanField()

    def __str__(self):
        return f"{self.event} - {self.score_subcategory}"
    class Meta:
        managed=False
        db_table="score_subcategory_instances"

class ScoreSubCategoryScore(models.Model):
    score_subcategory_score_id=models.AutoField(primary_key=True)
    team=models.ForeignKey(Team,models.DO_NOTHING,db_column="team_id",related_name="event_score_subcategory_scores")
    subcategory=models.ForeignKey(ScoreSubCategoryInstance,models.DO_NOTHING,db_column="subcategory_instance_id",related_name="team_scores")
    def __str__(self):
        return f"{self.team} → {self.subcategory}"
    
    class Meta:
        managed=False
        db_table="score_subcategory_scores"

class DurabilityRun(models.Model):
    durability_run_id = models.AutoField(primary_key=True)

    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        db_column="event_id",
        to_field="event_id",
        related_name="durability_runs",
        db_constraint=False,
    )

    team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        db_column="team_id",
        to_field="team_id",
        related_name="durability_runs",
        db_constraint=False,
    )

    run_order = models.IntegerField()

    state = models.CharField(
        max_length=24,
        default="SCHEDULED",
    )

    updated_at = models.DateTimeField()

    updated_by_source = models.CharField(
        max_length=16,
        default="system",
    )

    total_laps = models.IntegerField(
        blank=True,
        null=True,
        default=0,
        db_column="total_laps",
    )

    tractor = models.ForeignKey(
        Tractor,
        on_delete=models.PROTECT,
        db_column="tractor_id",
        to_field="tractor_id",
        related_name="durability_runs",
        db_constraint=False,
        blank=True,
        null=True,
    )

    class Meta:
        managed = False
        db_table = "durability_runs"
        indexes = [
            models.Index(fields=["event", "run_order"]),
            models.Index(fields=["event", "team"]),
            models.Index(fields=["event", "state", "run_order"]),
        ]

    def __str__(self):
        return f"DurabilityRun(event={self.event_id}, team={self.team_id}, run_order={self.run_order})"

class DurabilityData(models.Model):
    
    durability_data_id=models.AutoField(primary_key=True)
    durability_run=models.ForeignKey(
        DurabilityRun,
        on_delete=models.PROTECT,
        db_column="durability_run_id",
        to_field="durability_run_id",
        related_name="data",
        db_constraint=False,
    )
    speed=models.FloatField()
    pressure=models.FloatField()
    power=models.FloatField()
    class Meta:
        managed = False
        db_table = "durability_data"
        indexes = [
            models.Index(fields=["durability_run"]),
        ]

class ManeuverabilityRun(models.Model):
    maneuverability_run_id = models.AutoField(primary_key=True)

    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        db_column="event_id",
        to_field="event_id",
        related_name="maneuverability_runs",
        db_constraint=False,
    )

    team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        db_column="team_id",
        to_field="team_id",
        related_name="maneuverability_runs",
        db_constraint=False,
    )

    run_order = models.IntegerField()

    state = models.CharField(
        max_length=24,
        default="SCHEDULED",
    )

    updated_at = models.DateTimeField()

    updated_by_source = models.CharField(
        max_length=16,
        default="system",
    )

    class Meta:
        managed = False
        db_table = "maneuverability_runs"
        indexes = [
            models.Index(fields=["event", "run_order"]),
            models.Index(fields=["event", "team"]),
            models.Index(fields=["event", "state", "run_order"]),
        ]

    def __str__(self):
        return f"ManeuverabilityRun(event={self.event_id}, team={self.team_id}, run_order={self.run_order})"

class TeamInfo(models.Model):
    class InfoTypes(models.IntegerChoices):
        INSTAGRAM=1
        FACEBOOK=2
        WEBSITE=3
        BIO=4
        NICKNAME=5
        YOUTUBE=6
        LINKEDIN=7
    team_info_id=models.AutoField(primary_key=True)

    info_type=models.IntegerField(choices=InfoTypes.choices)
    team=models.ForeignKey(Team,models.DO_NOTHING,db_column="team_id",to_field="team_id")
    info=models.CharField(max_length=255)
    class Meta:
        managed = False
        db_table = "team_info"

class TractorInfo(models.Model):
    class InfoTypes(models.IntegerChoices):
        INSTAGRAM=1
        FACEBOOK=2
        WEBSITE=3
        BIO=4
        NICKNAME=5
        YOUTUBE=6
        LINKEDIN=7
    tractor_info_id=models.AutoField(primary_key=True)

    info_type=models.IntegerField(choices=InfoTypes.choices)
    tractor=models.ForeignKey(Tractor,models.DO_NOTHING,db_column="tractor_id",to_field="tractor_id")
    info=models.CharField(max_length=255)
    class Meta:
        managed = False
        db_table = "tractor_info"
