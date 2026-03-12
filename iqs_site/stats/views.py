from __future__ import annotations

import ipaddress
import json
import urllib.request
from collections import Counter
from datetime import date, datetime as dt_datetime, timedelta, timezone as dt_tz
from typing import Dict, List

from django.contrib.admin.models import LogEntry
from django.contrib.auth.decorators import user_passes_test
from iqs_site.utilities import log_view
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Max, Min, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from events.models import EditLog, EventTeamPhoto, PerformanceEventMedia, TractorMedia
from stats.models import IPGeoCache, NginxLog, PageSession
from users.models import GroupProfile, TeamEnrollmentRequest, View as PageView


def _is_private_ip(ip_str: str) -> bool:
    try:
        return ipaddress.ip_address(ip_str).is_private
    except ValueError:
        return False


def _fetch_geo_batch(ips: list) -> list:
    payload = json.dumps([{"query": ip} for ip in ips]).encode()
    req = urllib.request.Request(
        "http://ip-api.com/batch"
        "?fields=status,query,country,countryCode,regionName,city,isp,lat,lon",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return []


def resolve_geo(ips: list) -> dict:
    """Return mapping of ip -> geo dict, using DB cache and ip-api.com for misses."""
    result: dict = {}
    public_ips: list = []

    for ip in ips:
        if not ip:
            continue
        if _is_private_ip(ip):
            result[ip] = {"country": "Private", "country_code": "", "city": "",
                          "region": "", "isp": "", "is_private": True}
        else:
            public_ips.append(ip)

    if not public_ips:
        return result

    # Pull from cache
    cached = {obj.ip: obj for obj in IPGeoCache.objects.filter(ip__in=public_ips)}
    for ip, obj in cached.items():
        result[ip] = {
            "country": obj.country, "country_code": obj.country_code,
            "city": obj.city, "region": obj.region, "isp": obj.isp,
            "is_private": False,
        }

    missing = [ip for ip in public_ips if ip not in cached]

    # Batch-fetch missing IPs (100 per request, ip-api.com limit)
    new_objs = []
    for i in range(0, len(missing), 100):
        for r in _fetch_geo_batch(missing[i:i + 100]):
            ip = r.get("query", "")
            if not ip:
                continue
            geo = {
                "country": r.get("country", ""),
                "country_code": r.get("countryCode", ""),
                "city": r.get("city", ""),
                "region": r.get("regionName", ""),
                "isp": r.get("isp", ""),
                "is_private": False,
            }
            result[ip] = geo
            new_objs.append(IPGeoCache(
                ip=ip,
                country=geo["country"], country_code=geo["country_code"],
                city=geo["city"], region=geo["region"], isp=geo["isp"],
            ))

    if new_objs:
        IPGeoCache.objects.bulk_create(new_objs, ignore_conflicts=True)

    return result


def _get_tz_offset(request) -> int:
    """Return browser's getTimezoneOffset() value from cookie (minutes to add to local → UTC)."""
    try:
        return int(request.COOKIES.get('tz_offset', '0'))
    except (ValueError, TypeError):
        return 0


def _get_day_bounds(selected_date: date, tz_offset: int):
    """Return (day_start, day_end) as UTC-aware datetimes bounding the user's local day."""
    # local midnight in UTC = naive UTC midnight + offset minutes
    # (getTimezoneOffset returns minutes such that UTC = local + offset)
    day_start = dt_datetime(
        selected_date.year, selected_date.month, selected_date.day,
        tzinfo=dt_tz.utc,
    ) + timedelta(minutes=tz_offset)
    return day_start, day_start + timedelta(days=1)


AVAILABLE_METRICS = [
    ("speed", "Speed (ft/s)"),
    ("force", "Force (lbf)"),
    ("distance", "Distance (ft)"),
    ("rpm", "Engine RPM"),
]


def _fmt_seconds(s):
    """Format seconds as 'Xm Ys' string."""
    if s is None:
        return "0s"
    s = int(s)
    if s >= 60:
        return f"{s // 60}m {s % 60}s"
    return f"{s}s"


def _aggregate_team_page_stats(team_page_sessions, user_team_map):
    """
    Given a queryset of (path, user_id, session_count, total_active_s) rows
    and a user→teams map, aggregate by (team_name, team_number, path).
    Users on multiple teams get counted for each team.
    Returns list sorted by total_active_s descending, capped at 50 rows.
    """
    agg: dict = {}  # (team_name, team_number, path) -> {session_count, total_active_s}
    for row in team_page_sessions:
        uid = row['user_id']
        teams = user_team_map.get(uid, [])
        for (team_name, team_number) in teams:
            key = (team_name, team_number, row['path'])
            if key not in agg:
                agg[key] = {'team_name': team_name, 'team_number': team_number,
                            'path': row['path'], 'session_count': 0, 'total_active_s': 0}
            agg[key]['session_count'] += row['session_count']
            agg[key]['total_active_s'] += row['total_active_s'] or 0

    result = sorted(agg.values(), key=lambda x: -x['total_active_s'])[:50]
    for row in result:
        row['avg_active_s'] = (row['total_active_s'] // row['session_count']
                               if row['session_count'] else 0)
        row['total_active_fmt'] = _fmt_seconds(row['total_active_s'])
        row['avg_active_fmt'] = _fmt_seconds(row['avg_active_s'])
    return result


@log_view
@user_passes_test(lambda u: u.is_staff)
def daily_activity(request):
    date_str = request.GET.get("date")
    try:
        selected_date = date.fromisoformat(date_str) if date_str else timezone.localdate()
    except ValueError:
        selected_date = timezone.localdate()

    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)
    tz_offset = _get_tz_offset(request)
    day_start, day_end = _get_day_bounds(selected_date, tz_offset)
    is_today = selected_date == (timezone.now() - timedelta(minutes=tz_offset)).date()

    # --- New accounts ---
    new_accounts = list(
        User.objects.filter(date_joined__gte=day_start, date_joined__lt=day_end)
        .order_by("-date_joined")
        .values("id", "username", "email", "date_joined", "first_name", "last_name")
    )

    # --- Logins (last_login on this date) ---
    logins = list(
        User.objects.filter(last_login__gte=day_start, last_login__lt=day_end)
        .order_by("-last_login")
        .values("id", "username", "email", "last_login")
    )

    # --- Page views ---
    page_views = PageView.objects.filter(time__gte=day_start, time__lt=day_end)
    page_view_total = page_views.count()
    top_urls = list(
        page_views.values("url")
        .annotate(count=Count("view_id"))
        .order_by("-count")[:20]
    )
    recent_views = list(
        page_views.select_related("user")
        .order_by("-time")
        .values("time", "url", "ip", "response_code", "response_time_s", "user__username")[:100]
    )

    # --- Geo lookup (unique IPs for the day, by view count) ---
    ip_view_counts = dict(
        page_views.values("ip")
        .annotate(count=Count("view_id"))
        .values_list("ip", "count")
    )
    geo_map = resolve_geo(list(ip_view_counts.keys()))

    # Annotate recent_views with geo location
    for v in recent_views:
        geo = geo_map.get(v["ip"], {})
        if geo.get("is_private"):
            v["location"] = "Private"
        elif geo.get("city"):
            parts = [geo["city"]]
            if geo.get("region"):
                parts.append(geo["region"])
            parts.append(geo.get("country_code", ""))
            v["location"] = ", ".join(p for p in parts if p)
        elif geo.get("country"):
            v["location"] = geo["country"]
        else:
            v["location"] = ""

    country_counter: Counter = Counter()
    city_counts: dict = {}  # (city, region, country_code) -> int
    for ip, view_count in ip_view_counts.items():
        geo = geo_map.get(ip, {})
        if geo.get("is_private"):
            continue
        country = geo.get("country") or "Unknown"
        country_counter[country] += view_count
        city = geo.get("city", "")
        region = geo.get("region", "")
        cc = geo.get("country_code", "")
        if city:
            key = (city, region, cc)
            city_counts[key] = city_counts.get(key, 0) + view_count
    geo_by_country = [{"name": c, "count": n} for c, n in country_counter.most_common(20)]
    geo_by_city = sorted(
        [{"name": ", ".join(p for p in [city, region, cc] if p),
          "city": city, "region": region, "country_code": cc, "count": n}
         for (city, region, cc), n in city_counts.items()],
        key=lambda x: -x["count"],
    )[:15]

    # --- Geo for auth_status only (real browser sessions, not bots/crawlers) ---
    auth_ip_counts = dict(
        page_views.filter(url="/user/auth-status/")
        .values("ip")
        .annotate(count=Count("view_id"))
        .values_list("ip", "count")
    )
    # geo_map already covers most of these; resolve_geo handles any new ones
    auth_geo_map = resolve_geo(list(auth_ip_counts.keys()))
    auth_country_counter: Counter = Counter()
    auth_city_counts: dict = {}
    for ip, view_count in auth_ip_counts.items():
        geo = auth_geo_map.get(ip, {})
        if geo.get("is_private"):
            continue
        country = geo.get("country") or "Unknown"
        auth_country_counter[country] += view_count
        city = geo.get("city", "")
        region = geo.get("region", "")
        cc = geo.get("country_code", "")
        if city:
            key = (city, region, cc)
            auth_city_counts[key] = auth_city_counts.get(key, 0) + view_count
    auth_geo_by_country = [{"name": c, "count": n} for c, n in auth_country_counter.most_common(20)]
    auth_geo_by_city = sorted(
        [{"name": ", ".join(p for p in [city, region, cc] if p),
          "city": city, "region": region, "country_code": cc, "count": n}
         for (city, region, cc), n in auth_city_counts.items()],
        key=lambda x: -x["count"],
    )[:15]
    auth_status_total = sum(auth_ip_counts.values())

    # --- Edit logs (team/tractor field changes) ---
    edit_logs = list(
        EditLog.objects.filter(timestamp__gte=day_start, timestamp__lt=day_end)
        .select_related("user", "team", "tractor")
        .order_by("-timestamp")
        .values(
            "timestamp", "entity_type", "field_name", "old_value", "new_value",
            "user__username", "team__team_name", "team__team_number",
            "tractor__tractor_name",
        )[:200]
    )

    # --- Enrollment requests submitted today ---
    enrollment_requests = list(
        TeamEnrollmentRequest.objects.filter(requested_at__gte=day_start, requested_at__lt=day_end)
        .select_related("user", "team", "reviewed_by")
        .order_by("-requested_at")
        .values(
            "request_id", "requested_at", "status", "message",
            "user__username", "user__email",
            "team__team_name", "team__team_number",
        )
    )

    # --- Enrollment requests reviewed today ---
    reviewed_requests = list(
        TeamEnrollmentRequest.objects.filter(reviewed_at__gte=day_start, reviewed_at__lt=day_end)
        .select_related("user", "team", "reviewed_by")
        .order_by("-reviewed_at")
        .values(
            "request_id", "reviewed_at", "status",
            "user__username", "team__team_name", "team__team_number",
            "reviewed_by__username",
        )
    )

    # --- Media uploads ---
    tractor_media = list(
        TractorMedia.objects.filter(created_at__gte=day_start, created_at__lt=day_end)
        .select_related("uploaded_by", "tractor")
        .order_by("-created_at")
        .values(
            "media_id", "created_at", "media_type", "link",
            "uploaded_by__username", "tractor__tractor_name",
        )
    )

    event_team_photos = list(
        EventTeamPhoto.objects.filter(created_at__gte=day_start, created_at__lt=day_end)
        .order_by("-created_at")
        .values("event_team_photo_id", "created_at", "photo_path", "caption", "approved",
                "submitted_from_ip")
    )

    perf_media = list(
        PerformanceEventMedia.objects.filter(created_at__gte=day_start, created_at__lt=day_end)
        .select_related("uploaded_by")
        .order_by("-created_at")
        .values(
            "media_id", "created_at", "media_type", "link", "caption",
            "uploaded_by__username", "performance_event_type",
        )
    )

    # --- Django admin log entries ---
    admin_logs = list(
        LogEntry.objects.filter(action_time__gte=day_start, action_time__lt=day_end)
        .select_related("user", "content_type")
        .order_by("-action_time")
        .values(
            "action_time", "action_flag", "object_repr", "change_message",
            "user__username", "content_type__app_label", "content_type__model",
        )[:100]
    )

    # --- Page Session summary ---
    sessions_today = PageSession.objects.filter(started_at__gte=day_start, started_at__lt=day_end)
    session_total = sessions_today.count()
    top_pages_by_time = list(
        sessions_today
        .values('path')
        .annotate(session_count=Count('session_id'), total_active_s=Sum('active_seconds'))
        .order_by('-total_active_s')[:20]
    )
    top_pages_by_count = list(
        sessions_today
        .values('path')
        .annotate(session_count=Count('session_id'), total_active_s=Sum('active_seconds'))
        .order_by('-session_count')[:20]
    )
    for row in top_pages_by_time:
        row['total_active_fmt'] = _fmt_seconds(row['total_active_s'])
    for row in top_pages_by_count:
        row['total_active_fmt'] = _fmt_seconds(row['total_active_s'])

    # --- Team breakdown via GroupProfile ---
    user_team_rows = (GroupProfile.objects
        .filter(team__isnull=False)
        .values('group__user', 'team__team_name', 'team__team_number'))
    user_team_map: dict = {}
    for row in user_team_rows:
        uid = row['group__user']
        if uid:
            user_team_map.setdefault(uid, []).append(
                (row['team__team_name'], row['team__team_number'])
            )
    team_page_sessions_qs = (sessions_today
        .filter(user__isnull=False)
        .values('path', 'user_id')
        .annotate(session_count=Count('session_id'), total_active_s=Sum('active_seconds')))
    team_page_stats = _aggregate_team_page_stats(team_page_sessions_qs, user_team_map)

    # --- Nginx daily summary ---
    nginx_today = NginxLog.objects.filter(time__gte=day_start, time__lt=day_end)
    nginx_total = nginx_today.count()
    nginx_bytes = nginx_today.aggregate(total=Sum('bytes_sent'))['total'] or 0
    nginx_status_dist = list(
        nginx_today
        .values('status_code')
        .annotate(count=Count('id'))
        .order_by('status_code')
    )
    nginx_top_urls = list(
        nginx_today
        .values('url')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    # --- 500 errors ---
    server_errors = list(
        page_views.filter(response_code__gte=500)
        .select_related("user")
        .order_by("-time")
        .values("time", "url", "ip", "response_code", "response_time_s", "user__username")[:200]
    )
    server_error_urls = list(
        page_views.filter(response_code__gte=500)
        .values("url", "response_code")
        .annotate(count=Count("view_id"))
        .order_by("-count")[:20]
    )
    for v in server_errors:
        geo = geo_map.get(v["ip"], {})
        if geo.get("is_private"):
            v["location"] = "Private"
        elif geo.get("city"):
            parts = [geo["city"]]
            if geo.get("region"):
                parts.append(geo["region"])
            parts.append(geo.get("country_code", ""))
            v["location"] = ", ".join(p for p in parts if p)
        elif geo.get("country"):
            v["location"] = geo["country"]
        else:
            v["location"] = ""

    return render(request, "stats/daily_activity.html", {
        "selected_date": selected_date,
        "prev_date": prev_date,
        "next_date": next_date,
        "is_today": is_today,
        "new_accounts": new_accounts,
        "logins": logins,
        "page_view_total": page_view_total,
        "top_urls": top_urls,
        "recent_views": recent_views,
        "geo_by_country": geo_by_country,
        "geo_by_city": geo_by_city,
        "auth_geo_by_country": auth_geo_by_country,
        "auth_geo_by_city": auth_geo_by_city,
        "auth_status_total": auth_status_total,
        "edit_logs": edit_logs,
        "enrollment_requests": enrollment_requests,
        "reviewed_requests": reviewed_requests,
        "tractor_media": tractor_media,
        "event_team_photos": event_team_photos,
        "perf_media": perf_media,
        "admin_logs": admin_logs,
        "server_errors": server_errors,
        "server_error_urls": server_error_urls,
        "session_total": session_total,
        "top_pages_by_time": top_pages_by_time,
        "top_pages_by_count": top_pages_by_count,
        "team_page_stats": team_page_stats,
        "nginx_total": nginx_total,
        "nginx_bytes": nginx_bytes,
        "nginx_status_dist": nginx_status_dist,
        "nginx_top_urls": nginx_top_urls,
    })


@log_view
@user_passes_test(lambda u: u.is_staff)
def location_drill(request):
    city = request.GET.get("city", "").strip()
    country_code = request.GET.get("country_code", "").strip()
    country = request.GET.get("country", "").strip()
    date_str = request.GET.get("date")
    history_days = int(request.GET.get("days", 30))

    if not city and not country:
        return redirect("stats:daily_activity")

    try:
        selected_date = date.fromisoformat(date_str) if date_str else timezone.localdate()
    except ValueError:
        selected_date = timezone.localdate()

    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)
    tz_offset = _get_tz_offset(request)
    day_start, day_end = _get_day_bounds(selected_date, tz_offset)
    is_today = selected_date == (timezone.now() - timedelta(minutes=tz_offset)).date()

    # Resolve matching IPs from cache
    if city and country_code:
        cache_qs = IPGeoCache.objects.filter(city=city, country_code=country_code)
        matching_ips = list(cache_qs.values_list("ip", flat=True))
        region = cache_qs.values_list("region", flat=True).first() or ""
        location_label = ", ".join(p for p in [city, region, country_code] if p)
    else:
        matching_ips = list(
            IPGeoCache.objects.filter(country=country)
            .values_list("ip", flat=True)
        )
        region = ""
        location_label = country

    base_qs = PageView.objects.filter(ip__in=matching_ips)

    # --- Day view ---
    day_views = list(
        base_qs.filter(time__gte=day_start, time__lt=day_end)
        .select_related("user")
        .order_by("-time")
        .values("time", "url", "ip", "response_code", "response_time_s", "user__username")
    )

    top_urls = list(
        base_qs.filter(time__gte=day_start, time__lt=day_end)
        .values("url")
        .annotate(count=Count("view_id"))
        .order_by("-count")[:20]
    )

    # --- Auth-status views (real browser sessions) for this location ---
    auth_qs = base_qs.filter(url="/user/auth-status/")

    auth_day_views = list(
        auth_qs.filter(time__gte=day_start, time__lt=day_end)
        .select_related("user")
        .order_by("-time")
        .values("time", "ip", "response_code", "response_time_s", "user__username")
    )

    # --- History: fill a full date range so days with 0 views show up ---
    history_start = selected_date - timedelta(days=history_days - 1)
    raw_history = {
        row["day"]: row
        for row in base_qs.filter(
            time__date__gte=history_start,
            time__date__lte=selected_date,
        )
        .annotate(day=TruncDate("time"))
        .values("day")
        .annotate(count=Count("view_id"), unique_ips=Count("ip", distinct=True))
    }
    raw_auth_history = {
        row["day"]: row["count"]
        for row in auth_qs.filter(
            time__date__gte=history_start,
            time__date__lte=selected_date,
        )
        .annotate(day=TruncDate("time"))
        .values("day")
        .annotate(count=Count("view_id"))
    }
    history = []
    for i in range(history_days):
        d = history_start + timedelta(days=i)
        row = raw_history.get(d, {})
        history.append({
            "day": d,
            "count": row.get("count", 0),
            "unique_ips": row.get("unique_ips", 0),
            "auth_count": raw_auth_history.get(d, 0),
        })
    history_max = max((r["count"] for r in history), default=1) or 1

    return render(request, "stats/location_drill.html", {
        "location_label": location_label,
        "city": city,
        "country_code": country_code,
        "country": country,
        "selected_date": selected_date,
        "prev_date": prev_date,
        "next_date": next_date,
        "is_today": is_today,
        "matching_ip_count": len(matching_ips),
        "day_views": day_views,
        "top_urls": top_urls,
        "auth_day_views": auth_day_views,
        "history": history,
        "history_max": history_max,
        "history_days": history_days,
    })


