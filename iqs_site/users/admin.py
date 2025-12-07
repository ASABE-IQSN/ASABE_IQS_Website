from django.contrib import admin
from django.contrib.auth.models import Group
from .models import GroupProfile


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
