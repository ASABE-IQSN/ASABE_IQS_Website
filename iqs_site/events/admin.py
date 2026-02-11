from django.contrib import admin, messages
from django.conf import settings
from django.utils.html import format_html
from django import forms
from .models import (
    TeamClass,
    Team,
    Tractor,
    TractorEvent,
    Event,
    Hook,
    Pull,
    PullData,
    EventTeam,
    EventTeamPhoto,
    ScheduleItem,
    ScheduleItemType,
    TractorMedia,
)
from .models import (
    ScoreCategory,
    ScoreSubCategory,
    ScoreCategoryInstance,
    ScoreSubCategoryInstance,
    ScoreSubCategoryScore,
    EditLog,
)
from django.db.models import Q


@admin.register(TeamClass)
class TeamClassAdmin(admin.ModelAdmin):
    list_display = ("team_class_id", "name")
    search_fields = ("name",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("team_id", "team_name", "team_number", "team_class")
    list_filter = ("team_class",)
    search_fields = ("team_name", "team_number")


@admin.register(Tractor)
class TractorAdmin(admin.ModelAdmin):
    list_display = ("tractor_id", "tractor_name", "original_team", "year", "primary_photo")
    search_fields = ("tractor_name",)
    list_filter = ("year", "original_team")
    raw_id_fields = ("primary_photo",)


class EventForm(forms.ModelForm):
    event_id = forms.IntegerField(required=False, label="Event ID")

    class Meta:
        model = Event
        fields = ["event_id", "event_name", "event_datetime", "event_active", "techin_released"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventForm
    list_display = ("event_id", "event_name", "event_datetime")
    search_fields = ("event_name",)
    list_filter = ("event_datetime",)

    fields = ("event_id", "event_name", "event_datetime", "event_active", "techin_released")

    def get_readonly_fields(self, request, obj=None):
        # Make event_id readonly when editing an existing event, but editable when creating new one
        if obj:  # Editing an existing object
            return ("event_id",)
        return ()  # Creating a new object


@admin.register(ScheduleItemType)
class ScheduleItemTypeAdmin(admin.ModelAdmin):
    list_display = ("schedule_item_type_id", "name")
    search_fields = ("name",)


@admin.register(ScheduleItem)
class ScheduleItemAdmin(admin.ModelAdmin):
    list_display = ("schedule_item_id", "name", "datetime", "type", "team", "event")
    list_filter = ("event", "type", "datetime")
    search_fields = ("name", "team__team_name", "team__team_number", "event__event_name")
    date_hierarchy = "datetime"


@admin.register(Hook)
class HookAdmin(admin.ModelAdmin):
    list_display = ("hook_id", "hook_name", "event")
    search_fields = ("hook_name",)
    list_filter = ("event",)


@admin.register(Pull)
class PullAdmin(admin.ModelAdmin):
    list_display = ("pull_id", "team", "event", "hook", "tractor", "final_distance")
    list_filter = ("event", "hook", "tractor")
    search_fields = ("team__team_name", "team__team_number")


@admin.register(PullData)
class PullDataAdmin(admin.ModelAdmin):
    list_display = ("data_id", "pull", "distance", "speed", "chain_force")
    list_filter = ("pull",)


@admin.register(EventTeam)
class EventTeamAdmin(admin.ModelAdmin):
    list_display = ("event_team_id", "event", "team", "total_score")
    list_filter = ("event",)
    search_fields = ("team__team_name", "team__team_number")


@admin.register(EventTeamPhoto)
class EventTeamPhotoAdmin(admin.ModelAdmin):
    list_display = ("event_team_photo_id", "event_team", "approved", "created_at", "photo_preview")
    list_filter = ("approved", "created_at")
    search_fields = ("photo_path",)

    readonly_fields = ("photo_preview",)

    fields = (
        "event_team",
        "photo_path",
        "caption",
        "approved",
        "submitted_from_ip",
        "created_at",
        "photo_preview",
    )

    actions = ["approve_photos", "unapprove_photos"]

    @admin.action(description="Approve selected photos")
    def approve_photos(self, request, queryset):
        updated = queryset.filter(approved=False).update(approved=True)
        self.message_user(request, f"Approved {updated} photo(s).", level=messages.SUCCESS)

    @admin.action(description="Unapprove selected photos")
    def unapprove_photos(self, request, queryset):
        updated = queryset.filter(approved=True).update(approved=False)
        self.message_user(request, f"Unapproved {updated} photo(s).", level=messages.WARNING)

    def photo_preview(self, obj):
        if not obj.photo_path:
            return "(no image)"

        # photo_path is relative to /static, e.g. "team_photos/foo.jpg"
        # Build the URL that will actually serve it
        url = "http://iqsconnect.org/static/" + obj.photo_path.lstrip("/")#settings.STATIC_URL + obj.photo_path.lstrip("/")

        return format_html(
            '<img src="{}" style="max-width: 400px; max-height: 300px; border-radius: 8px; border: 1px solid #1f2937;" />',
            url,
        )

    photo_preview.short_description = "Preview"

class TractorEventInline(admin.TabularInline):
    model = TractorEvent
    extra = 0
    raw_id_fields = ("tractor", "team", "event")


# ----- TractorEvent admin -----

@admin.register(TractorEvent)
class TractorEventAdmin(admin.ModelAdmin):
    list_display = ("tractor_event_id", "tractor", "team", "event")
    list_filter = ("event", "team", "tractor")
    search_fields = (
        "tractor__tractor_name",
        "team__team_name",
        "event__event_name",
    )

@admin.register(ScoreCategory)
class ScoreCategoryAdmin(admin.ModelAdmin):
    list_display = ("score_category_id", "category_name")
    search_fields = ("category_name",)
    ordering = ("category_name",)

@admin.register(ScoreSubCategory)
class ScoreSubCategoryAdmin(admin.ModelAdmin):
    list_display = ("score_subcategory_id", "subcategory_name")
    search_fields = ("subcategory_name",)
    ordering = ("subcategory_name",)

@admin.register(ScoreCategoryInstance)
class ScoreCategoryInstanceAdmin(admin.ModelAdmin):
    list_display = (
        "score_category_instance_id",
        "score_category",
        "event",
        "max_points",
        "released",
    )

    list_filter = ("released", "event", "score_category")
    search_fields = ("score_category__category_name", "event__event_name")

    ordering = ("event", "score_category")

@admin.register(ScoreSubCategoryInstance)
class ScoreSubCategoryInstanceAdmin(admin.ModelAdmin):
    list_display = (
        "score_subcategory_instance_id",
        "score_subcategory",
        "event",
        "max_points",
        "released",
    )

    list_filter = ("released", "event", "score_subcategory")
    search_fields = ("score_subcategory__subcategory_name", "event__event_name")

    ordering = ("event", "score_subcategory")

@admin.register(ScoreSubCategoryScore)
class ScoreSubCategoryScoreAdmin(admin.ModelAdmin):
    list_display = (
        "score_subcategory_score_id",
        "team",
        "subcategory",
    )

    list_filter = ("team", "subcategory__event")
    search_fields = (
        "team__team_name",
        "subcategory__score_subcategory__subcategory_name",
        "subcategory__event__event_name",
    )

    ordering = ("subcategory__event", "team")


from .models import DurabilityRun, DurabilityData, PerformanceEventMedia


@admin.register(DurabilityRun)
class DurabilityRunAdmin(admin.ModelAdmin):
    list_display = (
        "durability_run_id",
        "event",
        "team",
        "run_order",
        "state",
        "total_laps",
        "tractor",
        "updated_at",
    )
    list_filter = (
        "state",
        "event",
    )
    search_fields = (
        "team__team_name",
        "team__team_number",
        "team__team_abbreviation",
        "tractor__tractor_name",
        "event__event_name",
    )
    ordering = ("event", "run_order")
    date_hierarchy = "updated_at"

    fields = (
        "event",
        "team",
        "run_order",
        "state",
        "total_laps",
        "tractor",
        "updated_at",
        "updated_by_source",
    )
    readonly_fields = ("updated_at",)

    autocomplete_fields = ("event", "team", "tractor")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("event", "team", "tractor")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Optional quality-of-life:
        - In the add form, if event is selected via ?event_id=25 in the URL,
          pre-filter Team/Tractor dropdowns to those that participated in that event
          (via TractorEvent).
        """
        if db_field.name in ("team", "tractor"):
            event_id = request.GET.get("event") or request.GET.get("event_id")
            if event_id:
                try:
                    event_id_int = int(event_id)
                except (TypeError, ValueError):
                    event_id_int = None

                if event_id_int:
                    if db_field.name == "team":
                        # teams that appeared in tractor_events for this event
                        kwargs["queryset"] = kwargs["queryset"].filter(
                            Q(tractor_events__event__event_id=event_id_int)
                        ).distinct()
                    else:
                        # tractors that appeared in tractor_events for this event
                        kwargs["queryset"] = kwargs["queryset"].filter(
                            Q(tractor_events__event__event_id=event_id_int)
                        ).distinct()

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(DurabilityData)
class DurabilityDataAdmin(admin.ModelAdmin):
    list_display = (
        "durability_data_id",
        "durability_run",
        "speed",
        "pressure",
        "power",
    )
    list_filter = ("durability_run",)
    search_fields = (
        "durability_run__team__team_name",
        "durability_run__team__team_number",
        "durability_run__tractor__tractor_name",
        "durability_run__event__event_name",
    )
    ordering = ("durability_data_id",)


@admin.register(PerformanceEventMedia)
class PerformanceEventMediaAdmin(admin.ModelAdmin):
    list_display = (
        "media_id",
        "media_type",
        "performance_event_type",
        "performance_event_id",
        "link",
    )
    list_filter = ("media_type", "performance_event_type")
    search_fields = (
        "link",
    )
    ordering = ("media_id",)


@admin.register(TractorMedia)
class TractorMediaAdmin(admin.ModelAdmin):
    list_display = ("media_id", "tractor", "media_type", "uploaded_by", "approved", "created_at", "media_preview")
    list_filter = ("media_type", "approved", "created_at")
    search_fields = ("tractor__tractor_name", "link", "caption", "uploaded_by__username")
    readonly_fields = ("media_preview",)

    actions = ["approve_media", "unapprove_media"]

    @admin.action(description="Approve selected media")
    def approve_media(self, request, queryset):
        updated = queryset.filter(approved=False).update(approved=True)
        self.message_user(request, f"Approved {updated} media item(s).", level=messages.SUCCESS)

    @admin.action(description="Unapprove selected media")
    def unapprove_media(self, request, queryset):
        updated = queryset.filter(approved=True).update(approved=False)
        self.message_user(request, f"Unapproved {updated} media item(s).", level=messages.WARNING)

    def media_preview(self, obj):
        if obj.media_type == TractorMedia.MediaTypes.IMAGE:
            if not obj.link:
                return "(no image)"
            url = "http://iqsconnect.org/static/" + obj.link.lstrip("/")
            return format_html(
                '<img src="{}" style="max-width: 400px; max-height: 300px; border-radius: 8px;" />',
                url,
            )
        elif obj.media_type == TractorMedia.MediaTypes.YOUTUBE_VIDEO:
            return format_html('<a href="{}" target="_blank">View Video</a>', obj.link)
        return "(unknown media type)"

    media_preview.short_description = "Preview"


@admin.register(EditLog)
class EditLogAdmin(admin.ModelAdmin):
    list_display = ('edit_log_id', 'timestamp', 'user', 'entity_type', 'team', 'tractor', 'field_name')
    list_filter = ('entity_type', 'timestamp', 'user')
    search_fields = ('user__username', 'field_name', 'old_value', 'new_value')
    readonly_fields = ('edit_log_id', 'timestamp', 'user', 'entity_type', 'team', 'tractor', 'field_name', 'old_value', 'new_value')
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
