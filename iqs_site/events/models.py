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
    event_active = models.BooleanField(blank=True, null=True)
    techin_released = models.BooleanField(blank=True, null=True)
    scores_released = models.BooleanField(default=False)
    enabled = models.BooleanField(blank=True, null=True)
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
        permissions = [
            ("can_edit_any_team", "Can edit any team"),
        ]

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

    # Primary photo for this tractor
    primary_photo = models.ForeignKey(
        "TractorMedia",
        models.SET_NULL,
        db_column="primary_photo_media_id",
        blank=True,
        null=True,
        related_name="primary_for_tractors",
    )
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


# DDL (managed=False — must be applied manually):
#   ALTER TABLE hooks ADD COLUMN start_time DATETIME NULL;
#   ALTER TABLE hooks ADD COLUMN end_time   DATETIME NULL;
class Hook(models.Model):
    hook_id = models.AutoField(primary_key=True)
    event = models.ForeignKey(
        Event,
        models.DO_NOTHING,
        db_column="event_id",
        related_name="hooks",
    )
    hook_name = models.CharField(max_length=255, blank=True, null=True)
    start_time = models.DateTimeField(blank=True, null=True)
    end_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "hooks"

    def __str__(self):
        return f"Hook {self.hook_id} (Event {self.event_id})"