@log_view
@user_passes_test(lambda u: u.is_staff)
def ip_list(request):
    city = request.GET.get("city", "").strip()
    country_code = request.GET.get("country_code", "").strip()
    country = request.GET.get("country", "").strip()

    if not city and not country:
        return redirect("stats:daily_activity")

    date_str = request.GET.get("date")
    tz_offset = _get_tz_offset(request)
    try:
        selected_date = date.fromisoformat(date_str) if date_str else timezone.localdate()
    except ValueError:
        selected_date = timezone.localdate()
    day_start, day_end = _get_day_bounds(selected_date, tz_offset)

    if city and country_code:
        cache_qs = IPGeoCache.objects.filter(city=city, country_code=country_code)
        region = cache_qs.values_list("region", flat=True).first() or ""
        location_label = ", ".join(p for p in [city, region, country_code] if p)
    else:
        cache_qs = IPGeoCache.objects.filter(country=country)
        region = ""
        location_label = country

    geo_entries = list(cache_qs.values("ip", "isp", "city", "region", "country", "country_code"))
    matching_ips = [e["ip"] for e in geo_entries]

    total_counts = dict(
        PageView.objects.filter(ip__in=matching_ips)
        .values("ip").annotate(n=Count("view_id")).values_list("ip", "n")
    )
    day_counts = dict(
        PageView.objects.filter(ip__in=matching_ips, time__gte=day_start, time__lt=day_end)
        .values("ip").annotate(n=Count("view_id")).values_list("ip", "n")
    )
    first_seen_map = dict(
        PageView.objects.filter(ip__in=matching_ips)
        .values("ip").annotate(t=Min("time")).values_list("ip", "t")
    )
    last_seen_map = dict(
        PageView.objects.filter(ip__in=matching_ips)
        .values("ip").annotate(t=Max("time")).values_list("ip", "t")
    )

    ip_rows = sorted(
        [
            {
                "ip": e["ip"],
                "isp": e["isp"],
                "total_views": total_counts.get(e["ip"], 0),
                "day_views": day_counts.get(e["ip"], 0),
                "first_seen": first_seen_map.get(e["ip"]),
                "last_seen": last_seen_map.get(e["ip"]),
            }
            for e in geo_entries
        ],
        key=lambda x: -x["total_views"],
    )

    return render(request, "stats/ip_list.html", {
        "location_label": location_label,
        "city": city,
        "country_code": country_code,
        "country": country,
        "region": region,
        "selected_date": selected_date,
        "ip_rows": ip_rows,
    })


