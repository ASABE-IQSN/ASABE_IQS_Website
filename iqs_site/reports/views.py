import json

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Max
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from events.models import Event, Report

from .models import AnalysisJob, ChunkMatch, PageMatch, ReportPage

REPORT_TYPE_LABELS = {
    1: "Design Report",
    2: "Cost Report",
    3: "Design Log",
}


def _require_staff(request):
    """Return True if the user is authenticated staff, raise Http404 otherwise."""
    if request.user.is_authenticated and request.user.is_staff:
        return True
    raise Http404()


# ── Report download ───────────────────────────────────────────────────────────

def report_download(request, report_id):
    report = get_object_or_404(Report, pk=report_id)

    # Internal Celery task access: bypass user auth when a valid token is present.
    internal_token = getattr(settings, "INTERNAL_REPORT_TOKEN", "")
    if internal_token and request.headers.get("X-Internal-Token") == internal_token:
        pass  # allow
    elif not request.user.is_authenticated or not request.user.is_staff:
        raise Http404()

    response = HttpResponse(content_type="application/pdf")
    response["X-Accel-Redirect"] = f"/_reports/{report.report_link}"
    response["Content-Disposition"] = f'inline; filename="{report.report_link}"'
    return response


# ── Analysis dashboard ────────────────────────────────────────────────────────

def analysis_dashboard(request):
    _require_staff(request)

    if request.method == "POST":
        raw = request.POST.get("report_type", "").strip()
        report_type = int(raw) if raw.isdigit() else None
        job = AnalysisJob.objects.create(report_type=report_type)
        from .tasks import run_plagiarism_analysis
        run_plagiarism_analysis.delay(job.pk)
        messages.success(request, f"Analysis job #{job.pk} queued.")
        return redirect("reports:analysis_dashboard")

    jobs = AnalysisJob.objects.order_by("-created_at")[:10]
    active_job_ids = [j.job_id for j in jobs if j.status in (AnalysisJob.Statuses.QUEUED, AnalysisJob.Statuses.RUNNING)]

    available_types = (
        Report.objects
        .values_list("report_type", flat=True)
        .distinct()
        .order_by("report_type")
    )
    report_type_choices = [
        (rt, REPORT_TYPE_LABELS.get(rt, f"Type {rt}"))
        for rt in available_types
    ]

    return render(request, "reports/analysis_dashboard.html", {
        "jobs": jobs,
        "active_job_ids_json": json.dumps(active_job_ids),
        "report_type_choices": report_type_choices,
    })


def analysis_job_status(request, job_id):
    _require_staff(request)
    job = get_object_or_404(AnalysisJob, pk=job_id)
    return JsonResponse({
        "job_id": job.job_id,
        "status": job.status,
        "reports_found": job.reports_found,
        "reports_processed": job.reports_processed,
        "pages_processed": job.pages_processed,
        "error_message": job.error_message or "",
    })


# ── Report match list ─────────────────────────────────────────────────────────

def report_matches(request, report_id):
    _require_staff(request)

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    page_ids = list(ReportPage.objects.filter(report=report).values_list("page_id", flat=True))

    if not page_ids:
        return render(request, "reports/report_matches.html", {
            "report": report,
            "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
            "match_groups": [],
            "no_pages": True,
        })

    matches = (
        PageMatch.objects
        .filter(page_a_id__in=page_ids)
        .select_related(
            "page_a",
            "page_b__report__event_team__team",
            "page_b__report__event_team__event",
        )
        .order_by("-similarity")
    )
    # Also check the other direction.
    matches_b = (
        PageMatch.objects
        .filter(page_b_id__in=page_ids)
        .select_related(
            "page_b",
            "page_a__report__event_team__team",
            "page_a__report__event_team__event",
        )
        .order_by("-similarity")
    )

    groups = {}  # other_report_id → dict

    def _add(this_page, other_page, other_report, sim, pm_id):
        key = other_report.report_id
        if key not in groups:
            groups[key] = {
                "other_report": other_report,
                "team_name": getattr(getattr(other_report.event_team, "team", None), "team_name", "?"),
                "event_name": getattr(getattr(other_report.event_team, "event", None), "event_name", "?"),
                "report_type_label": REPORT_TYPE_LABELS.get(other_report.report_type, f"Type {other_report.report_type}"),
                "page_pairs": [],
                "max_sim": 0.0,
            }
        groups[key]["page_pairs"].append({
            "this_page": this_page,
            "other_page": other_page,
            "similarity": sim,
            "page_match_id": pm_id,
        })
        groups[key]["max_sim"] = max(groups[key]["max_sim"], sim)

    for m in matches:
        _add(m.page_a, m.page_b, m.page_b.report, m.similarity, m.page_match_id)
    for m in matches_b:
        _add(m.page_b, m.page_a, m.page_a.report, m.similarity, m.page_match_id)

    match_groups = sorted(groups.values(), key=lambda g: g["max_sim"], reverse=True)

    return render(request, "reports/report_matches.html", {
        "report": report,
        "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
        "match_groups": match_groups,
        "no_pages": False,
    })


# ── Event analysis matrix ─────────────────────────────────────────────────────

