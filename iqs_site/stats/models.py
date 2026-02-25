from django.db import models


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
