from django.contrib import admin

# Register your models here.

from .models import Team, Event, Hook, Pull


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "school")
    search_fields = ("name", "school")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "start_date", "end_date")
    search_fields = ("name", "location")
    list_filter = ("start_date",)


@admin.register(Hook)
class HookAdmin(admin.ModelAdmin):
    list_display = ("event", "number", "class_name")
    list_filter = ("event", "class_name")


@admin.register(Pull)
class PullAdmin(admin.ModelAdmin):
    list_display = ("team", "event", "hook", "final_distance", "created_at")
    list_filter = ("event", "hook__class_name")
    search_fields = ("team__name", "team__school")
