from django.contrib import admin
from django.utils.html import format_html
from .models import AwardType, Award


@admin.register(AwardType)
class AwardTypeAdmin(admin.ModelAdmin):
    list_display = ('award_type_id', 'name', 'short_name', 'category', 'team_class', 'display_order', 'image_preview')
    list_editable = ('display_order',)
    list_filter = ('category', 'team_class')
    readonly_fields = ('image_preview',)
    fields = ('name', 'short_name', 'description', 'image', 'category', 'team_class', 'display_order', 'image_preview')

    def image_preview(self, obj):
        url = obj.image_url
        if url:
            return format_html('<img src="{}" style="max-height:80px; border-radius:4px;">', url)
        return '—'
    image_preview.short_description = 'Preview'


@admin.register(Award)
class AwardAdmin(admin.ModelAdmin):
    list_display = ('award_id', 'award_type', 'get_event', 'get_team', 'placement', 'notes', 'display_order')
    list_filter = ('award_type__category', 'award_type', 'event_team__event')
    search_fields = ('event_team__team__team_name', 'award_type__name')
    raw_id_fields = ('event_team',)
    list_select_related = True

    def get_event(self, obj):
        return obj.event_team.event.event_name if obj.event_team and obj.event_team.event else '—'
    get_event.short_description = 'Event'
    get_event.admin_order_field = 'event_team__event__event_name'

    def get_team(self, obj):
        return obj.event_team.team.team_name if obj.event_team and obj.event_team.team else '—'
    get_team.short_description = 'Team'
    get_team.admin_order_field = 'event_team__team__team_name'
