import base64
import io
import json
import random
import re
import statistics

from django.core.cache import cache
from django.conf import settings
from django.contrib import messages
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

import requests as http_requests

from events.models import Event, EventTeam, Report, Team

from .models import (
    AIDetectedSentence, AIDetectionResult,
    AnalysisJob, ChunkMatch, ImageMatch, PageMatch,
    ReportChunk, ReportImage, ReportPage,
)

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


def _resolve_job_param(request, qs, job_field="job_id"):
    """Return (selected_job_id, available_jobs_qs) for artifact querysets.

    Builds the list of AnalysisJob rows that produced results in qs, defaults
    to the most recent one, and honours a ?job=<pk> GET parameter.
    """
    job_ids = (
        qs.exclude(**{f"{job_field}__isnull": True})
          .values_list(job_field, flat=True)
          .distinct()
    )
    available_jobs = AnalysisJob.objects.filter(pk__in=job_ids).order_by("-created_at")
    requested = request.GET.get("job")
    if requested and requested.isdigit():
        req_id = int(requested)
        if available_jobs.filter(pk=req_id).exists():
            return req_id, available_jobs
    first = available_jobs.first()
    return (first.pk if first else None), available_jobs


# ── Report download ───────────────────────────────────────────────────────────
def report_download(request, report_id):
    report = get_object_or_404(Report, pk=report_id)

    # Internal Celery task access: bypass user auth when a valid token is present.
    internal_token = getattr(settings, "INTERNAL_REPORT_TOKEN", "")
    if internal_token and request.headers.get("X-Internal-Token") == internal_token:
        pass  # allow
    elif not request.user.is_authenticated or not request.user.is_staff:
        raise Http404()

    if settings.DEBUG:
        from iqs_site.storage import ReportStorage
        storage = ReportStorage()
        with storage.open(report.report_link, "rb") as f:
            pdf_bytes = f.read()
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{report.report_link}"'
        return response

    response = HttpResponse(content_type="application/pdf")
    response["X-Accel-Redirect"] = f"/_reports/{report.report_link}"
    response["Content-Disposition"] = f'inline; filename="{report.report_link}"'
    return response


# ── Reports overview ──────────────────────────────────────────────────────────
def reports_overview(request):
    _require_staff(request)

    events = list(Event.objects.order_by("-event_datetime"))

    # Per-event report counts and analysis status.
    event_ids = [e.event_id for e in events]

    # Total reports per event, grouped by report type.
    report_counts = {}  # event_id → {report_type: total}
    for row in (
        Report.objects
        .filter(event_team__event_id__in=event_ids)
        .values("event_team__event_id", "report_type")
        .annotate(n=Count("report_id"))
    ):
        eid = row["event_team__event_id"]
        report_counts.setdefault(eid, {})[row["report_type"]] = row["n"]

    # Reports that have been processed (have at least one page extracted).
    processed_counts = {}  # event_id → count of distinct processed report_ids
    for row in (
        ReportPage.objects
        .filter(report__event_team__event_id__in=event_ids)
        .values("report__event_team__event_id")
        .annotate(n=Count("report_id", distinct=True))
    ):
        processed_counts[row["report__event_team__event_id"]] = row["n"]

    event_rows = []
    for e in events:
        total = sum(report_counts.get(e.event_id, {}).values())
        processed = processed_counts.get(e.event_id, 0)
        event_rows.append({
            "event": e,
            "total_reports": total,
            "processed_reports": processed,
            "report_type_choices": [
                (rt, REPORT_TYPE_LABELS.get(rt, f"Type {rt}"))
                for rt in sorted(report_counts.get(e.event_id, {}).keys())
            ],
        })

    return render(request, "reports/overview.html", {
        "event_rows": event_rows,
    })


# ── Analysis dashboard ────────────────────────────────────────────────────────
def analysis_dashboard(request):
    _require_staff(request)

    if request.method == "POST":
        raw = request.POST.get("report_type", "").strip()
        report_type = int(raw) if raw.isdigit() else None
        job_type = request.POST.get("job_type", "full")

        if job_type == "extraction":
            job = AnalysisJob.objects.create(
                report_type=report_type,
                job_type=AnalysisJob.JobTypes.EXTRACTION,
            )
            from .tasks import run_extraction
            run_extraction.delay(job.pk)
            messages.success(request, f"Extraction job #{job.pk} queued.")
        elif job_type == "similarity":
            job = AnalysisJob.objects.create(
                report_type=report_type,
                job_type=AnalysisJob.JobTypes.SIMILARITY,
            )
            from .tasks import run_similarity_analysis
            run_similarity_analysis.delay(job.pk)
            messages.success(request, f"Similarity job #{job.pk} queued.")
        elif job_type == "ai_detection":
            if not request.user.has_perm("reports.can_run_ai_detection"):
                raise Http404()
            raw_event = request.POST.get("event_id", "").strip()
            event_id = int(raw_event) if raw_event.isdigit() else None
            if not event_id:
                messages.error(request, "AI detection requires an event to be selected.")
                return redirect("reports:analysis_dashboard")
            from .models import AIDetectionResult as _ADR
            valid_keys = {c[0] for c in _ADR.Detectors.choices}
            selected_detectors = [d for d in request.POST.getlist("detectors") if d in valid_keys]
            detectors_str = ",".join(selected_detectors)
            if not selected_detectors:
                messages.error(request, "Select at least one AI detector.")
                return redirect("reports:analysis_dashboard")
            job = AnalysisJob.objects.create(
                report_type=report_type,
                job_type=AnalysisJob.JobTypes.AI_DETECTION,
                event_id=event_id,
                detectors=detectors_str,
            )
            from .tasks import run_ai_detection
            run_ai_detection.delay(job.pk)
            messages.success(request, f"AI detection job #{job.pk} queued ({detectors_str}).")
        elif job_type == "bulk_pdf_export":
            raw_event = request.POST.get("event_id", "").strip()
            event_id = int(raw_event) if raw_event.isdigit() else None
            if not event_id:
                messages.error(request, "Bulk PDF export requires an event to be selected.")
                return redirect("reports:analysis_dashboard")
            job = AnalysisJob.objects.create(
                report_type=report_type,
                job_type=AnalysisJob.JobTypes.BULK_PDF_EXPORT,
                event_id=event_id,
            )
            from .tasks import run_bulk_pdf_export
            run_bulk_pdf_export.delay(job.pk)
            messages.success(request, f"Bulk PDF export job #{job.pk} queued.")
        else:
            job = AnalysisJob.objects.create(
                report_type=report_type,
                job_type=AnalysisJob.JobTypes.FULL,
            )
            from .tasks import run_plagiarism_analysis
            run_plagiarism_analysis.delay(job.pk)
            messages.success(request, f"Full analysis job #{job.pk} queued.")

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

    events = Event.objects.order_by("-event_datetime")

    detector_info = [
        (val, label, bool(getattr(settings, f"{val}_API_KEY", "")))
        for val, label in AIDetectionResult.Detectors.choices
    ]

    return render(request, "reports/analysis_dashboard.html", {
        "jobs": jobs,
        "active_job_ids_json": json.dumps(active_job_ids),
        "report_type_choices": report_type_choices,
        "events": events,
        "can_run_ai_detection": request.user.has_perm("reports.can_run_ai_detection"),
        "detector_info": detector_info,
    })


