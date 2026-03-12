import uuid

from django.contrib.auth import get_user_model
from django.db import models


class NginxLog(models.Model):
    """
    One row per nginx access log line.
    Captures requests nginx handles directly (static files, images, 404s)
    that never reach the Django application.

    Import with: manage.py import_nginx_logs --log-file /path/to/access.log
    """
    ip = models.CharField(max_length=45, db_index=True)
    time = models.DateTimeField(db_index=True)
    method = models.CharField(max_length=16)
    url = models.CharField(max_length=2048, db_index=True)
    query_string = models.CharField(max_length=2048, blank=True, default="")
    protocol = models.CharField(max_length=16, blank=True, default="")
    status_code = models.SmallIntegerField(db_index=True)
    bytes_sent = models.BigIntegerField()          # response body bytes (0 if nginx returns -)
    referer = models.CharField(max_length=2048, blank=True, default="")
    user_agent = models.TextField(blank=True, default="")
    # SHA-256 of the raw log line — prevents duplicate imports on re-runs
    source_hash = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = "nginx_log"
        indexes = [
            models.Index(fields=["time", "status_code"]),
            models.Index(fields=["ip", "time"]),
        ]

    def __str__(self):
        return f"{self.time} {self.ip} {self.method} {self.url} {self.status_code}"


class IPGeoCache(models.Model):
    ip = models.CharField(max_length=45, primary_key=True)
    country = models.CharField(max_length=100, blank=True, default="")
    country_code = models.CharField(max_length=10, blank=True, default="")
    region = models.CharField(max_length=100, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    isp = models.CharField(max_length=255, blank=True, default="")
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    is_private = models.BooleanField(default=False)
    cached_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ip_geo_cache"

    def __str__(self):
        return f"{self.ip} → {self.city}, {self.country}"


class PageSession(models.Model):
    """
    One row per page visit. Created by JS on page load, updated by 30-second
    heartbeats while the tab is visible, and finalised by a sendBeacon on unload.
    active_seconds counts only time the tab was actually in the foreground.
    """
    session_id = models.AutoField(primary_key=True)
    token = models.UUIDField(default=uuid.uuid4, editable=False,
        help_text="Secret returned to JS — used to authenticate ping/end requests.")
    user = models.ForeignKey(
        get_user_model(), on_delete=models.SET_NULL,
        null=True, blank=True, related_name='page_sessions',
    )
    path = models.CharField(max_length=500)
    page_title = models.CharField(max_length=512, blank=True)
    referrer = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField()
    active_seconds = models.PositiveIntegerField(default=0)
    is_complete = models.BooleanField(default=False,
        help_text="True once the end beacon has been received.")

    class Meta:
        indexes = [
            models.Index(fields=['user', 'started_at']),
            models.Index(fields=['path', 'started_at']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user_id else 'anon'
        return f"{user_str} — {self.path} ({self.active_seconds}s)"
