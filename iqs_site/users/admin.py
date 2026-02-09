from django.contrib import admin
from django.contrib.auth.models import Group
from .models import GroupProfile, TeamEmail, TeamEnrollmentRequest


class GroupProfileInline(admin.StackedInline):
    model = GroupProfile
    can_delete = False
    extra = 0
    filter_horizontal = ("admins",)


class CustomGroupAdmin(admin.ModelAdmin):
    inlines = [GroupProfileInline]
    list_display = ("name",)
    search_fields = ("name",)


# Remove default Group admin
admin.site.unregister(Group)

# Register Group with your custom admin
admin.site.register(Group, CustomGroupAdmin)


@admin.register(TeamEmail)
class TeamEmailAdmin(admin.ModelAdmin):
    list_display = ("team_email_id", "email", "team", "role", "collected")
    list_filter = ("team",)
    search_fields = ("email", "team__team_name")
    raw_id_fields = ("team",)


@admin.register(TeamEnrollmentRequest)
class TeamEnrollmentRequestAdmin(admin.ModelAdmin):
    list_display = ("request_id", "user", "team", "status", "requested_at", "reviewed_by")
    list_filter = ("status", "requested_at")
    search_fields = ("user__username", "user__email", "team__team_name")
    readonly_fields = ("requested_at", "reviewed_at")
    raw_id_fields = ("user", "team", "reviewed_by")