@log_view
@user_passes_test(lambda u: u.is_staff)
def ip_drill(request):
    ip = request.GET.get("ip", "").strip()
    if not ip:
        return redirect("stats:daily_activity")

    date_str = request.GET.get("date")
    history_days = int(request.GET.get("days", 30))
    try:
        selected_date = date.fromisoformat(date_str) if date_str else timezone.localdate()
    except ValueError:
        selected_date = timezone.localdate()

    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)
    tz_offset = _get_tz_offset(request)
    day_start, day_end = _get_day_bounds(selected_date, tz_offset)
    is_today = selected_date == (timezone.now() - timedelta(minutes=tz_offset)).date()

    # Resolve geo for this IP
    geo_map = resolve_geo([ip])
    geo = geo_map.get(ip, {})
    try:
        geo_cache = IPGeoCache.objects.get(ip=ip)
    except IPGeoCache.DoesNotExist:
        geo_cache = None

    base_qs = PageView.objects.filter(ip=ip)

    day_views = list(
        base_qs.filter(time__gte=day_start, time__lt=day_end)
        .select_related("user")
        .order_by("-time")
        .values("time", "url", "response_code", "response_time_s", "user__username")
    )

    top_urls = list(
        base_qs.filter(time__gte=day_start, time__lt=day_end)
        .values("url")
        .annotate(count=Count("view_id"))
        .order_by("-count")[:20]
    )

    history_start = selected_date - timedelta(days=history_days - 1)
    raw_history = {
        row["day"]: row["count"]
        for row in base_qs.filter(
            time__date__gte=history_start,
            time__date__lte=selected_date,
        )
        .annotate(day=TruncDate("time"))
        .values("day")
        .annotate(count=Count("view_id"))
    }
    history = [
        {"day": history_start + timedelta(days=i),
         "count": raw_history.get(history_start + timedelta(days=i), 0)}
        for i in range(history_days)
    ]
    history_max = max((r["count"] for r in history), default=1) or 1

    total_views = base_qs.count()
    first_seen = base_qs.order_by("time").values_list("time", flat=True).first()
    last_seen = base_qs.order_by("-time").values_list("time", flat=True).first()

    return render(request, "stats/ip_drill.html", {
        "ip": ip,
        "geo": geo,
        "geo_cache": geo_cache,
        "selected_date": selected_date,
        "prev_date": prev_date,
        "next_date": next_date,
        "is_today": is_today,
        "day_views": day_views,
        "top_urls": top_urls,
        "history": history,
        "history_max": history_max,
        "history_days": history_days,
        "total_views": total_views,
        "first_seen": first_seen,
        "last_seen": last_seen,
    })


