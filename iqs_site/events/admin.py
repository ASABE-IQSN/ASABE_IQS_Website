from django.contrib import admin, messages
from django.conf import settings
from django.utils.html import format_html
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
)
from .models import (
    ScoreCategory,
    ScoreSubCategory,
    ScoreCategoryInstance,
    ScoreSubCategoryInstance,
    ScoreSubCategoryScore,
)


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
    list_display = ("tractor_id", "tractor_name", "original_team")
    search_fields = ("tractor_name",)
    list_filter = ("original_team",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_name", "event_datetime")
    search_fields = ("event_name",)
    list_filter = ("event_datetime",)


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
