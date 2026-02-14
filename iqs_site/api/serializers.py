from rest_framework import serializers
from events.models import (
    Event, Team, TeamClass, Tractor, TractorEvent, Hook, Pull, PullData,
    PullMedia, PerformanceEventMedia, TractorMedia, EventTeam,
    EventTeamPhoto, ScheduleItem, ScheduleItemType,
    ScoreCategory, ScoreCategoryInstance, ScoreSubCategory,
    ScoreSubCategoryInstance, ScoreSubCategoryScore,
    DurabilityRun, DurabilityData, ManeuverabilityRun,
    TeamInfo, TractorInfo,
)
from techin.models import (
    RuleCategory, RuleSubCategory, Rule, EventTractorRuleStatus,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _build_info_dict(info_qs):
    """Convert a queryset of TeamInfo/TractorInfo into a flat dict."""
    TYPE_NAMES = {1: "instagram", 2: "facebook", 3: "website", 4: "bio",
                  5: "nickname", 6: "youtube", 7: "linkedin"}
    return {TYPE_NAMES.get(row.info_type, str(row.info_type)): row.info
            for row in info_qs}


# ── Team Class ───────────────────────────────────────────────────────

class TeamClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamClass
        fields = ["team_class_id", "name"]


# ── Events ───────────────────────────────────────────────────────────

class EventListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ["event_id", "event_name", "event_datetime", "event_active"]


class HookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hook
        fields = ["hook_id", "hook_name"]


class ScheduleItemSerializer(serializers.ModelSerializer):
    type_name = serializers.CharField(source="type.name", read_only=True)
    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_id = serializers.IntegerField(source="team.team_id", read_only=True)

    class Meta:
        model = ScheduleItem
        fields = ["schedule_item_id", "datetime", "name", "type_name",
                  "team_name", "team_id"]


class EventDetailSerializer(serializers.ModelSerializer):
    hooks = HookSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = ["event_id", "event_name", "event_datetime", "event_active",
                  "techin_released", "hooks"]


# ── Teams ────────────────────────────────────────────────────────────

class TeamListSerializer(serializers.ModelSerializer):
    team_class = TeamClassSerializer(read_only=True)
    nickname = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ["team_id", "team_name", "team_number",
                  "team_abbreviation", "team_class", "nickname"]

    def get_nickname(self, obj):
        # Uses prefetched info if available, otherwise queries
        info = getattr(obj, "_prefetched_info", None)
        if info is not None:
            for i in info:
                if i.info_type == TeamInfo.InfoTypes.NICKNAME:
                    return i.info
            return None
        ti = TeamInfo.objects.filter(
            team=obj, info_type=TeamInfo.InfoTypes.NICKNAME
        ).values_list("info", flat=True).first()
        return ti


class TeamDetailSerializer(serializers.ModelSerializer):
    team_class = TeamClassSerializer(read_only=True)
    info = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ["team_id", "team_name", "team_number",
                  "team_abbreviation", "team_class", "info"]

    def get_info(self, obj):
        qs = TeamInfo.objects.filter(team=obj)
        return _build_info_dict(qs)


# ── Event Teams (standings) ──────────────────────────────────────────

class EventTeamSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_number = serializers.CharField(source="team.team_number", read_only=True)
    team_abbreviation = serializers.CharField(
        source="team.team_abbreviation", read_only=True)
    team_class = serializers.SerializerMethodField()

    class Meta:
        model = EventTeam
        fields = ["event_team_id", "event_id", "team_id", "total_score",
                  "team_name", "team_number", "team_abbreviation", "team_class"]

    def get_team_class(self, obj):
        tc = getattr(obj.team, "team_class", None)
        if tc:
            return {"team_class_id": tc.team_class_id, "name": tc.name}
        return None


# ── Tractors ─────────────────────────────────────────────────────────

class TractorListSerializer(serializers.ModelSerializer):
    original_team_name = serializers.CharField(
        source="original_team.team_name", default=None, read_only=True)
    primary_photo_url = serializers.SerializerMethodField()
    nickname = serializers.SerializerMethodField()

    class Meta:
        model = Tractor
        fields = ["tractor_id", "tractor_name", "year",
                  "original_team_name", "primary_photo_url", "nickname"]

    def get_primary_photo_url(self, obj):
        if obj.primary_photo and obj.primary_photo.link:
            return obj.primary_photo.link
        return None

    def get_nickname(self, obj):
        # Use annotated value if available
        nick = getattr(obj, "nickname_info", None)
        if nick is not None:
            return nick
        return obj.nickname


class TractorDetailSerializer(serializers.ModelSerializer):
    original_team = TeamListSerializer(read_only=True)
    primary_photo_url = serializers.SerializerMethodField()
    info = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    usages = serializers.SerializerMethodField()

    class Meta:
        model = Tractor
        fields = ["tractor_id", "tractor_name", "year", "original_team",
                  "primary_photo_url", "info", "media", "usages"]

    def get_primary_photo_url(self, obj):
        if obj.primary_photo and obj.primary_photo.link:
            return obj.primary_photo.link
        return None

    def get_info(self, obj):
        qs = TractorInfo.objects.filter(tractor=obj)
        return _build_info_dict(qs)

    def get_media(self, obj):
        qs = TractorMedia.objects.filter(
            tractor=obj, approved=True, media_type=TractorMedia.MediaTypes.IMAGE
        ).order_by("-created_at")
        return [{"media_id": m.media_id, "link": m.link,
                 "caption": m.caption} for m in qs]

    def get_usages(self, obj):
        tes = (TractorEvent.objects
               .filter(tractor=obj)
               .select_related("team", "event")
               .order_by("event__event_datetime"))
        results = []
        for te in tes:
            year = te.event.event_datetime.year if te.event and te.event.event_datetime else None
            results.append({
                "event_id": te.event_id,
                "event_name": te.event.event_name if te.event else None,
                "team_id": te.team_id,
                "team_name": te.team.team_name if te.team else None,
                "year": year,
            })
        return results


# ── Pulls ────────────────────────────────────────────────────────────

class PullListSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_id = serializers.IntegerField(source="team.team_id", read_only=True)
    hook_name = serializers.CharField(source="hook.hook_name", default=None, read_only=True)
    hook_id = serializers.IntegerField(source="hook.hook_id", default=None, read_only=True)
    tractor_name = serializers.CharField(
        source="tractor.tractor_name", default=None, read_only=True)

    class Meta:
        model = Pull
        fields = ["pull_id", "final_distance", "team_name", "team_id",
                  "hook_name", "hook_id", "tractor_name"]


class PullDetailSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_id = serializers.IntegerField(source="team.team_id", read_only=True)
    team_abbreviation = serializers.CharField(
        source="team.team_abbreviation", read_only=True)
    event_name = serializers.CharField(
        source="event.event_name", default=None, read_only=True)
    event_id = serializers.IntegerField(
        source="event.event_id", default=None, read_only=True)
    hook_name = serializers.CharField(
        source="hook.hook_name", default=None, read_only=True)
    tractor_name = serializers.CharField(
        source="tractor.tractor_name", default=None, read_only=True)
    chart_data = serializers.SerializerMethodField()
    videos = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()

    class Meta:
        model = Pull
        fields = ["pull_id", "final_distance", "team_name", "team_id",
                  "team_abbreviation", "event_name", "event_id",
                  "hook_name", "tractor_name", "chart_data",
                  "videos", "photos"]

    def get_chart_data(self, obj):
        data_qs = (PullData.objects
                   .filter(pull=obj)
                   .order_by("distance")
                   .values_list("pull_time", "distance", "speed", "chain_force"))
        times, distances, speeds, forces = [], [], [], []
        for t, d, s, f in data_qs:
            if d is None or s is None or f is None:
                continue
            times.append(float(t) if t else 0)
            distances.append(float(d))
            speeds.append(float(s))
            forces.append(float(f))
        return {
            "times": times,
            "distances": distances,
            "speeds": speeds,
            "forces": forces,
        }

    def get_videos(self, obj):
        # Check PerformanceEventMedia first, fall back to PullMedia
        yt = PerformanceEventMedia.objects.filter(
            performance_event_type=PerformanceEventMedia.EventTypes.PULL,
            performance_event_id=obj.pull_id,
            media_type=PerformanceEventMedia.MediaTypes.YOUTUBE_VIDEO,
        )
        if not yt.exists():
            yt = obj.pull_media.filter(
                pull_media_type=PullMedia.types.YOUTUBE_VIDEO)
        return [{"link": v.link} for v in yt]

    def get_photos(self, obj):
        photos = PerformanceEventMedia.objects.filter(
            performance_event_type=PerformanceEventMedia.EventTypes.PULL,
            performance_event_id=obj.pull_id,
            media_type=PerformanceEventMedia.MediaTypes.IMAGE,
            approved=True,
        ).order_by("-created_at")
        return [{"media_id": p.media_id, "link": p.link,
                 "caption": p.caption} for p in photos]


# ── Durability ───────────────────────────────────────────────────────

class DurabilityRunListSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_id = serializers.IntegerField(source="team.team_id", read_only=True)
    tractor_name = serializers.CharField(
        source="tractor.tractor_name", default=None, read_only=True)

    class Meta:
        model = DurabilityRun
        fields = ["durability_run_id", "run_order", "state", "total_laps",
                  "team_name", "team_id", "tractor_name"]


class DurabilityRunDetailSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_id = serializers.IntegerField(source="team.team_id", read_only=True)
    event_name = serializers.CharField(
        source="event.event_name", default=None, read_only=True)
    event_id = serializers.IntegerField(
        source="event.event_id", default=None, read_only=True)
    tractor_name = serializers.CharField(
        source="tractor.tractor_name", default=None, read_only=True)
    chart_data = serializers.SerializerMethodField()
    videos = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()

    class Meta:
        model = DurabilityRun
        fields = ["durability_run_id", "run_order", "state", "total_laps",
                  "team_name", "team_id", "event_name", "event_id",
                  "tractor_name", "chart_data", "videos", "photos"]

    def get_chart_data(self, obj):
        data_qs = (DurabilityData.objects
                   .filter(durability_run=obj)
                   .order_by("durability_data_id")
                   .only("speed", "pressure", "power"))
        speeds, pressures, powers = [], [], []
        for row in data_qs:
            if row.speed is None or row.pressure is None or row.power is None:
                continue
            speeds.append(float(row.speed))
            pressures.append(float(row.pressure))
            powers.append(float(row.power))

        # Downsample if too many points (same logic as views.py)
        max_points = 5000
        if len(speeds) > max_points:
            step = (len(speeds) // max_points) + 1
            speeds = speeds[::step]
            pressures = pressures[::step]
            powers = powers[::step]

        return {
            "speeds": speeds,
            "pressures": pressures,
            "powers": powers,
        }

    def get_videos(self, obj):
        yt = PerformanceEventMedia.objects.filter(
            performance_event_type=PerformanceEventMedia.EventTypes.DURABILITY,
            performance_event_id=obj.durability_run_id,
            media_type=PerformanceEventMedia.MediaTypes.YOUTUBE_VIDEO,
        )
        return [{"link": v.link} for v in yt]

    def get_photos(self, obj):
        photos = PerformanceEventMedia.objects.filter(
            performance_event_type=PerformanceEventMedia.EventTypes.DURABILITY,
            performance_event_id=obj.durability_run_id,
            media_type=PerformanceEventMedia.MediaTypes.IMAGE,
            approved=True,
        ).order_by("-created_at")
        return [{"media_id": p.media_id, "link": p.link,
                 "caption": p.caption} for p in photos]


# ── Maneuverability ──────────────────────────────────────────────────

class ManeuverabilityRunListSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_id = serializers.IntegerField(source="team.team_id", read_only=True)

    class Meta:
        model = ManeuverabilityRun
        fields = ["maneuverability_run_id", "run_order", "state",
                  "team_name", "team_id"]


class ManeuverabilityRunDetailSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_id = serializers.IntegerField(source="team.team_id", read_only=True)
    event_name = serializers.CharField(
        source="event.event_name", default=None, read_only=True)
    event_id = serializers.IntegerField(
        source="event.event_id", default=None, read_only=True)
    videos = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()

    class Meta:
        model = ManeuverabilityRun
        fields = ["maneuverability_run_id", "run_order", "state",
                  "team_name", "team_id", "event_name", "event_id",
                  "videos", "photos"]

    def get_videos(self, obj):
        yt = PerformanceEventMedia.objects.filter(
            performance_event_type=PerformanceEventMedia.EventTypes.MANEUVERABILITY,
            performance_event_id=obj.maneuverability_run_id,
            media_type=PerformanceEventMedia.MediaTypes.YOUTUBE_VIDEO,
        )
        return [{"link": v.link} for v in yt]

    def get_photos(self, obj):
        photos = PerformanceEventMedia.objects.filter(
            performance_event_type=PerformanceEventMedia.EventTypes.MANEUVERABILITY,
            performance_event_id=obj.maneuverability_run_id,
            media_type=PerformanceEventMedia.MediaTypes.IMAGE,
            approved=True,
        ).order_by("-created_at")
        return [{"media_id": p.media_id, "link": p.link,
                 "caption": p.caption} for p in photos]


# ── Scores ───────────────────────────────────────────────────────────

class ScoreSubCategoryScoreSerializer(serializers.Serializer):
    team_id = serializers.IntegerField(source="team.team_id")
    team_name = serializers.CharField(source="team.team_name")
    subcategory_name = serializers.CharField(
        source="subcategory.score_subcategory.subcategory_name")
    score_subcategory_score_id = serializers.IntegerField()


class EventResultsSerializer(serializers.Serializer):
    """Nested scoring: categories -> subcategories -> team scores."""
    categories = serializers.SerializerMethodField()

    def get_categories(self, event):
        cat_instances = (
            ScoreCategoryInstance.objects
            .filter(event=event, released=True)
            .select_related("score_category")
            .order_by("score_category__category_name")
        )
        result = []
        for ci in cat_instances:
            subcat_instances = (
                ScoreSubCategoryInstance.objects
                .filter(event=event)
                .select_related("score_subcategory")
            )
            subcats = []
            for si in subcat_instances:
                scores = (
                    ScoreSubCategoryScore.objects
                    .filter(subcategory=si)
                    .select_related("team")
                    .order_by("team__team_name")
                )
                subcats.append({
                    "subcategory_name": si.score_subcategory.subcategory_name,
                    "max_points": si.max_points,
                    "released": si.released,
                    "scores": [
                        {"team_id": s.team_id,
                         "team_name": s.team.team_name}
                        for s in scores
                    ],
                })
            result.append({
                "category_name": ci.score_category.category_name,
                "max_points": ci.max_points,
                "subcategories": subcats,
            })
        return result


# ── Photos ───────────────────────────────────────────────────────────

class EventTeamPhotoSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(
        source="event_team.team.team_name", read_only=True)
    event_name = serializers.CharField(
        source="event_team.event.event_name", read_only=True)

    class Meta:
        model = EventTeamPhoto
        fields = ["event_team_photo_id", "photo_path", "caption",
                  "official", "created_at", "team_name", "event_name"]


# ── Team-Event composite ────────────────────────────────────────────

class TeamEventDetailSerializer(serializers.Serializer):
    """Composite view of a team's performance at a specific event."""
    event = EventListSerializer()
    team = TeamListSerializer()
    event_team = EventTeamSerializer(allow_null=True)
    pulls = PullListSerializer(many=True)
    durability_runs = DurabilityRunListSerializer(many=True)
    maneuverability_runs = ManeuverabilityRunListSerializer(many=True)
    photos = EventTeamPhotoSerializer(many=True)
    schedule_items = ScheduleItemSerializer(many=True)


# ── Tech Inspection ──────────────────────────────────────────────────

class RuleStatusSerializer(serializers.Serializer):
    rule_id = serializers.IntegerField(source="rule.rule_id")
    rule_number = serializers.CharField(source="rule.rule_number")
    rule_content = serializers.CharField(source="rule.rule_content")
    status = serializers.IntegerField()
    status_label = serializers.SerializerMethodField()

    STATUS_MAP = {0: "Not Started", 1: "Failed", 2: "Corrected", 3: "Pass"}

    def get_status_label(self, obj):
        return self.STATUS_MAP.get(obj.status, "Unknown")


class TechinTeamOverviewSerializer(serializers.Serializer):
    """Per-team tech inspection progress."""
    team_id = serializers.IntegerField()
    team_name = serializers.CharField()
    categories = serializers.ListField()


# ── Auth ─────────────────────────────────────────────────────────────

class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    teams = serializers.SerializerMethodField()

    def get_teams(self, user):
        from users.models import GroupProfile
        profiles = GroupProfile.objects.filter(
            group__in=user.groups.all()
        ).select_related("team")
        result = []
        for gp in profiles:
            if gp.team:
                result.append({
                    "team_id": gp.team.team_id,
                    "team_name": gp.team.team_name,
                    "is_admin": gp.admins.filter(pk=user.pk).exists(),
                })
        return result


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