def event_analysis(request, event_id):
    _require_staff(request)

    event = get_object_or_404(Event, pk=event_id)

    try:
        report_type = int(request.GET.get("report_type", 1))
    except (TypeError, ValueError):
        report_type = 1

    reports = list(
        Report.objects
        .filter(event_team__event_id=event_id, report_type=report_type)
        .select_related("event_team__team")
        .order_by("event_team__team__team_name")
    )

    available_types = (
        Report.objects
        .filter(event_team__event_id=event_id)
        .values_list("report_type", flat=True)
        .distinct()
        .order_by("report_type")
    )
    report_type_choices = [
        (rt, REPORT_TYPE_LABELS.get(rt, f"Type {rt}"))
        for rt in available_types
    ]

    if not reports:
        return render(request, "reports/event_analysis.html", {
            "event": event,
            "report_type": report_type,
            "report_type_label": REPORT_TYPE_LABELS.get(report_type, f"Type {report_type}"),
            "report_type_choices": report_type_choices,
            "reports": [],
            "rows": [],
            "no_reports": True,
        })

    report_ids = [r.report_id for r in reports]

    # page/chunk counts per report for the scan-health summary
    stats_by_report = {
        s["report_id"]: s
        for s in ReportPage.objects
            .filter(report_id__in=report_ids)
            .values("report_id")
            .annotate(page_count=Count("page_id"), chunk_count=Count("chunks"))
    }
    report_data = [
        {
            "report": r,
            "page_count": stats_by_report.get(r.report_id, {}).get("page_count", 0),
            "chunk_count": stats_by_report.get(r.report_id, {}).get("chunk_count", 0),
        }
        for r in reports
    ]

    # page_id → (report_id, page_number)
    page_info = {
        p["page_id"]: (p["report_id"], p["page_number"])
        for p in ReportPage.objects
            .filter(report_id__in=report_ids)
            .values("page_id", "report_id", "page_number")
    }
    page_ids = list(page_info.keys())

    # Max similarity per page, checking both directions of PageMatch.
    page_max_sim = {}
    if page_ids:
        for row in PageMatch.objects.filter(page_a_id__in=page_ids).values("page_a_id").annotate(ms=Max("similarity")):
            pid = row["page_a_id"]
            page_max_sim[pid] = max(page_max_sim.get(pid, 0.0), row["ms"])
        for row in PageMatch.objects.filter(page_b_id__in=page_ids).values("page_b_id").annotate(ms=Max("similarity")):
            pid = row["page_b_id"]
            page_max_sim[pid] = max(page_max_sim.get(pid, 0.0), row["ms"])

    # report_id → {page_number: max_sim (float or None if no matches)}
    report_page_sims = {r.report_id: {} for r in reports}
    for pid, (rid, pnum) in page_info.items():
        report_page_sims[rid][pnum] = page_max_sim.get(pid)  # None = processed but no match found

    all_page_numbers = sorted({pnum for ps in report_page_sims.values() for pnum in ps})

    rows = []
    for pnum in all_page_numbers:
        cells = []
        for r in reports:
            ps = report_page_sims[r.report_id]
            if pnum not in ps:
                cells.append(None)  # this report doesn't have this page
            else:
                sim = ps[pnum] or 0.0
                cells.append({"sim": sim, "sim_pct": round(sim * 100)})
        rows.append({"page_number": pnum, "cells": cells})

    return render(request, "reports/event_analysis.html", {
        "event": event,
        "report_type": report_type,
        "report_type_label": REPORT_TYPE_LABELS.get(report_type, f"Type {report_type}"),
        "report_type_choices": report_type_choices,
        "reports": reports,
        "report_data": report_data,
        "rows": rows,
        "no_reports": False,
    })


# ── Page match detail ─────────────────────────────────────────────────────────

def page_match_detail(request, page_match_id):
    _require_staff(request)

    pm = get_object_or_404(
        PageMatch.objects.select_related(
            "page_a__report__event_team__team",
            "page_a__report__event_team__event",
            "page_b__report__event_team__team",
            "page_b__report__event_team__event",
        ),
        pk=page_match_id,
    )

    chunk_matches = list(
        ChunkMatch.objects
        .filter(page_match=pm)
        .select_related("chunk_a", "chunk_b")
        .order_by("-similarity")
    )

    matched_a_ids = {cm.chunk_a_id for cm in chunk_matches}
    matched_b_ids = {cm.chunk_b_id for cm in chunk_matches}

    # Build bidirectional chunk-link map for JS hover logic.
    chunk_links = {}
    for cm in chunk_matches:
        aid = f"chunk-{cm.chunk_a_id}"
        bid = f"chunk-{cm.chunk_b_id}"
        chunk_links.setdefault(aid, []).append(bid)
        chunk_links.setdefault(bid, []).append(aid)

    def _chunk_data(chunks, matched_ids):
        return json.dumps([
            {
                "id": f"chunk-{c.chunk_id}",
                "x0": c.bbox_x0,
                "y0": c.bbox_y0,
                "x1": c.bbox_x1,
                "y1": c.bbox_y1,
                "matched": c.chunk_id in matched_ids,
            }
            for c in chunks
            if c.bbox_x0 is not None
        ])

    a_chunks = list(pm.page_a.chunks.order_by("chunk_index"))
    b_chunks = list(pm.page_b.chunks.order_by("chunk_index"))

    team_a = getattr(getattr(pm.page_a.report.event_team, "team", None), "team_name", "?")
    team_b = getattr(getattr(pm.page_b.report.event_team, "team", None), "team_name", "?")

    return render(request, "reports/page_match_detail.html", {
        "pm": pm,
        "team_a": team_a,
        "team_b": team_b,
        "chunk_matches": chunk_matches,
        "chunk_links_json": json.dumps(chunk_links),
        "left_chunk_data_json": _chunk_data(a_chunks, matched_a_ids),
        "right_chunk_data_json": _chunk_data(b_chunks, matched_b_ids),
    })
