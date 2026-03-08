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