def analysis_job_status(request, job_id):
    _require_staff(request)
    job = get_object_or_404(AnalysisJob, pk=job_id)
    data = {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "reports_found": job.reports_found,
        "reports_processed": job.reports_processed,
        "pages_processed": job.pages_processed,
        "error_message": job.error_message or "",
    }
    if job.export_file:
        data["export_url"] = reverse("reports:export_download", args=[job.job_id])
    return JsonResponse(data)


def export_download(request, job_id):
    """Serve the ZIP file from a completed BULK_PDF_EXPORT job."""
    _require_staff(request)
    job = get_object_or_404(AnalysisJob, pk=job_id)
    if not job.export_file:
        raise Http404("No export file for this job.")

    from iqs_site.storage import ReportStorage
    storage = ReportStorage()
    try:
        with storage.open(job.export_file, "rb") as f:
            zip_bytes = f.read()
    except Exception:
        raise Http404("Export file not found in storage.")

    response = HttpResponse(zip_bytes, content_type="application/zip")
    filename = job.export_file.split("/")[-1]
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ── Report overview ────────────────────────────────────────────────────────────
def report_overview(request, report_id):
    _require_staff(request)

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    page_count  = ReportPage.objects.filter(report=report).count()
    chunk_count = ReportChunk.objects.filter(page__report=report).count()
    image_count = ReportImage.objects.filter(report=report).count()

    # Word count from extracted chunk text
    chunk_texts = ReportChunk.objects.filter(page__report=report).values_list("text", flat=True)
    total_text_words = sum(len(t.split()) for t in chunk_texts)

    # AI detection summary
    ai_results = AIDetectionResult.objects.filter(page__report=report)
    ai_analyzed_count = ai_results.count()
    avg_ai_pct = None
    if ai_analyzed_count:
        agg = ai_results.aggregate(avg=Avg("fake_percentage"))
        avg_ai_pct = round(agg["avg"], 1)

    # Text similarity summary
    text_matches = PageMatch.objects.filter(Q(page_a__report=report) | Q(page_b__report=report))
    text_match_count = text_matches.count()
    best_text_sim_raw = text_matches.order_by("-similarity").values_list("similarity", flat=True).first()
    best_text_sim = round(best_text_sim_raw * 100, 1) if best_text_sim_raw is not None else None

    # Image similarity summary
    image_matches = ImageMatch.objects.filter(Q(image_a__report=report) | Q(image_b__report=report))
    image_match_count = image_matches.count()
    best_hamming = image_matches.order_by("hamming_distance").values_list("hamming_distance", flat=True).first()
    best_image_sim = round((1 - best_hamming / 64) * 100, 1) if best_hamming is not None else None

    return render(request, "reports/report_overview.html", {
        "report": report,
        "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
        "page_count": page_count,
        "chunk_count": chunk_count,
        "image_count": image_count,
        "total_text_words": total_text_words,
        "ai_analyzed_count": ai_analyzed_count,
        "avg_ai_pct": avg_ai_pct,
        "text_match_count": text_match_count,
        "best_text_sim": best_text_sim,
        "image_match_count": image_match_count,
        "best_image_sim": best_image_sim,
        "can_run_ai_detection": request.user.has_perm("reports.can_run_ai_detection"),
    })


# ── Text match grouping helper ────────────────────────────────────────────────