@log_view
@user_passes_test(lambda u: u.is_staff)
def page_overview(request):
    days = int(request.GET.get("days", 7))
    days = min(max(days, 1), 90)

    window_start = timezone.now() - timedelta(days=days)
    base_qs = PageView.objects.filter(time__gte=window_start)

    total_views = base_qs.count()
    top_pages = list(
        base_qs.values("url")
        .annotate(count=Count("view_id"), unique_ips=Count("ip", distinct=True))
        .order_by("-count")[:200]
    )

    # Merge PageSession stats by path
    session_stats = (PageSession.objects
        .filter(started_at__gte=window_start)
        .values('path')
        .annotate(
            session_count=Count('session_id'),
            total_active_s=Sum('active_seconds'),
            avg_active_s=Avg('active_seconds'),
        ))
    session_by_path = {row['path']: row for row in session_stats}
    for row in top_pages:
        sess = session_by_path.get(row['url'], {})
        row['session_count'] = sess.get('session_count', 0)
        row['total_active_s'] = sess.get('total_active_s') or 0
        row['avg_active_s'] = sess.get('avg_active_s') or 0
        row['total_active_fmt'] = _fmt_seconds(row['total_active_s'])
        row['avg_active_fmt'] = _fmt_seconds(row['avg_active_s'])

    return render(request, "stats/page_overview.html", {
        "days": days,
        "window_start": window_start,
        "total_views": total_views,
        "top_pages": top_pages,
        "day_options": [1, 7, 14, 30, 90],
    })


