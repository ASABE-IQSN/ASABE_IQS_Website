import io
import itertools
import logging
import os
import re

import pdfplumber
import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from events.models import Report
from .models import AnalysisJob, ChunkMatch, PageMatch, ReportChunk, ReportPage

logger = logging.getLogger(__name__)

# ── Tuning constants ──────────────────────────────────────────────────────────
SHINGLE_SIZE_WORDS = 5
NUM_PERMUTATIONS = 128
PAGE_SIMILARITY_THRESHOLD = 0.15   # min Jaccard to record a PageMatch
CHUNK_SIMILARITY_THRESHOLD = 0.30  # min word-set Jaccard to record a ChunkMatch
PARAGRAPH_GAP_PTS = 10             # vertical gap (pts) that starts a new chunk
PUBLIC_BASE_URL = "https://iqsconnect.org"
# ─────────────────────────────────────────────────────────────────────────────


# ── Text helpers ──────────────────────────────────────────────────────────────

def _normalize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return re.findall(r"[a-z0-9']+", text)


def _shingles(words: list[str], k: int) -> list[str]:
    if len(words) < k:
        return []
    return [" ".join(words[i : i + k]) for i in range(len(words) - k + 1)]


def _minhash(shs: list[str]):
    from datasketch import MinHash
    m = MinHash(num_perm=NUM_PERMUTATIONS)
    for s in shs:
        m.update(s.encode("utf-8"))
    return m


def _word_set_jaccard(text_a: str, text_b: str) -> float:
    """Simple word-set Jaccard — fast and sufficient for small chunks."""
    words_a = set(_normalize(text_a))
    words_b = set(_normalize(text_b))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _extract_pages(pdf_bytes: bytes) -> list[dict]:
    """
    Open a PDF from raw bytes with pdfplumber.
    Returns a list of page dicts:
      {
        "page_number": int,           # 1-indexed
        "chunks": [
          {
            "chunk_index": int,
            "text": str,
            "bbox_x0": float, "bbox_y0": float,
            "bbox_x1": float, "bbox_y1": float,
          },
          ...
        ]
      }
    """
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=True)
            if not words:
                continue

            # Group words into paragraph-level chunks by vertical gap.
            chunks_raw = []
            current_group: list[dict] = []
            prev_top = None
            for word in words:
                top = word.get("top", 0)
                if prev_top is not None and (top - prev_top) > PARAGRAPH_GAP_PTS:
                    if current_group:
                        chunks_raw.append(current_group)
                        current_group = []
                current_group.append(word)
                prev_top = top
            if current_group:
                chunks_raw.append(current_group)

            chunk_dicts = []
            for idx, group in enumerate(chunks_raw):
                text = " ".join(w["text"] for w in group)
                if not text.strip():
                    continue
                x0 = min(w["x0"] for w in group)
                y0 = min(w["top"] for w in group)
                x1 = max(w["x1"] for w in group)
                y1 = max(w["bottom"] for w in group)
                chunk_dicts.append({
                    "chunk_index": idx,
                    "text": text,
                    "bbox_x0": x0,
                    "bbox_y0": y0,
                    "bbox_x1": x1,
                    "bbox_y1": y1,
                })

            if chunk_dicts:
                pages.append({"page_number": page_num, "chunks": chunk_dicts})

    return pages