# DDL (managed=False — must be applied manually):
#   ALTER TABLE pulls ADD COLUMN expected_start_time INT NULL;
#   CREATE INDEX ix_pulls_hook_run_order ON pulls (hook_id, run_order);
#   CREATE INDEX ix_pulls_hook_state     ON pulls (hook_id, state);
# (state, start_time, end_time, top_speed, updated_at, updated_by_source
# already exist on the DB table; this model now exposes them.)
class Pull(models.Model):
    class States(models.TextChoices):
        SCHEDULED = "SCHEDULED"
        RUNNING = "RUNNING"
        COMPLETED = "COMPLETED"
        SCRATCHED = "SCRATCHED"

    pull_id = models.AutoField(primary_key=True)
    final_distance = models.FloatField(blank=True, null=True)
    top_speed = models.FloatField(blank=True, null=True)

    # All three are unix epoch seconds.
    start_time = models.IntegerField(blank=True, null=True)
    end_time = models.IntegerField(blank=True, null=True)
    expected_start_time = models.IntegerField(blank=True, null=True)

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
    run_order = models.IntegerField(default=0)
    state = models.CharField(
        max_length=24,
        choices=States.choices,
        default=States.SCHEDULED,
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by_source = models.CharField(max_length=16, default="system")

    # Default ordering is by leaderboard rank (-final_distance). Run-sheet
    # views must call .order_by("run_order") explicitly.
    class Meta:
        managed = False
        db_table = "pulls"
        ordering = ["-final_distance"]

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
    caption = models.CharField(max_length=255, blank=True, null=True)
    approved = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(
        "auth.User",
        models.DO_NOTHING,
        db_column="uploaded_by_user_id",
        related_name="uploaded_performance_media",
        blank=True,
        null=True,
    )
    submitted_from_ip = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(default=datetime.utcnow)

    class Meta:
        managed = False
        db_table = "performance_event_media"
        permissions = [
            ("can_auto_approve_performance_media", "Can auto-approve uploaded performance event media"),
        ]


class TractorMedia(models.Model):
    media_id = models.AutoField(primary_key=True)

    class MediaTypes(models.IntegerChoices):
        YOUTUBE_VIDEO = 1
        IMAGE = 2

    media_type = models.IntegerField(choices=MediaTypes.choices, blank=True, null=True)
    link = models.CharField(max_length=255, blank=True, null=True)  # URL or file path

    tractor = models.ForeignKey(
        Tractor,
        models.DO_NOTHING,
        db_column="tractor_id",
        related_name="media",
        blank=True,
        null=True,
    )

    uploaded_by = models.ForeignKey(
        "auth.User",
        models.DO_NOTHING,
        db_column="uploaded_by_user_id",
        related_name="uploaded_tractor_media",
        blank=True,
        null=True,
    )

    caption = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(default=datetime.utcnow)
    approved = models.BooleanField(default=False)
    submitted_from_ip = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "tractor_media"
        permissions = [
            ("can_auto_approve_tractor_media", "Can auto-approve uploaded tractor media"),
        ]

    def __str__(self):
        return f"Media {self.media_id} ({self.get_media_type_display()}) for {self.tractor}"


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
    pull_time = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "pull_data"

    def __str__(self):
        return f"PullData {self.data_id} for Pull {self.pull_id}"


class PullExportJob(models.Model):
    class Statuses(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    pull_export_job_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        "auth.User",
        models.DO_NOTHING,
        db_column="user_id",
        related_name="pull_export_jobs",
    )
    status = models.CharField(max_length=20, choices=Statuses.choices)
    filters_json = models.TextField(blank=True, null=True)
    total_pulls = models.IntegerField(blank=True, null=True)
    processed_pulls = models.IntegerField(blank=True, null=True)
    zip_rel_path = models.CharField(max_length=255, blank=True, null=True)
    download_url = models.CharField(max_length=500, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    task_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField()
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "pull_export_jobs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"PullExportJob #{self.pull_export_job_id} ({self.status})"


class PullExportJobItem(models.Model):
    pull_export_job_item_id = models.AutoField(primary_key=True)
    pull_export_job = models.ForeignKey(
        PullExportJob,
        models.DO_NOTHING,
        db_column="pull_export_job_id",
        related_name="items",
    )
    pull = models.ForeignKey(
        Pull,
        models.DO_NOTHING,
        db_column="pull_id",
        related_name="export_job_items",
    )

    class Meta:
        managed = False
        db_table = "pull_export_job_items"
        constraints = [
            models.UniqueConstraint(
                fields=["pull_export_job", "pull"],
                name="uniq_pull_export_job_item",
            )
        ]
        indexes = [
            models.Index(fields=["pull_export_job"]),
            models.Index(fields=["pull"]),
        ]

    def __str__(self):
        return f"PullExportJobItem #{self.pull_export_job_item_id}"


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
    official = models.BooleanField(default=False)

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
    
class ScoreCategory(models.Model):
    score_category_id=models.AutoField(primary_key=True)
    category_name=models.CharField(max_length=45)

    def __str__(self):
        return self.category_name

    class Meta:
        managed=True
        db_table="score_categories"

class ScoreSubCategory(models.Model):
    score_subcategory_id=models.AutoField(primary_key=True)
    subcategory_name=models.CharField(max_length=45)

    def __str__(self):
        return self.subcategory_name

    class Meta:
        managed=True
        db_table="score_subcategories"

class ScoreCategoryInstance(models.Model):
    score_category_instance_id=models.AutoField(primary_key=True)
    score_category=models.ForeignKey(ScoreCategory,models.DO_NOTHING,db_column="score_category_id",related_name="instances")
    event=models.ForeignKey(Event,models.DO_NOTHING,db_column="event_id",related_name="score_category_instances",to_field="event_id",)
    max_points=models.IntegerField()
    released=models.BooleanField()
    display_order=models.IntegerField(default=0)
    def __str__(self):
        return f"{self.event} - {self.score_category}"
    class Meta:
        managed=True
        db_table="score_category_instances"

class ScoreSubCategoryInstance(models.Model):
    score_subcategory_instance_id=models.AutoField(primary_key=True)
    score_subcategory=models.ForeignKey(ScoreSubCategory,models.DO_NOTHING,db_column="score_subcategory_id",related_name="instances")
    event=models.ForeignKey(Event,models.DO_NOTHING,db_column="event_id",related_name="score_subcategory_instances")
    max_points=models.IntegerField()
    released=models.BooleanField()
    category_instance=models.ForeignKey(
        ScoreCategoryInstance,
        models.DO_NOTHING,
        db_column="category_instance_id",
        related_name="subcategory_instances",
        null=True,
        blank=True,
        db_constraint=False,
    )

    def __str__(self):
        return f"{self.event} - {self.score_subcategory}"
    class Meta:
        managed=True
        db_table="score_subcategory_instances"

class ScoreSubCategoryScore(models.Model):
    score_subcategory_score_id=models.AutoField(primary_key=True)
    team=models.ForeignKey(Team,models.DO_NOTHING,db_column="team_id",related_name="event_score_subcategory_scores")
    subcategory=models.ForeignKey(ScoreSubCategoryInstance,models.DO_NOTHING,db_column="subcategory_instance_id",related_name="team_scores")
    score=models.FloatField(null=True,blank=True)
    def __str__(self):
        return f"{self.team} → {self.subcategory}"

    class Meta:
        managed=True
        db_table="score_subcategory_scores"

class ScoreCategoryScore(models.Model):
    score_category_score_id=models.AutoField(primary_key=True)
    team=models.ForeignKey(Team,models.DO_NOTHING,db_column="team_id",related_name="category_scores",db_constraint=False)
    category_instance=models.ForeignKey(ScoreCategoryInstance,models.DO_NOTHING,db_column="category_instance_id",related_name="team_scores",db_constraint=False)
    score=models.FloatField()

    def __str__(self):
        return f"{self.team} → {self.category_instance} ({self.score})"

    class Meta:
        managed=True
        db_table="score_category_scores"
        unique_together=[["team","category_instance"]]

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
    # Completed-lap count at the time this row was recorded (from the lap_counter).
    lap_count=models.IntegerField(blank=True, null=True, default=0)
    # Durability countdown remaining (seconds, clamped at 0) at record time.
    time_remaining=models.FloatField(blank=True, null=True, default=0)
    class Meta:
        managed = False
        db_table = "durability_data"
        indexes = [
            models.Index(fields=["durability_run"]),
        ]

class EngineData(models.Model):
    # Engine telemetry sampled continuously while any event (pull or durability)
    # is active. Each row links to whichever run was live when it was recorded;
    # the other foreign key is null.
    engine_data_id = models.AutoField(primary_key=True)

    time = models.FloatField(blank=True, null=True)

    pull = models.ForeignKey(
        Pull,
        on_delete=models.PROTECT,
        db_column="pull_id",
        to_field="pull_id",
        related_name="engine_data",
        db_constraint=False,
        blank=True,
        null=True,
    )
    durability_run = models.ForeignKey(
        DurabilityRun,
        on_delete=models.PROTECT,
        db_column="durability_run_id",
        to_field="durability_run_id",
        related_name="engine_data",
        db_constraint=False,
        blank=True,
        null=True,
    )

    eng_speed = models.FloatField(blank=True, null=True)
    eng_percent_torque = models.FloatField(blank=True, null=True)
    coolant_temp = models.FloatField(blank=True, null=True)
    oil_press = models.FloatField(blank=True, null=True)
    oil_temp = models.FloatField(blank=True, null=True)
    fuel_rate = models.FloatField(blank=True, null=True)
    turbo_boost_press = models.FloatField(blank=True, null=True)
    throttle_pos = models.FloatField(blank=True, null=True)
    percent_load = models.FloatField(blank=True, null=True)
    fuel_level = models.FloatField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = "engine_data"
        indexes = [
            models.Index(fields=["pull"]),
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
        LOGO=8
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


class EditLog(models.Model):
    edit_log_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        'auth.User', models.SET_NULL, null=True, blank=True,
        related_name='edit_logs'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    entity_type = models.CharField(max_length=30)
    team = models.ForeignKey(
        Team, models.SET_NULL, null=True, blank=True,
        db_column='team_id', to_field='team_id',
        related_name='edit_logs', db_constraint=False,
    )
    tractor = models.ForeignKey(
        Tractor, models.SET_NULL, null=True, blank=True,
        db_column='tractor_id', to_field='tractor_id',
        related_name='edit_logs', db_constraint=False,
    )
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'edit_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['team', '-timestamp']),
            models.Index(fields=['tractor', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
        ]

    def __str__(self):
        target = self.team or self.tractor
        return f"{self.user} changed {self.field_name} on {target} at {self.timestamp}"

class Report(models.Model):
    report_id=models.AutoField(primary_key=True)
    report_type=models.IntegerField()
    event_team = models.ForeignKey(
        EventTeam,
        models.DO_NOTHING,
        db_column="event_team_id",
        related_name="reports",
    )
    report_link=models.CharField(max_length=255)
    released=models.BooleanField(default=False)

    class Meta:
        db_table = 'reports'


class ScoreSheetSubmission(models.Model):
    submission_id = models.AutoField(primary_key=True)
    file_path = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    submitted_from_ip = models.CharField(max_length=255, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(default=datetime.utcnow)

    class Meta:
        managed = True
        db_table = "score_sheet_submissions"

    def __str__(self):
        return f"ScoreSheet {self.submission_id} — {self.original_filename}"
        
