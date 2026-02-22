import io
import json

from django.core.cache import cache
from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Max, Min, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

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
            raw_event = request.POST.get("event_id", "").strip()
            event_id = int(raw_event) if raw_event.isdigit() else None
            if not event_id:
                messages.error(request, "AI detection requires an event to be selected.")
                return redirect("reports:analysis_dashboard")
            job = AnalysisJob.objects.create(
                report_type=report_type,
                job_type=AnalysisJob.JobTypes.AI_DETECTION,
                event_id=event_id,
            )
            from .tasks import run_ai_detection
            run_ai_detection.delay(job.pk)
            messages.success(request, f"AI detection job #{job.pk} queued.")
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

    return render(request, "reports/analysis_dashboard.html", {
        "jobs": jobs,
        "active_job_ids_json": json.dumps(active_job_ids),
        "report_type_choices": report_type_choices,
        "events": events,
    })


def analysis_job_status(request, job_id):
    _require_staff(request)
    job = get_object_or_404(AnalysisJob, pk=job_id)
    return JsonResponse({
        "job_id": job.job_id,
        "job_type": job.job_type,
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

    # AI detection fake_percentage per page_id.
    ai_pct_by_page = {
        r["page_id"]: r["fake_percentage"]
        for r in AIDetectionResult.objects
            .filter(page_id__in=page_ids)
            .values("page_id", "fake_percentage")
    }
    # report_id → {page_number: ai fake_pct}
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


# ── Image match list ──────────────────────────────────────────────────────────

def report_image_matches(request, report_id):
    _require_staff(request)

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    image_ids = list(ReportImage.objects.filter(report=report).values_list("image_id", flat=True))

    if not image_ids:
        return render(request, "reports/report_image_matches.html", {
            "report": report,
            "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
            "match_groups": [],
            "no_images": True,
        })

    matches_a = (
        ImageMatch.objects
        .filter(image_a_id__in=image_ids)
        .select_related("image_a", "image_b__report__event_team__team", "image_b__report__event_team__event")
        .order_by("hamming_distance")
    )
    matches_b = (
        ImageMatch.objects
        .filter(image_b_id__in=image_ids)
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

    return render(request, "reports/report_image_matches.html", {
        "report": report,
        "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
        "match_groups": match_groups,
        "no_images": False,
    })


# ── Image serve ───────────────────────────────────────────────────────────────

_PDF_CACHE_TTL   = 3600   # seconds — how long to keep a raw PDF in Redis
_JPEG_CACHE_TTL  = 3600   # seconds — how long to keep a rendered JPEG in Redis


def image_serve(request, image_id):
    _require_staff(request)

    rim = get_object_or_404(ReportImage, pk=image_id)

    # Level 1: return the rendered JPEG straight from cache if available.
    jpeg_key = f"img_jpeg:{image_id}"
    jpeg_bytes = cache.get(jpeg_key)
    if jpeg_bytes is not None:
        return HttpResponse(jpeg_bytes, content_type="image/jpeg")

    # Level 2: get the raw PDF bytes from cache, or fetch and cache them.
    pdf_key = f"report_pdf:{rim.report_id}"
    pdf_bytes = cache.get(pdf_key)
    if pdf_bytes is None:
        token = getattr(settings, "INTERNAL_REPORT_TOKEN", "")
        headers = {"X-Internal-Token": token} if token else {}
        url = f"https://iqsconnect.org/reports/{rim.report_id}"
        try:
            resp = http_requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception:
            raise Http404("Could not fetch source PDF")
        pdf_bytes = resp.content
        cache.set(pdf_key, pdf_bytes, timeout=_PDF_CACHE_TTL)

    try:
        from pypdf import PdfReader
        from PIL import Image

        reader = PdfReader(io.BytesIO(pdf_bytes))
        page = reader.pages[rim.page_number - 1]
        img_obj = list(page.images)[rim.image_index]
        pil_img = Image.open(io.BytesIO(img_obj.data)).convert("RGB")

        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=85)
        jpeg_bytes = buf.getvalue()
        cache.set(jpeg_key, jpeg_bytes, timeout=_JPEG_CACHE_TTL)
        return HttpResponse(jpeg_bytes, content_type="image/jpeg")
    except Exception:
        raise Http404("Could not extract image from PDF")


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

    return render(request, "reports/image_match_detail.html", {
        "im": im,
        "team_a": team_a,
        "team_b": team_b,
        "back_report_id": back_report_id,
        "back_team": back_team,
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
    })


# ── AI Detection report ───────────────────────────────────────────────────────

def report_ai_detection(request, report_id):
    _require_staff(request)

    report = get_object_or_404(
        Report.objects.select_related("event_team__team", "event_team__event"),
        pk=report_id,
    )

    pages = (
        ReportPage.objects
        .filter(report=report)
        .prefetch_related("chunks", "ai_detection__sentences")
        .order_by("page_number")
    )

    page_data = []
    total_ai_words = 0
    total_text_words = 0
    analyzed_count = 0

    for page in pages:
        try:
            result = page.ai_detection
        except AIDetectionResult.DoesNotExist:
            result = None

        chunks = list(page.chunks.order_by("chunk_index"))

        flagged_sentence_texts = set()
        if result:
            analyzed_count += 1
            total_ai_words += result.ai_words
            total_text_words += result.text_words
            for s in result.sentences.all():
                if s.text:
                    flagged_sentence_texts.add(s.text)

        page_data.append({
            "page": page,
            "result": result,
            "chunks": chunks,
            "flagged_texts": flagged_sentence_texts,
        })

    avg_fake_pct = None
    if analyzed_count:
        total = sum(pd["result"].fake_percentage for pd in page_data if pd["result"])
        avg_fake_pct = round(total / analyzed_count, 1)

    return render(request, "reports/report_ai_detection.html", {
        "report": report,
        "report_type_label": REPORT_TYPE_LABELS.get(report.report_type, f"Type {report.report_type}"),
        "page_data": page_data,
        "analyzed_count": analyzed_count,
        "total_pages": len(page_data),
        "avg_fake_pct": avg_fake_pct,
        "total_ai_words": total_ai_words,
        "total_text_words": total_text_words,
    })