# ── Celery task ───────────────────────────────────────────────────────────────

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def run_plagiarism_analysis(self, job_id: int) -> dict:
    """
    Full plagiarism analysis across all report PDFs.

    Phase 1: Download each PDF and extract ReportPage + ReportChunk records.
    Phase 2: MinHash page-level comparison → PageMatch records.
    Phase 3: Word-set Jaccard chunk comparison within each PageMatch → ChunkMatch records.
    """
    job = AnalysisJob.objects.get(pk=job_id)
    job.status = AnalysisJob.Statuses.RUNNING
    job.started_at = timezone.now()
    job.error_message = None
    job.save(update_fields=["status", "started_at", "error_message"])

    token = getattr(settings, "INTERNAL_REPORT_TOKEN", "")
    headers = {"X-Internal-Token": token} if token else {}

    try:
        # ── Phase 1: extract pages and chunks ────────────────────────────────
        qs = Report.objects.all()
        if job.report_type is not None:
            qs = qs.filter(report_type=job.report_type)
        reports = list(qs)

        job.reports_found = len(reports)
        job.save(update_fields=["reports_found"])
        logger.info("AnalysisJob %s: found %d reports", job_id, len(reports))

        processed_report_ids = []

        for report in reports:
            ext = os.path.splitext(report.report_link)[1].lower()
            if ext != ".pdf":
                logger.info("Skipping report %s (extension %r)", report.report_id, ext)
                continue

            url = f"{PUBLIC_BASE_URL}/reports/{report.report_id}"
            try:
                resp = requests.get(url, headers=headers, timeout=60)
                resp.raise_for_status()
            except Exception:
                logger.warning("Failed to download report %s from %s", report.report_id, url, exc_info=True)
                continue

            try:
                page_data = _extract_pages(resp.content)
            except Exception:
                logger.warning("Failed to extract pages from report %s", report.report_id, exc_info=True)
                continue

            if not page_data:
                logger.warning("Report %s produced no pages", report.report_id)
                continue

            # Clear stale extraction for this report so re-runs are fresh.
            ReportPage.objects.filter(report=report).delete()

            for pdata in page_data:
                rpage = ReportPage.objects.create(
                    report=report,
                    page_number=pdata["page_number"],
                )
                ReportChunk.objects.bulk_create([
                    ReportChunk(
                        page=rpage,
                        chunk_index=c["chunk_index"],
                        text=c["text"],
                        bbox_x0=c["bbox_x0"],
                        bbox_y0=c["bbox_y0"],
                        bbox_x1=c["bbox_x1"],
                        bbox_y1=c["bbox_y1"],
                    )
                    for c in pdata["chunks"]
                ])

            processed_report_ids.append(report.report_id)
            job.reports_processed += 1
            job.pages_processed += len(page_data)
            job.save(update_fields=["reports_processed", "pages_processed"])
            logger.info("Report %s: extracted %d pages", report.report_id, len(page_data))

        # ── Phase 2: page-level MinHash comparison ────────────────────────────
        # Load all pages for the processed reports.
        all_pages = list(
            ReportPage.objects
            .filter(report_id__in=processed_report_ids)
            .prefetch_related("chunks")
        )
        logger.info("AnalysisJob %s: comparing %d pages", job_id, len(all_pages))

        # Build (page, minhash) list. Pages with no text are skipped.
        page_hashes = []
        for rpage in all_pages:
            full_text = " ".join(c.text for c in rpage.chunks.all())
            words = _normalize(full_text)
            shs = _shingles(words, SHINGLE_SIZE_WORDS)
            if shs:
                page_hashes.append((rpage, _minhash(shs)))

        # Clear old match data before writing new results.
        PageMatch.objects.filter(
            page_a__report_id__in=processed_report_ids
        ).delete()

        new_page_matches = []
        for (pa, mh_a), (pb, mh_b) in itertools.combinations(page_hashes, 2):
            # Only compare pages from different reports.
            if pa.report_id == pb.report_id:
                continue
            sim = mh_a.jaccard(mh_b)
            if sim >= PAGE_SIMILARITY_THRESHOLD:
                # Enforce page_a_id < page_b_id to avoid duplicate pairs.
                a, b = (pa, pb) if pa.page_id < pb.page_id else (pb, pa)
                new_page_matches.append(PageMatch(page_a=a, page_b=b, similarity=sim))

        PageMatch.objects.bulk_create(new_page_matches, ignore_conflicts=True)
        logger.info("AnalysisJob %s: created %d PageMatch records", job_id, len(new_page_matches))

        # ── Phase 3: chunk-level matching ──────────────────────────────────────
        created_chunk_matches = 0
        for pm in PageMatch.objects.filter(page_a__report_id__in=processed_report_ids).prefetch_related(
            "page_a__chunks", "page_b__chunks"
        ):
            chunks_a = list(pm.page_a.chunks.all())
            chunks_b = list(pm.page_b.chunks.all())
            batch = []
            for ca, cb in itertools.product(chunks_a, chunks_b):
                sim = _word_set_jaccard(ca.text, cb.text)
                if sim >= CHUNK_SIMILARITY_THRESHOLD:
                    batch.append(ChunkMatch(
                        page_match=pm,
                        chunk_a=ca,
                        chunk_b=cb,
                        similarity=sim,
                    ))
            if batch:
                ChunkMatch.objects.bulk_create(batch)
                created_chunk_matches += len(batch)

        logger.info("AnalysisJob %s: created %d ChunkMatch records", job_id, created_chunk_matches)

        job.status = AnalysisJob.Statuses.SUCCEEDED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])

        return {
            "job_id": job_id,
            "status": job.status,
            "reports_processed": job.reports_processed,
            "pages_processed": job.pages_processed,
            "page_matches": len(new_page_matches),
            "chunk_matches": created_chunk_matches,
        }

    except Exception as exc:
        logger.exception("AnalysisJob %s failed", job_id)
        job.status = AnalysisJob.Statuses.FAILED
        job.completed_at = timezone.now()
        job.error_message = str(exc)[:4000]
        job.save(update_fields=["status", "completed_at", "error_message"])
        raise