@log_view
@user_passes_test(lambda u: u.is_staff)
def page_drill(request):
    url = request.GET.get("url", "").strip()
    if not url:
        return redirect("stats:page_overview")

    days = int(request.GET.get("days", 7))
    days = min(max(days, 1), 90)

    tz_offset = _get_tz_offset(request)
    now = timezone.now()
    window_start = now - timedelta(days=days)
    today = (now - timedelta(minutes=tz_offset)).date()
    history_start = today - timedelta(days=days - 1)

    base_qs = PageView.objects.filter(url=url, time__gte=window_start)

    total_views = base_qs.count()
    unique_ip_count = base_qs.values("ip").distinct().count()

    # Geo
    ip_counts = dict(
        base_qs.values("ip").annotate(n=Count("view_id")).values_list("ip", "n")
    )
    geo_map = resolve_geo(list(ip_counts.keys()))

    country_counter: Counter = Counter()
    city_counts: dict = {}
    for ip, count in ip_counts.items():
        geo = geo_map.get(ip, {})
        if geo.get("is_private"):
            continue
        country = geo.get("country") or "Unknown"
        country_counter[country] += count
        city = geo.get("city", "")
        region = geo.get("region", "")
        cc = geo.get("country_code", "")
        if city:
            key = (city, region, cc)
            city_counts[key] = city_counts.get(key, 0) + count

    geo_by_country = [{"name": c, "count": n} for c, n in country_counter.most_common(20)]
    geo_by_city = sorted(
        [{"name": ", ".join(p for p in [city, region, cc] if p),
          "city": city, "region": region, "country_code": cc, "count": n}
         for (city, region, cc), n in city_counts.items()],
        key=lambda x: -x["count"],
    )[:20]

    # Daily history
    raw_history = {
        row["day"]: row["count"]
        for row in base_qs
        .annotate(day=TruncDate("time"))
        .values("day")
        .annotate(count=Count("view_id"))
    }
    history = [
        {"day": history_start + timedelta(days=i),
         "count": raw_history.get(history_start + timedelta(days=i), 0)}
        for i in range(days)
    ]
    history_max = max((r["count"] for r in history), default=1) or 1

    # Recent views with location annotation
    recent_views = list(
        base_qs.select_related("user")
        .order_by("-time")
        .values("time", "ip", "response_code", "response_time_s", "user__username")[:100]
    )
    for v in recent_views:
        geo = geo_map.get(v["ip"], {})
        if geo.get("is_private"):
            v["location"] = "Private"
        elif geo.get("city"):
            parts = [geo["city"]]
            if geo.get("region"):
                parts.append(geo["region"])
            parts.append(geo.get("country_code", ""))
            v["location"] = ", ".join(p for p in parts if p)
        elif geo.get("country"):
            v["location"] = geo["country"]
        else:
            v["location"] = ""

    # Top IPs with location
    ip_rows = []
    for ip, count in sorted(ip_counts.items(), key=lambda x: -x[1])[:50]:
        geo = geo_map.get(ip, {})
        if geo.get("is_private"):
            location = "Private"
        elif geo.get("city"):
            parts = [geo["city"]]
            if geo.get("region"):
                parts.append(geo["region"])
            parts.append(geo.get("country_code", ""))
            location = ", ".join(p for p in parts if p)
        elif geo.get("country"):
            location = geo["country"]
        else:
            location = ""
        ip_rows.append({
            "ip": ip,
            "count": count,
            "location": location,
            "isp": geo.get("isp", ""),
        })

    return render(request, "stats/page_drill.html", {
        "url": url,
        "days": days,
        "window_start": window_start,
        "total_views": total_views,
        "unique_ip_count": unique_ip_count,
        "geo_by_country": geo_by_country,
        "geo_by_city": geo_by_city,
        "history": history,
        "history_max": history_max,
        "history_end": today,
        "recent_views": recent_views,
        "ip_rows": ip_rows,
        "day_options": [1, 7, 14, 30, 90],
    })


