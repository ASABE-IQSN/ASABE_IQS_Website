from django.contrib import admin

from .models import (
    Location,
    ScheduleItem,
    ScheduleItemType,
    ScheduleNotification,
    ScheduleSubscription,
)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("location_id", "name", "event", "icon_category", "latitude", "longitude")
    list_filter = ("event", "icon_category")
    search_fields = ("name", "address", "description")
    raw_id_fields = ("event",)


@admin.register(ScheduleItemType)
class ScheduleItemTypeAdmin(admin.ModelAdmin):
    list_display = ("schedule_item_type_id", "name")
    search_fields = ("name",)


@admin.register(ScheduleItem)
class ScheduleItemAdmin(admin.ModelAdmin):
    list_display = ("schedule_item_id", "name", "datetime", "type", "team", "event", "location")
    list_filter = ("event", "type", "datetime")
    search_fields = ("name", "team__team_name", "team__team_number", "event__event_name")
    date_hierarchy = "datetime"
    raw_id_fields = ("location",)


@admin.register(ScheduleSubscription)
class ScheduleSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("subscription_id", "user", "team", "schedule_item_type", "created_at")
    list_filter = ("team", "schedule_item_type")
    search_fields = ("user__username", "user__email", "team__team_name")
    raw_id_fields = ("user", "team")


@admin.register(ScheduleNotification)
class ScheduleNotificationAdmin(admin.ModelAdmin):
    list_display = ("notification_id", "user", "schedule_item", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("user__username", "message")
    raw_id_fields = ("user", "schedule_item")
    readonly_fields = ("created_at",)
