# core/sitemaps.py
from django.contrib.sitemaps import Sitemap
from events.models import Event, Team, Pull, EventTeam, Tractor
from datetime import datetime, timezone
from techin.models import RuleSubCategory,Rule

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
    
class TechinSitemap(Sitemap):
    changefreq = "weekly"
    protocol = "https"
    priority = 0.8
    def items(self):
        l=[]
        events=Event.objects.all().order_by("event_id").filter(techin_released=True)
        subcategories=RuleSubCategory.objects.all().order_by("rule_subcategory_id")
        rules=Rule.objects.all().order_by("rule_id")
        for event in events:
            url=f"/techin/event/{event.event_id}"
            l.append(url)
            teamEvents=EventTeam.objects.all().filter(event=event).order_by("event_team_id")
            for et in teamEvents:
                url=f"/techin/event/{et.event.event_id}/team/{et.team.team_id}"
                l.append(url)
                for sub in subcategories:
                    url=f"/techin/event/{et.event.event_id}/team/{et.team.team_id}/subcategory/{sub.rule_subcategory_id}"
                    l.append(url)
                for rule in rules:
                    url=f"/techin/event/{et.event.event_id}/team/{et.team.team_id}/rule/{rule.rule_id}"
                    l.append(url)
        return l
    
    def location(self, item):
        # item is already the path string
        return item
    def lastmod(self, obj):
        return datetime(2026, 1, 1, tzinfo=timezone.utc)