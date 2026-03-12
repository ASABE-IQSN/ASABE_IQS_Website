from django.contrib import admin
from stats.models import NginxLog, PageSession


@admin.register(NginxLog)
class NginxLogAdmin(admin.ModelAdmin):
    list_display = ("time", "ip", "method", "url", "status_code", "bytes_sent")
    list_filter = ("status_code", "method")
    search_fields = ("ip", "url", "user_agent")
    ordering = ("-time",)
    readonly_fields = [f.name for f in NginxLog._meta.get_fields()]
    date_hierarchy = "time"


@admin.register(PageSession)
class PageSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'user', 'path', 'started_at', 'active_seconds', 'is_complete')
    list_filter = ('is_complete',)
    search_fields = ('user__username', 'path', 'page_title')
    ordering = ('-started_at',)
    date_hierarchy = 'started_at'
    readonly_fields = ('session_id', 'token', 'user', 'path', 'page_title', 'referrer',
                       'started_at', 'last_seen_at', 'active_seconds', 'is_complete')