def _get_text_match_groups(report, job_id=None):
    """Return (match_groups, no_pages) for a report's text similarity matches.

    match_groups is a list of dicts sorted by max_sort_score descending.
    Each dict has: other_report, team_name, event_name, report_type_label,
    page_pairs (list), max_sim, max_sort_score.
    """
    page_ids = list(ReportPage.objects.filter(report=report).values_list("page_id", flat=True))

    if not page_ids:
        return [], True

    job_filter = {"job_id": job_id} if job_id is not None else {}

    matches = (
        PageMatch.objects
        .filter(page_a_id__in=page_ids, **job_filter)
        .select_related(
            "page_a",
            "page_b__report__event_team__team",
            "page_b__report__event_team__event",
        )
        .order_by("-similarity")
    )
    matches_b = (
        PageMatch.objects
        .filter(page_b_id__in=page_ids, **job_filter)
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

    # Compute word counts for all pages that appear in pairs (one bulk query).
    all_pair_page_ids = set()
    for g in groups.values():
        for pair in g["page_pairs"]:
            all_pair_page_ids.add(pair["this_page"].page_id)
            all_pair_page_ids.add(pair["other_page"].page_id)
    word_counts = {}
    for chunk in ReportChunk.objects.filter(page_id__in=all_pair_page_ids).values("page_id", "text"):
        word_counts[chunk["page_id"]] = word_counts.get(chunk["page_id"], 0) + len(chunk["text"].split())
    for g in groups.values():
        for pair in g["page_pairs"]:
            pair["this_word_count"] = word_counts.get(pair["this_page"].page_id, 0)
            pair["other_word_count"] = word_counts.get(pair["other_page"].page_id, 0)
            pair["min_word_count"] = min(pair["this_word_count"], pair["other_word_count"])
            pair["sort_score"] = pair["min_word_count"] * pair["similarity"]
        g["page_pairs"].sort(key=lambda p: p["sort_score"], reverse=True)
        g["max_sort_score"] = g["page_pairs"][0]["sort_score"] if g["page_pairs"] else 0

    match_groups = sorted(groups.values(), key=lambda g: g["max_sort_score"], reverse=True)
    return match_groups, False


# ── Report match list ─────────────────────────────────────────────────────────
def report_matches(request, report_id):
    _require_staff(request)

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    page_ids = list(ReportPage.objects.filter(report=report).values_list("page_id", flat=True))
    candidate_qs = PageMatch.objects.filter(
        Q(page_a_id__in=page_ids) | Q(page_b_id__in=page_ids)
    )
    selected_job, available_jobs = _resolve_job_param(request, candidate_qs)

    match_groups, no_pages = _get_text_match_groups(report, job_id=selected_job)

    return render(request, "reports/report_matches.html", {
        "report": report,
        "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
        "match_groups": match_groups,
        "no_pages": no_pages,
        "available_jobs": available_jobs,
        "selected_job": selected_job,
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

    # image match counts per report (matches in either direction)
    img_match_counts = {}
    for row in (
        ImageMatch.objects
        .filter(image_a__report_id__in=report_ids)
        .values("image_a__report_id")
        .annotate(n=Count("image_match_id"))
    ):
        rid = row["image_a__report_id"]
        img_match_counts[rid] = img_match_counts.get(rid, 0) + row["n"]
    for row in (
        ImageMatch.objects
        .filter(image_b__report_id__in=report_ids)
        .values("image_b__report_id")
        .annotate(n=Count("image_match_id"))
    ):
        rid = row["image_b__report_id"]
        img_match_counts[rid] = img_match_counts.get(rid, 0) + row["n"]

    report_data = [
        {
            "report": r,
            "page_count": stats_by_report.get(r.report_id, {}).get("page_count", 0),
            "chunk_count": stats_by_report.get(r.report_id, {}).get("chunk_count", 0),
            "image_match_count": img_match_counts.get(r.report_id, 0),
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

    # Image similarity per page: min Hamming distance among all images on that page.
    # pHash is 64-bit, so similarity = (1 - hamming/64) * 100.
    image_info = {
        img["image_id"]: (img["report_id"], img["page_number"])
        for img in ReportImage.objects
            .filter(report_id__in=report_ids)
            .values("image_id", "report_id", "page_number")
    }
    image_ids = list(image_info.keys())
    image_min_hamming = {}  # image_id → lowest Hamming distance found
    if image_ids:
        for row in ImageMatch.objects.filter(image_a_id__in=image_ids).values("image_a_id").annotate(mh=Min("hamming_distance")):
            iid = row["image_a_id"]
            image_min_hamming[iid] = min(image_min_hamming.get(iid, 64), row["mh"])
        for row in ImageMatch.objects.filter(image_b_id__in=image_ids).values("image_b_id").annotate(mh=Min("hamming_distance")):
            iid = row["image_b_id"]
            image_min_hamming[iid] = min(image_min_hamming.get(iid, 64), row["mh"])
    # report_id → {page_number: best image similarity pct on that page}
    report_page_img_sims = {r.report_id: {} for r in reports}
    for iid, (rid, pnum) in image_info.items():
        if iid in image_min_hamming:
            img_sim_pct = round((1 - image_min_hamming[iid] / 64) * 100)
            existing = report_page_img_sims[rid].get(pnum, 0)
            report_page_img_sims[rid][pnum] = max(existing, img_sim_pct)

    # AI detection: median fake_percentage across detectors per page_id.
    ai_pcts_by_page = {}  # page_id → list of fake_pct values (one per detector)
    for row in (
        AIDetectionResult.objects
        .filter(page_id__in=page_ids)
        .values("page_id", "fake_percentage")
    ):
        ai_pcts_by_page.setdefault(row["page_id"], []).append(row["fake_percentage"])
    ai_pct_by_page = {
        pid: statistics.median(vals) for pid, vals in ai_pcts_by_page.items()
    }
    # report_id → {page_number: ai median fake_pct}
    report_page_ai = {r.report_id: {} for r in reports}
    for pid, (rid, pnum) in page_info.items():
        if pid in ai_pct_by_page:
            report_page_ai[rid][pnum] = round(ai_pct_by_page[pid])

    rows = []
    for pnum in all_page_numbers:
        cells = []
        for r in reports:
            ps = report_page_sims[r.report_id]
            if pnum not in ps:
                cells.append(None)  # this report doesn't have this page
            else:
                sim = ps[pnum] or 0.0
                cells.append({
                    "report_id": r.report_id,
                    "sim_pct": round(sim * 100),
                    "img_sim_pct": report_page_img_sims[r.report_id].get(pnum),  # None = no img matches
                    "ai_pct": report_page_ai[r.report_id].get(pnum),  # None = not analyzed
                })
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


# ── Report coverage matrix ────────────────────────────────────────────────────
def report_coverage(request):
    _require_staff(request)

    try:
        report_type = int(request.GET.get("report_type", 1))
    except (TypeError, ValueError):
        report_type = 1

    events = list(Event.objects.order_by("-event_datetime"))

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

    # Teams that appear in at least one of these events, sorted by name.
    teams = list(
        Team.objects
        .filter(event_teams__event__in=events)
        .distinct()
        .order_by("team_number")
    )

    event_ids = [e.event_id for e in events]
    team_ids  = [t.team_id  for t in teams]

    # Which (event_id, team_id) pairs have an EventTeam record.
    participation = set(
        EventTeam.objects
        .filter(event_id__in=event_ids, team_id__in=team_ids)
        .values_list("event_id", "team_id")
    )

    # Which pairs have a report of the selected type.
    has_report = set(
        Report.objects
        .filter(report_type=report_type, event_team__event_id__in=event_ids)
        .values_list("event_team__event_id", "event_team__team_id")
    )

    rows = []
    for event in events:
        cells = []
        for team in teams:
            key = (event.event_id, team.team_id)
            if key not in participation:
                cells.append(None)          # didn't participate
            elif key in has_report:
                cells.append(True)          # submitted
            else:
                cells.append(False)         # participated but no report
        rows.append({"event": event, "cells": cells})

    return render(request, "reports/report_coverage.html", {
        "report_type": report_type,
        "report_type_label": REPORT_TYPE_LABELS.get(report_type, f"Type {report_type}"),
        "report_type_choices": report_type_choices,
        "teams": teams,
        "rows": rows,
    })


# ── Image match grouping helper ───────────────────────────────────────────────

def _get_image_match_groups(report, job_id=None):
    """Return (match_groups, no_images) for a report's image similarity matches.

    match_groups is a list of dicts sorted by min_hamming ascending.
    Each dict has: other_report, team_name, event_name, report_type_label,
    image_pairs (list), min_hamming.
    """
    image_ids = list(ReportImage.objects.filter(report=report).values_list("image_id", flat=True))

    if not image_ids:
        return [], True

    job_filter = {"job_id": job_id} if job_id is not None else {}

    matches_a = (
        ImageMatch.objects
        .filter(image_a_id__in=image_ids, **job_filter)
        .select_related("image_a", "image_b__report__event_team__team", "image_b__report__event_team__event")
        .order_by("hamming_distance")
    )
    matches_b = (
        ImageMatch.objects
        .filter(image_b_id__in=image_ids, **job_filter)
        .select_related("image_b", "image_a__report__event_team__team", "image_a__report__event_team__event")
        .order_by("hamming_distance")
    )

    groups = {}  # other_report_id → dict

    def _add(this_img, other_img, other_report, distance, im_id):
        key = other_report.report_id
        if key not in groups:
            groups[key] = {
                "other_report": other_report,
                "team_name": getattr(getattr(other_report.event_team, "team", None), "team_name", "?"),
                "event_name": getattr(getattr(other_report.event_team, "event", None), "event_name", "?"),
                "report_type_label": REPORT_TYPE_LABELS.get(other_report.report_type, f"Type {other_report.report_type}"),
                "image_pairs": [],
                "min_hamming": 999,
            }
        groups[key]["image_pairs"].append({
            "this_img": this_img,
            "other_img": other_img,
            "hamming_distance": distance,
            "image_match_id": im_id,
        })
        groups[key]["min_hamming"] = min(groups[key]["min_hamming"], distance)

    for m in matches_a:
        _add(m.image_a, m.image_b, m.image_b.report, m.hamming_distance, m.image_match_id)
    for m in matches_b:
        _add(m.image_b, m.image_a, m.image_a.report, m.hamming_distance, m.image_match_id)

    match_groups = sorted(groups.values(), key=lambda g: g["min_hamming"])
    return match_groups, False


# ── Image match list ──────────────────────────────────────────────────────────
def report_image_matches(request, report_id):
    _require_staff(request)

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    image_ids = list(ReportImage.objects.filter(report=report).values_list("image_id", flat=True))
    candidate_qs = ImageMatch.objects.filter(
        Q(image_a_id__in=image_ids) | Q(image_b_id__in=image_ids)
    )
    selected_job, available_jobs = _resolve_job_param(request, candidate_qs)

    match_groups, no_images = _get_image_match_groups(report, job_id=selected_job)

    return render(request, "reports/report_image_matches.html", {
        "report": report,
        "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
        "match_groups": match_groups,
        "no_images": no_images,
        "available_jobs": available_jobs,
        "selected_job": selected_job,
    })


# ── Image helpers ─────────────────────────────────────────────────────────────

_PDF_CACHE_TTL   = 3600   # seconds — how long to keep a raw PDF in Redis
_JPEG_CACHE_TTL  = 3600   # seconds — how long to keep a rendered JPEG in Redis


def _get_pdf_bytes(report_id):
    """Fetch raw PDF bytes for a report, using Redis cache."""
    pdf_key = f"report_pdf:{report_id}"
    pdf_bytes = cache.get(pdf_key)
    if pdf_bytes is None:
        token = getattr(settings, "INTERNAL_REPORT_TOKEN", "")
        headers = {"X-Internal-Token": token} if token else {}
        url = f"https://iqsconnect.org/reports/{report_id}"
        resp = http_requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        pdf_bytes = resp.content
        cache.set(pdf_key, pdf_bytes, timeout=_PDF_CACHE_TTL)
    return pdf_bytes


def _extract_image_jpeg(report_image):
    """Extract a ReportImage as JPEG bytes.  Returns bytes or None."""
    jpeg_key = f"img_jpeg:{report_image.image_id}"
    jpeg_bytes = cache.get(jpeg_key)
    if jpeg_bytes is not None:
        return jpeg_bytes
    try:
        pdf_bytes = _get_pdf_bytes(report_image.report_id)
        from pypdf import PdfReader
        from PIL import Image

        reader = PdfReader(io.BytesIO(pdf_bytes))
        page = reader.pages[report_image.page_number - 1]
        img_obj = list(page.images)[report_image.image_index]
        pil_img = Image.open(io.BytesIO(img_obj.data)).convert("RGB")

        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=85)
        jpeg_bytes = buf.getvalue()
        cache.set(jpeg_key, jpeg_bytes, timeout=_JPEG_CACHE_TTL)
        return jpeg_bytes
    except Exception:
        return None


# ── Image serve ───────────────────────────────────────────────────────────────

def image_serve(request, image_id):
    _require_staff(request)

    rim = get_object_or_404(ReportImage, pk=image_id)

    # Level 1: return the rendered JPEG straight from cache if available.
    jpeg_key = f"img_jpeg:{image_id}"
    jpeg_bytes = cache.get(jpeg_key)
    if jpeg_bytes is not None:
        return HttpResponse(jpeg_bytes, content_type="image/jpeg")

    jpeg_bytes = _extract_image_jpeg(rim)
    if jpeg_bytes is None:
        raise Http404("Could not extract image from PDF")
    return HttpResponse(jpeg_bytes, content_type="image/jpeg")


# ── Image match detail ────────────────────────────────────────────────────────
def image_match_detail(request, image_match_id):
    _require_staff(request)

    im = get_object_or_404(
        ImageMatch.objects.select_related(
            "image_a__report__event_team__team",
            "image_a__report__event_team__event",
            "image_b__report__event_team__team",
            "image_b__report__event_team__event",
        ),
        pk=image_match_id,
    )

    team_a = getattr(getattr(im.image_a.report.event_team, "team", None), "team_name", "?")
    team_b = getattr(getattr(im.image_b.report.event_team, "team", None), "team_name", "?")

    try:
        from_report_id = int(request.GET.get("from_report", 0))
    except (TypeError, ValueError):
        from_report_id = 0

    if from_report_id == im.image_b.report_id:
        back_report_id = im.image_b.report_id
        back_team = team_b
    else:
        back_report_id = im.image_a.report_id
        back_team = team_a

    last_page_a = (
        ReportPage.objects.filter(report=im.image_a.report)
        .order_by("-page_number").values_list("page_number", flat=True).first()
    )
    last_page_b = (
        ReportPage.objects.filter(report=im.image_b.report)
        .order_by("-page_number").values_list("page_number", flat=True).first()
    )

    return render(request, "reports/image_match_detail.html", {
        "im": im,
        "team_a": team_a,
        "team_b": team_b,
        "back_report_id": back_report_id,
        "back_team": back_team,
        "last_page_a": last_page_a,
        "last_page_b": last_page_b,
    })


# ── Report extracted content ──────────────────────────────────────────────────
def report_extracted(request, report_id):
    _require_staff(request)

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    pages = list(
        ReportPage.objects
        .filter(report=report)
        .prefetch_related("chunks")
        .order_by("page_number")
    )

    images = list(
        ReportImage.objects
        .filter(report=report)
        .order_by("page_number", "image_index")
    )

    chunk_data = []
    for page in pages:
        for chunk in page.chunks.all():
            if chunk.bbox_x0 is not None:
                chunk_data.append({
                    "id": f"chunk-{chunk.chunk_id}",
                    "page_number": page.page_number,
                    "x0": chunk.bbox_x0,
                    "y0": chunk.bbox_y0,
                    "x1": chunk.bbox_x1,
                    "y1": chunk.bbox_y1,
                })

    team_name = getattr(getattr(report.event_team, "team", None), "team_name", "?")
    event_name = getattr(getattr(report.event_team, "event", None), "event_name", "?")

    return render(request, "reports/report_extracted.html", {
        "report": report,
        "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
        "team_name": team_name,
        "event_name": event_name,
        "pages": pages,
        "images": images,
        "chunk_data_json": json.dumps(chunk_data),
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

    try:
        from_report_id = int(request.GET.get("from_report", 0))
    except (TypeError, ValueError):
        from_report_id = 0

    if from_report_id == pm.page_b.report_id:
        back_report_id = pm.page_b.report_id
        back_team = team_b
    else:
        back_report_id = pm.page_a.report_id
        back_team = team_a

    last_page_a = (
        ReportPage.objects.filter(report=pm.page_a.report)
        .order_by("-page_number").values_list("page_number", flat=True).first()
    )
    last_page_b = (
        ReportPage.objects.filter(report=pm.page_b.report)
        .order_by("-page_number").values_list("page_number", flat=True).first()
    )

    return render(request, "reports/page_match_detail.html", {
        "pm": pm,
        "team_a": team_a,
        "team_b": team_b,
        "back_report_id": back_report_id,
        "back_team": back_team,
        "chunk_matches": chunk_matches,
        "chunk_links_json": json.dumps(chunk_links),
        "left_chunk_data_json": _chunk_data(a_chunks, matched_a_ids),
        "right_chunk_data_json": _chunk_data(b_chunks, matched_b_ids),
        "last_page_a": last_page_a,
        "last_page_b": last_page_b,
    })


# ── Retrigger AI detection for a single report ────────────────────────────────
def retrigger_ai_detection(request, report_id):
    _require_staff(request)
    if not request.user.has_perm("reports.can_run_ai_detection"):
        raise Http404()
    if request.method != "POST":
        raise Http404()

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    has_any_key = any([
        getattr(settings, "ZEROGPT_API_KEY", ""),
        getattr(settings, "GPTZERO_API_KEY", ""),
        getattr(settings, "COPYLEAKS_API_KEY", ""),
    ])
    if not has_any_key:
        messages.error(request, "No AI detection API keys are configured — cannot queue AI detection.")
        return redirect("reports:report_ai_detection", report_id=report_id)

    valid_keys = {c[0] for c in AIDetectionResult.Detectors.choices}
    selected_detectors = [d for d in request.POST.getlist("detectors") if d in valid_keys]
    if not selected_detectors:
        selected_detectors = list(valid_keys)
    detectors_str = ",".join(selected_detectors)

    event = getattr(report.event_team, "event", None)
    job = AnalysisJob.objects.create(
        job_type=AnalysisJob.JobTypes.AI_DETECTION,
        event=event,
        status=AnalysisJob.Statuses.QUEUED,
        detectors=detectors_str,
    )

    from .tasks import run_ai_detection_report
    run_ai_detection_report.delay(report.pk, job_id=job.pk)
    messages.success(
        request,
        f"AI detection queued for {report.event_team.team.team_name} "
        f"({report.event_team.event.event_name}). Refresh in a moment to see updated results.",
    )
    return redirect("reports:report_ai_detection", report_id=report_id)


# ── Methodology explanations ──────────────────────────────────────────────────
def methodology_image(request, image_match_id=None):
    """Interactive walkthrough of the pHash image similarity algorithm.

    When called with image_match_id (via the methodology_image_match URL), it pins
    to that specific match instead of picking a random one.
    """
    _require_staff(request)

    pinned = image_match_id is not None

    if pinned:
        im = get_object_or_404(
            ImageMatch.objects.select_related(
                "image_a__report__event_team__team",
                "image_a__report__event_team__event",
                "image_b__report__event_team__team",
                "image_b__report__event_team__event",
            ),
            pk=image_match_id,
        )
    else:
        def _pick_match(min_d, max_d):
            qs = (
                ImageMatch.objects
                .select_related(
                    "image_a__report__event_team__team",
                    "image_a__report__event_team__event",
                    "image_b__report__event_team__team",
                    "image_b__report__event_team__event",
                )
                .filter(hamming_distance__gte=min_d, hamming_distance__lte=max_d)
            )
            count = qs.count()
            if not count:
                return None
            return qs[random.randint(0, count - 1)]

        # Prefer a slightly-different pair so the bit diff is interesting
        im = _pick_match(1, 8) or _pick_match(0, 64)

    if not im:
        return render(request, "reports/methodology_image.html", {"no_data": True, "pinned": False})

    def _hex_to_bits(h):
        return bin(int(h, 16))[2:].zfill(64)

    bits_a = _hex_to_bits(im.image_a.phash)
    bits_b = _hex_to_bits(im.image_b.phash)

    # 8×8 grids for template rendering
    bit_grid_a    = [list(bits_a[i * 8:(i + 1) * 8]) for i in range(8)]
    bit_grid_b    = [list(bits_b[i * 8:(i + 1) * 8]) for i in range(8)]
    bit_grid_diff = [
        [bits_a[i * 8 + j] != bits_b[i * 8 + j] for j in range(8)]
        for i in range(8)
    ]
    # Flat list of 64 bit-pair dicts for Hamming diff view
    bit_pairs = [
        {"a": bits_a[i], "b": bits_b[i], "diff": bits_a[i] != bits_b[i]}
        for i in range(64)
    ]
    # Combined grid: list of 8 rows, each row = list of 8 cell dicts
    bit_grid_cmp = [
        [
            {"a": bits_a[i * 8 + j], "b": bits_b[i * 8 + j],
             "diff": bits_a[i * 8 + j] != bits_b[i * 8 + j]}
            for j in range(8)
        ]
        for i in range(8)
    ]

    team_a = getattr(getattr(im.image_a.report.event_team, "team", None), "team_name", "?")
    team_b = getattr(getattr(im.image_b.report.event_team, "team", None), "team_name", "?")

    image_a_url = request.build_absolute_uri(
        reverse("reports:image_serve", args=[im.image_a.image_id])
    )
    image_b_url = request.build_absolute_uri(
        reverse("reports:image_serve", args=[im.image_b.image_id])
    )

    return render(request, "reports/methodology_image.html", {
        "no_data": False,
        "pinned": pinned,
        "im": im,
        "team_a": team_a,
        "team_b": team_b,
        "bits_a": bits_a,
        "bits_b": bits_b,
        "bit_grid_a": bit_grid_a,
        "bit_grid_b": bit_grid_b,
        "bit_grid_diff": bit_grid_diff,
        "bit_pairs": bit_pairs,
        "bit_grid_cmp": bit_grid_cmp,
        "image_a_url": image_a_url,
        "image_b_url": image_b_url,
        "image_a_id": im.image_a.image_id,
        "image_b_id": im.image_b.image_id,
        "phash_a": im.image_a.phash,
        "phash_b": im.image_b.phash,
        "hamming": im.hamming_distance,
        "similarity_pct": round((1 - im.hamming_distance / 64) * 100, 1),
    })

def methodology_text(request):
    """Interactive walkthrough of the text shingling / Jaccard similarity algorithm."""
    _require_staff(request)

    SHINGLE_K = 5

    def _normalize(text):
        text = text.lower()
        text = re.sub(r"\s+", " ", text)
        return re.findall(r"[a-z0-9']+", text)

    def _shingles(words, k):
        if len(words) < k:
            return []
        return [" ".join(words[i: i + k]) for i in range(len(words) - k + 1)]

    MIN_WORDS = 8

    def _pick_chunk_match(min_sim):
        qs = (
            ChunkMatch.objects
            .filter(similarity__gte=min_sim)
            .select_related(
                "chunk_a__page__report__event_team__team",
                "chunk_b__page__report__event_team__team",
                "page_match",
            )
        )
        candidates = [
            cm for cm in qs
            if len(cm.chunk_a.text.split()) > MIN_WORDS
            and len(cm.chunk_b.text.split()) > MIN_WORDS
        ]
        if not candidates:
            return None
        return random.choice(candidates)

    cm = _pick_chunk_match(0.6) or _pick_chunk_match(0.0)

    if not cm:
        return render(request, "reports/methodology_text.html", {"no_data": True})

    text_a = cm.chunk_a.text
    text_b = cm.chunk_b.text

    words_a = _normalize(text_a)
    words_b = _normalize(text_b)

    # Word-set Jaccard (used by ChunkMatch)
    set_words_a = set(words_a)
    set_words_b = set(words_b)
    word_intersection = set_words_a & set_words_b
    word_union = set_words_a | set_words_b
    word_jaccard = len(word_intersection) / len(word_union) if word_union else 0.0

    # Shingle-based Jaccard (concept used for PageMatch via MinHash)
    shingles_a = _shingles(words_a, SHINGLE_K)
    shingles_b = _shingles(words_b, SHINGLE_K)
    set_sh_a = set(shingles_a)
    set_sh_b = set(shingles_b)
    sh_shared = sorted(set_sh_a & set_sh_b)
    sh_only_a = sorted(set_sh_a - set_sh_b)
    sh_only_b = sorted(set_sh_b - set_sh_a)
    sh_union_count = len(set_sh_a | set_sh_b)
    shingle_jaccard = len(sh_shared) / sh_union_count if sh_union_count else 0.0

    # Sliding window demonstration: first 8 shingles with per-word highlight data
    window_demo = []
    for start_idx, sh in enumerate(shingles_a[:8]):
        word_display = words_a[:start_idx + SHINGLE_K + 4]  # show a bit of context
        window_demo.append({
            "shingle": sh,
            "start": start_idx,
            "end": start_idx + SHINGLE_K,
            "words": [
                {"word": w, "active": start_idx <= wi < start_idx + SHINGLE_K}
                for wi, w in enumerate(word_display)
            ],
        })

    team_a = getattr(getattr(cm.chunk_a.page.report.event_team, "team", None), "team_name", "?")
    team_b = getattr(getattr(cm.chunk_b.page.report.event_team, "team", None), "team_name", "?")

    return render(request, "reports/methodology_text.html", {
        "no_data": False,
        "cm": cm,
        "team_a": team_a,
        "team_b": team_b,
        "text_a": text_a,
        "text_b": text_b,
        "words_a": words_a[:40],          # cap for display
        "words_b": words_b[:40],
        "shingle_k": SHINGLE_K,
        "window_demo": window_demo,
        "words_a_display": words_a[:30],
        "words_b_display": words_b[:30],
        "shingles_a": sorted(set_sh_a),
        "shingles_b": sorted(set_sh_b),
        "sh_shared": sh_shared,
        "sh_only_a": sh_only_a,
        "sh_only_b": sh_only_b,
        "sh_count_a": len(set_sh_a),
        "sh_count_b": len(set_sh_b),
        "sh_intersection": len(sh_shared),
        "sh_union": sh_union_count,
        "shingle_jaccard": round(shingle_jaccard * 100, 1),
        "word_set_a": sorted(set_words_a),
        "word_set_b": sorted(set_words_b),
        "word_intersection": sorted(word_intersection),
        "word_union_count": len(word_union),
        "word_intersection_count": len(word_intersection),
        "word_jaccard": round(word_jaccard * 100, 1),
        "stored_chunk_sim": round(cm.similarity * 100, 1),
        "stored_page_sim": round(cm.page_match.similarity * 100, 1),
    })


# ── AI Detection report ───────────────────────────────────────────────────────
def report_ai_detection(request, report_id):
    _require_staff(request)

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    # Resolve job selector.
    candidate_qs = AIDetectionResult.objects.filter(page__report=report)
    selected_job, available_jobs = _resolve_job_param(request, candidate_qs)

    # Resolve detector selector.
    _key_map = {
        AIDetectionResult.Detectors.ZEROGPT: bool(getattr(settings, "ZEROGPT_API_KEY", "")),
        AIDetectionResult.Detectors.GPTZERO: bool(getattr(settings, "GPTZERO_API_KEY", "")),
        AIDetectionResult.Detectors.COPYLEAKS: bool(getattr(settings, "COPYLEAKS_API_KEY", "")),
    }
    # List of (value, label, is_configured) for template tab strip.
    detector_info = [
        (val, label, _key_map.get(val, False))
        for val, label in AIDetectionResult.Detectors.choices
    ]
    requested_detector = request.GET.get("detector", AIDetectionResult.Detectors.ZEROGPT)
    if requested_detector not in _key_map:
        requested_detector = AIDetectionResult.Detectors.ZEROGPT
    selected_detector = requested_detector

    # Build result lookup: page_id → AIDetectionResult for selected job+detector.
    result_filter = {"page__report": report, "detector": selected_detector}
    if selected_job is not None:
        result_filter["job_id"] = selected_job
    else:
        result_filter["job__isnull"] = True

    results_by_page = {
        r.page_id: r
        for r in AIDetectionResult.objects.filter(**result_filter).prefetch_related("sentences")
    }

    pages = list(
        ReportPage.objects
        .filter(report=report)
        .prefetch_related("chunks")
        .order_by("page_number")
    )

    page_data = []
    total_ai_words = 0
    total_text_words = 0
    analyzed_count = 0
    chunk_data = []

    for page in pages:
        result = results_by_page.get(page.page_id)

        flagged_sentences = []
        if result:
            analyzed_count += 1
            total_ai_words += result.ai_words
            total_text_words += result.text_words
            for s in result.sentences.all():
                if s.text:
                    flagged_sentences.append({
                        "text": s.text,
                        "probability": s.generated_probability,
                    })

        for chunk in page.chunks.order_by("chunk_index"):
            if chunk.bbox_x0 is None:
                continue
            matching = [
                s for s in flagged_sentences
                if s["text"] in chunk.text or chunk.text in s["text"]
            ]
            chunk_data.append({
                "id": f"chunk-{chunk.chunk_id}",
                "page_number": page.page_number,
                "x0": chunk.bbox_x0,
                "y0": chunk.bbox_y0,
                "x1": chunk.bbox_x1,
                "y1": chunk.bbox_y1,
                "flagged": bool(matching),
                "sentences": matching,
            })

        page_data.append({
            "page": page,
            "result": result,
            "flagged_sentences": flagged_sentences,
        })

    avg_fake_pct = None
    median_fake_pct = None
    if analyzed_count:
        pcts = [pd["result"].fake_percentage for pd in page_data if pd["result"]]
        avg_fake_pct = round(sum(pcts) / len(pcts), 1)
        median_fake_pct = round(statistics.median(pcts), 1)

    # Build cross-detector comparison: page_number → {detector: fake_pct}
    all_job_filter = {"page__report": report}
    if selected_job is not None:
        all_job_filter["job_id"] = selected_job
    else:
        all_job_filter["job__isnull"] = True

    detector_pcts = {}  # page_id → {detector: fake_pct}
    for r in AIDetectionResult.objects.filter(**all_job_filter).values("page_id", "detector", "fake_percentage"):
        detector_pcts.setdefault(r["page_id"], {})[r["detector"]] = r["fake_percentage"]

    detectors_with_data = {d for pcts in detector_pcts.values() for d in pcts}
    active_detectors = [(val, label) for val, label, _ in detector_info if val in detectors_with_data]

    comparison_rows = []
    for page in pages:
        pcts = detector_pcts.get(page.page_id, {})
        if not pcts:
            continue
        vals = [pcts.get(val) for val, label in active_detectors]
        non_none = [v for v in vals if v is not None]
        avg = sum(non_none) / len(non_none) if non_none else None
        med = statistics.median(non_none) if non_none else None
        comparison_rows.append({
            "page_number": page.page_number,
            "pcts": [(val, label, pcts.get(val)) for val, label in active_detectors],
            "avg": round(avg, 1) if avg is not None else None,
            "median": round(med, 1) if med is not None else None,
        })

    return render(request, "reports/report_ai_detection.html", {
        "report": report,
        "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
        "page_data": page_data,
        "analyzed_count": analyzed_count,
        "total_pages": len(page_data),
        "avg_fake_pct": avg_fake_pct,
        "median_fake_pct": median_fake_pct,
        "total_ai_words": total_ai_words,
        "total_text_words": total_text_words,
        "chunk_data_json": json.dumps(chunk_data),
        "can_run_ai_detection": request.user.has_perm("reports.can_run_ai_detection"),
        "comparison_rows": comparison_rows,
        "active_detectors": active_detectors,
        "available_jobs": available_jobs,
        "selected_job": selected_job,
        "detector_info": detector_info,
        "selected_detector": selected_detector,
    })


# ── PDF export ───────────────────────────────────────────────────────────────

def _generate_plagiarism_pdf(report):
    """Generate plagiarism PDF bytes for a single Report.

    Returns (pdf_bytes, filename).  Usable from both the view and Celery tasks.
    """
    from pdf2image import convert_from_bytes
    from PIL import Image
    import weasyprint

    team_name = getattr(report.event_team.team, "team_name", "?")
    event_name = getattr(report.event_team.event, "event_name", "?")
    report_type_label = REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}")

    # ── Summary stats ────────────────────────────────────────────────────
    page_count = ReportPage.objects.filter(report=report).count()
    chunk_count = ReportChunk.objects.filter(page__report=report).count()
    image_count = ReportImage.objects.filter(report=report).count()

    chunk_texts = ReportChunk.objects.filter(page__report=report).values_list("text", flat=True)
    total_text_words = sum(len(t.split()) for t in chunk_texts)

    text_matches_qs = PageMatch.objects.filter(Q(page_a__report=report) | Q(page_b__report=report))
    text_match_count = text_matches_qs.count()
    best_text_sim_raw = text_matches_qs.order_by("-similarity").values_list("similarity", flat=True).first()
    best_text_sim = round(best_text_sim_raw * 100, 1) if best_text_sim_raw is not None else None

    image_matches_qs = ImageMatch.objects.filter(Q(image_a__report=report) | Q(image_b__report=report))
    image_match_count = image_matches_qs.count()
    best_hamming = image_matches_qs.order_by("hamming_distance").values_list("hamming_distance", flat=True).first()
    best_image_sim = round((1 - best_hamming / 64) * 100, 1) if best_hamming is not None else None

    # ── Top text match group ─────────────────────────────────────────────
    text_match_groups, _ = _get_text_match_groups(report)
    top_text_group = text_match_groups[0] if text_match_groups else None

    text_pair_details = []
    if top_text_group:
        sorted_pairs = sorted(top_text_group["page_pairs"], key=lambda p: p["this_page"].page_number)

        # Collect all unique (report_id, page_number) pairs we need to render.
        pages_to_render = {}
        for pair in sorted_pairs:
            pages_to_render[(pair["this_page"].report_id, pair["this_page"].page_number)] = None
            pages_to_render[(pair["other_page"].report_id, pair["other_page"].page_number)] = None

        # Render PDF pages to JPEG using pdf2image (poppler).
        report_ids_needed = {rid for rid, _ in pages_to_render}
        for rid in report_ids_needed:
            try:
                raw_pdf = _get_pdf_bytes(rid)
            except Exception:
                continue
            needed_pages = sorted({pn for r, pn in pages_to_render if r == rid})
            try:
                pil_pages = convert_from_bytes(
                    raw_pdf,
                    first_page=min(needed_pages),
                    last_page=max(needed_pages),
                    dpi=150,
                )
                base = min(needed_pages)
                rendered = {base + i: img for i, img in enumerate(pil_pages)}
                for pn in needed_pages:
                    pil_img = rendered.get(pn)
                    if pil_img is None:
                        continue
                    if pil_img.width > 500:
                        ratio = 500 / pil_img.width
                        pil_img = pil_img.resize(
                            (500, int(pil_img.height * ratio)), Image.LANCZOS
                        )
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=80)
                    pages_to_render[(rid, pn)] = base64.b64encode(buf.getvalue()).decode()
            except Exception:
                pass

        for pair in sorted_pairs:
            pm = PageMatch.objects.get(pk=pair["page_match_id"])
            chunk_matches = list(
                ChunkMatch.objects
                .filter(page_match=pm)
                .select_related("chunk_a", "chunk_b")
                .order_by("-similarity")
            )
            text_pair_details.append({
                "this_page_num": pair["this_page"].page_number,
                "other_page_num": pair["other_page"].page_number,
                "similarity": round(pair["similarity"] * 100, 1),
                "this_page_b64": pages_to_render.get(
                    (pair["this_page"].report_id, pair["this_page"].page_number)
                ),
                "other_page_b64": pages_to_render.get(
                    (pair["other_page"].report_id, pair["other_page"].page_number)
                ),
                "chunk_matches": [
                    {
                        "similarity": round(cm.similarity * 100, 1),
                        "text_a": cm.chunk_a.text,
                        "text_b": cm.chunk_b.text,
                    }
                    for cm in chunk_matches
                ],
            })

    # ── All image matches ────────────────────────────────────────────────
    img_match_groups, _ = _get_image_match_groups(report)

    for group in img_match_groups:
        for pair in group["image_pairs"]:
            pair["similarity_pct"] = round((1 - pair["hamming_distance"] / 64) * 100, 1)

            for key in ("this_img", "other_img"):
                rim = pair[key]
                jpeg_bytes = _extract_image_jpeg(rim)
                if jpeg_bytes:
                    pil_img = Image.open(io.BytesIO(jpeg_bytes))
                    if pil_img.width > 400:
                        ratio = 400 / pil_img.width
                        new_size = (400, int(pil_img.height * ratio))
                        pil_img = pil_img.resize(new_size, Image.LANCZOS)
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=85)
                    pair[f"{key}_b64"] = base64.b64encode(buf.getvalue()).decode()
                else:
                    pair[f"{key}_b64"] = None

    # ── Render HTML and convert to PDF ───────────────────────────────────
    context = {
        "report": report,
        "team_name": team_name,
        "event_name": event_name,
        "report_type_label": report_type_label,
        "export_date": timezone.now(),
        "page_count": page_count,
        "chunk_count": chunk_count,
        "image_count": image_count,
        "total_text_words": total_text_words,
        "text_match_count": text_match_count,
        "best_text_sim": best_text_sim,
        "image_match_count": image_match_count,
        "best_image_sim": best_image_sim,
        "top_text_group": top_text_group,
        "text_pair_details": text_pair_details,
        "img_match_groups": img_match_groups,
    }

    html_string = render_to_string("reports/export_pdf.html", context)
    pdf_bytes = weasyprint.HTML(string=html_string).write_pdf()

    safe_team = re.sub(r"[^\w\-]", "_", team_name)
    filename = f"plagiarism_report_{safe_team}_{report.report_id}.pdf"

    return pdf_bytes, filename


def report_export_pdf(request, report_id):
    """Generate a downloadable PDF plagiarism report for a single report."""
    _require_staff(request)

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    pdf_bytes, filename = _generate_plagiarism_pdf(report)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
