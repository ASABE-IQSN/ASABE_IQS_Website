# core/sitemaps.py
from django.contrib.sitemaps import Sitemap
from events.models import Event, Team, Pull, EventTeam, Tractor
from datetime import datetime, timezone

class StaticViewSitemap(Sitemap):
    priority = 0.5
    protocol = "https"
    changefreq = "monthly"

    def items(self):
        return ["events:landing", "events:privacy"]

    def location(self, item):
        from django.urls import reverse
        return reverse(item)


class EventSitemap(Sitemap):
    changefreq = "weekly"
    protocol = "https"
    priority = 0.8

    def items(self):
        return Event.objects.filter()

    def lastmod(self, obj):
        return datetime(2026, 1, 1, tzinfo=timezone.utc)

class EventTeamsSitemap(Sitemap):
    changefreq = "weekly"
    protocol = "https"
    priority = 0.8

    def items(self):
        return EventTeam.objects.filter()

    def lastmod(self, obj):
        return datetime(2026, 1, 1, tzinfo=timezone.utc)
    
class TeamsSitemap(Sitemap):
    changefreq = "weekly"
    protocol = "https"
    priority = 0.8

    def items(self):
        return Team.objects.filter()

    def lastmod(self, obj):
        return datetime(2026, 1, 1, tzinfo=timezone.utc)
    
class TractorsSitemap(Sitemap):
    changefreq = "weekly"
    protocol = "https"
    priority = 0.8

    def items(self):
        return Tractor.objects.filter()

    def lastmod(self, obj):
        return datetime(2026, 1, 1, tzinfo=timezone.utc)