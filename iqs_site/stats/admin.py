from django.contrib import admin
from stats.models import NginxLog


@admin.register(NginxLog)
class NginxLogAdmin(admin.ModelAdmin):
    list_display = ("time", "ip", "method", "url", "status_code", "bytes_sent")
    list_filter = ("status_code", "method")
    search_fields = ("ip", "url", "user_agent")
    ordering = ("-time",)
    readonly_fields = [f.name for f in NginxLog._meta.get_fields()]
    date_hierarchy = "time"