@log_view
@user_passes_test(lambda u: u.is_staff)
def user_activity(request):
    user_id = request.GET.get("user_id")
    if not user_id:
        return redirect("stats:daily_activity")
    try:
        profile_user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return redirect("stats:daily_activity")

    days = int(request.GET.get("days", 30))
    days = min(max(days, 1), 90)
    window_start = timezone.now() - timedelta(days=days)

    # Page views
    views_qs = PageView.objects.filter(user=profile_user, time__gte=window_start).order_by("-time")
    recent_views = list(views_qs.values("time", "url", "ip", "response_code", "response_time_s")[:200])
    top_urls = list(
        views_qs.values("url")
        .annotate(count=Count("view_id"))
        .order_by("-count")[:20]
    )

    # Page sessions
    sessions_qs = PageSession.objects.filter(user=profile_user, started_at__gte=window_start).order_by("-started_at")
    recent_sessions = list(sessions_qs.values(
        "session_id", "path", "page_title", "started_at", "last_seen_at", "active_seconds", "is_complete"
    )[:200])
    for s in recent_sessions:
        s["active_fmt"] = _fmt_seconds(s["active_seconds"])
    session_total_time = sessions_qs.aggregate(total=Sum("active_seconds"))["total"] or 0

    # Edit logs
    edit_logs = list(
        EditLog.objects.filter(user=profile_user, timestamp__gte=window_start)
        .select_related("team", "tractor")
        .order_by("-timestamp")
        .values(
            "timestamp", "entity_type", "field_name", "old_value", "new_value",
            "team__team_name", "team__team_number", "tractor__tractor_name",
        )[:200]
    )

    # Geo lookup for views
    ip_counts = dict(
        views_qs.values("ip").annotate(n=Count("view_id")).values_list("ip", "n")
    )
    geo_map = resolve_geo(list(ip_counts.keys()))
    for v in recent_views:
        geo = geo_map.get(v["ip"], {})
        if geo.get("is_private"):
            v["location"] = "Private"
        elif geo.get("city"):
            parts = [geo["city"]]
            if geo.get("region"):
                parts.append(geo["region"])
            parts.append(geo.get("country_code", ""))
            v["location"] = ", ".join(p for p in parts if p)
        elif geo.get("country"):
            v["location"] = geo["country"]
        else:
            v["location"] = ""

    return render(request, "stats/user_activity.html", {
        "profile_user": profile_user,
        "days": days,
        "window_start": window_start,
        "recent_views": recent_views,
        "top_urls": top_urls,
        "recent_sessions": recent_sessions,
        "session_total_time": _fmt_seconds(session_total_time),
        "edit_logs": edit_logs,
        "day_options": [7, 14, 30, 90],
    })


