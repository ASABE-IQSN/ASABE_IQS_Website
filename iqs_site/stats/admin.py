from django.contrib import admin
from stats.models import CsrfFailure, NginxLog, PageSession, ServerError


@admin.register(NginxLog)
class NginxLogAdmin(admin.ModelAdmin):
    list_display = ("time", "ip", "method", "url", "status_code", "bytes_sent")
    list_filter = ("status_code", "method")
    search_fields = ("ip", "url", "user_agent")
    ordering = ("-time",)
    readonly_fields = [f.name for f in NginxLog._meta.get_fields()]
    date_hierarchy = "time"


@admin.register(ServerError)
class ServerErrorAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "exception_type", "url", "method", "ip", "user")
    list_filter = ("exception_type", "method")
    search_fields = ("url", "ip", "exception_type", "user__username")
    ordering = ("-occurred_at",)
    readonly_fields = [f.name for f in ServerError._meta.get_fields()]
    date_hierarchy = "occurred_at"


@admin.register(CsrfFailure)
class CsrfFailureAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "ip", "path", "reason", "user")
    list_filter = ("reason",)
    search_fields = ("ip", "path", "user__username", "user_agent")
    ordering = ("-occurred_at",)
    readonly_fields = [f.name for f in CsrfFailure._meta.get_fields()]
    date_hierarchy = "occurred_at"


@admin.register(PageSession)
class PageSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'user', 'path', 'started_at', 'active_seconds', 'is_complete')
    list_filter = ('is_complete',)
    search_fields = ('user__username', 'path', 'page_title')
    ordering = ('-started_at',)
    date_hierarchy = 'started_at'
    readonly_fields = ('session_id', 'token', 'user', 'path', 'page_title', 'referrer',
                       'started_at', 'last_seen_at', 'active_seconds', 'is_complete')