@log_view
@user_passes_test(lambda u: u.is_staff)
def team_page_activity(request):
    days = int(request.GET.get("days", 30))
    days = min(max(days, 1), 90)
    window_start = timezone.now() - timedelta(days=days)

    sessions = (PageSession.objects
        .filter(started_at__gte=window_start)
        .filter(user__isnull=False)
        .values('path', 'user_id')
        .annotate(session_count=Count('session_id'), total_active_s=Sum('active_seconds')))

    user_team_rows = (GroupProfile.objects
        .filter(team__isnull=False)
        .values('group__user', 'team__team_name', 'team__team_number'))
    user_team_map: dict = {}
    for row in user_team_rows:
        uid = row['group__user']
        if uid:
            user_team_map.setdefault(uid, []).append(
                (row['team__team_name'], row['team__team_number'])
            )

    team_page_stats = _aggregate_team_page_stats(sessions, user_team_map)

    # Top teams by total time across all pages
    team_totals: dict = {}
    for row in team_page_stats:
        key = (row['team_name'], row['team_number'])
        if key not in team_totals:
            team_totals[key] = {'team_name': row['team_name'], 'team_number': row['team_number'],
                                'total_active_s': 0, 'session_count': 0}
        team_totals[key]['total_active_s'] += row['total_active_s']
        team_totals[key]['session_count'] += row['session_count']
    top_teams = sorted(team_totals.values(), key=lambda x: -x['total_active_s'])
    for t in top_teams:
        t['total_active_fmt'] = _fmt_seconds(t['total_active_s'])

    return render(request, "stats/team_page_activity.html", {
        "days": days,
        "window_start": window_start,
        "team_page_stats": team_page_stats,
        "top_teams": top_teams,
        "day_options": [1, 7, 14, 30, 90],
    })


@log_view
def plot_page(request):
    return render(
        request,
        "stats/plot.html",
        {"available_metrics": AVAILABLE_METRICS},
    )


def test_series_api(request):
    """
    Returns deterministic "constant" test series (same every call).
    Query:
      ?metrics=speed&metrics=force
    """
    metrics = request.GET.getlist("metrics") or ["speed"]

    # Time base: last 5 minutes, 1 Hz
    n = 300
    end = timezone.now()
    start = end - timedelta(seconds=n - 1)
    timestamps = [(start + timedelta(seconds=i)).isoformat() for i in range(n)]

    # Generate deterministic data (no randomness)
    # Keep it simple but not flat so zooming is interesting.
    series: Dict[str, Dict[str, List]] = {}

    for m in metrics:
        if m == "speed":
            # speed ramps up then stabilizes
            vals = [min(18.0, 3.0 + i * 0.08) for i in range(n)]
            series[m] = {"timestamps": timestamps, "values": vals, "label": "Speed (ft/s)"}

        elif m == "force":
            # force rises, small oscillation
            vals = [200.0 + i * 2.2 + (15.0 if (i // 10) % 2 == 0 else -15.0) for i in range(n)]
            series[m] = {"timestamps": timestamps, "values": vals, "label": "Force (lbf)"}

        elif m == "distance":
            # distance is cumulative integral-ish of speed
            dist = 0.0
            vals = []
            for i in range(n):
                v = min(18.0, 3.0 + i * 0.08)
                dist += v * 1.0  # dt=1s
                vals.append(dist)
            series[m] = {"timestamps": timestamps, "values": vals, "label": "Distance (ft)"}

        elif m == "rpm":
            # rpm ramps and has a step change
            vals = [1200 + int(i * 6) + (200 if i > 160 else 0) for i in range(n)]
            series[m] = {"timestamps": timestamps, "values": vals, "label": "Engine RPM"}

        else:
            # unknown metric -> empty series
            series[m] = {"timestamps": [], "values": [], "label": m}
    print(series)
    return JsonResponse({"series": series})


# ---------------------------------------------------------------------------
# Page-time tracking endpoints (called by JS in base.html)
# ---------------------------------------------------------------------------

@require_POST
def pv_start(request):
    """Create a new PageSession on page load. Returns session_id + token."""
    session = PageSession.objects.create(
        user=request.user if request.user.is_authenticated else None,
        path=request.POST.get('path', '')[:500],
        page_title=request.POST.get('title', '')[:512],
        referrer=request.POST.get('referrer', '')[:500],
        last_seen_at=timezone.now(),
    )
    return JsonResponse({'session_id': session.session_id, 'token': str(session.token)})


@require_POST
def pv_ping(request):
    """Heartbeat — bump last_seen_at and update active_seconds."""
    _update_session(request, complete=False)
    return JsonResponse({'ok': True})


@csrf_exempt
@require_POST
def pv_end(request):
    """
    Final beacon sent via sendBeacon on pagehide.
    csrf_exempt because sendBeacon with a Blob can't always attach the header
    in time; the token field provides authentication instead.
    """
    _update_session(request, complete=True)
    return JsonResponse({'ok': True})


def _update_session(request, complete):
    try:
        session_id = int(request.POST.get('session_id', ''))
        token = request.POST.get('token', '')
        active_seconds = max(0, int(float(request.POST.get('active_seconds', 0))))
    except (ValueError, TypeError):
        return

    try:
        session = PageSession.objects.get(pk=session_id, token=token)
    except PageSession.DoesNotExist:
        return

    session.last_seen_at = timezone.now()
    session.active_seconds = active_seconds
    if complete:
        session.is_complete = True
    session.save(update_fields=['last_seen_at', 'active_seconds', 'is_complete'])
