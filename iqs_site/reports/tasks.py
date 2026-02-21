import io
import itertools
import logging
import os
import re

import pdfplumber
import requests
from celery import chord, group, shared_task
from django.conf import settings
from django.db.models import F
from django.utils import timezone

from events.models import Report
from .models import AnalysisJob, ChunkMatch, ImageMatch, PageMatch, ReportChunk, ReportImage, ReportPage

logger = logging.getLogger(__name__)

# ── Tuning constants ──────────────────────────────────────────────────────────
SHINGLE_SIZE_WORDS = 5
NUM_PERMUTATIONS = 128
PAGE_SIMILARITY_THRESHOLD = 0.05   # min Jaccard to record a PageMatch
CHUNK_SIMILARITY_THRESHOLD = 0.30  # min word-set Jaccard to record a ChunkMatch
PARAGRAPH_GAP_PTS = 10             # vertical gap (pts) that starts a new chunk
OCR_DPI = 200                      # DPI for rendering pages before OCR
MIN_IMAGE_SIZE = 50                # px — skip icons/decorations smaller than this
MIN_COLOR_STDDEV = 8               # per-channel stddev threshold; below this = uniform/blank image
IMAGE_HAMMING_THRESHOLD = 10       # max pHash Hamming distance to record as a match
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


def _ocr_page(pdf_bytes: bytes, page_num: int) -> list[dict]:
    """
    Render a single PDF page as an image and OCR it with Tesseract.
    Returns chunk_dicts in the same format as _extract_pages.
    page_num is 1-indexed. Returns [] if OCR libraries are unavailable.
    """
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:
        logger.warning("OCR libraries not installed (pdf2image, pytesseract); skipping OCR for page %d", page_num)
        return []

    scale = 72.0 / OCR_DPI  # pixels → PDF points

    images = convert_from_bytes(pdf_bytes, dpi=OCR_DPI, first_page=page_num, last_page=page_num)
    if not images:
        return []

    data = pytesseract.image_to_data(images[0], output_type=pytesseract.Output.DICT)

    # Group words by (block_num, par_num) → paragraph-level chunks.
    blocks: dict = {}
    for i, text in enumerate(data["text"]):
        if not text.strip() or int(data["conf"][i]) < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i])
        blocks.setdefault(key, []).append({
            "text": text,
            "left":   data["left"][i],
            "top":    data["top"][i],
            "right":  data["left"][i] + data["width"][i],
            "bottom": data["top"][i]  + data["height"][i],
        })

    chunk_dicts = []
    for idx, (_, words) in enumerate(sorted(blocks.items())):
        text = " ".join(w["text"] for w in words)
        if not text.strip():
            continue
        chunk_dicts.append({
            "chunk_index": idx,
            "text": text,
            "bbox_x0": min(w["left"]   for w in words) * scale,
            "bbox_y0": min(w["top"]    for w in words) * scale,
            "bbox_x1": max(w["right"]  for w in words) * scale,
            "bbox_y1": max(w["bottom"] for w in words) * scale,
        })

    return chunk_dicts


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
                logger.debug("Report page %d has no extractable text; attempting OCR", page_num)
                chunk_dicts = _ocr_page(pdf_bytes, page_num)
                if chunk_dicts:
                    pages.append({"page_number": page_num, "chunks": chunk_dicts})
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


# ── Image extraction ──────────────────────────────────────────────────────────

def _extract_images(pdf_bytes: bytes) -> list[dict]:
    """
    Extract images from all pages of a PDF using pypdf + imagehash.
    Returns a list of dicts:
      {
        "page_number": int,   # 1-indexed
        "image_index": int,   # ordering within the page
        "phash": str,         # 16-char hex pHash
        "width": int,
        "height": int,
      }
    Images smaller than MIN_IMAGE_SIZE in either dimension are skipped.
    Un-decodable images are silently skipped.
    """
    try:
        import imagehash
        from PIL import Image, ImageStat
        from pypdf import PdfReader
    except ImportError:
        logger.warning("Image extraction libraries not available (pypdf, Pillow, imagehash); skipping")
        return []

    results = []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        logger.warning("Could not open PDF for image extraction", exc_info=True)
        return []

    for page_num, page in enumerate(reader.pages, start=1):
        try:
            page_images = list(page.images)
        except Exception:
            logger.debug("Could not list images on page %d", page_num, exc_info=True)
            continue

        for img_idx, img_obj in enumerate(page_images):
            try:
                pil_img = Image.open(io.BytesIO(img_obj.data))
                if pil_img.width < MIN_IMAGE_SIZE or pil_img.height < MIN_IMAGE_SIZE:
                    continue
                # Convert to RGB so pHash works regardless of source mode (CMYK, P, etc.)
                pil_img = pil_img.convert("RGB")
                # Skip images with very low color variation (solid fills, black boxes, etc.)
                stat = ImageStat.Stat(pil_img)
                if max(stat.stddev) < MIN_COLOR_STDDEV:
                    logger.debug(
                        "Skipping low-variation image %d on page %d (max stddev=%.1f)",
                        img_idx, page_num, max(stat.stddev),
                    )
                    continue
                ph = str(imagehash.phash(pil_img))
                results.append({
                    "page_number": page_num,
                    "image_index": img_idx,
                    "phash": ph,
                    "width": pil_img.width,
                    "height": pil_img.height,
                })
            except Exception:
                logger.debug("Skipping undecodable image %d on page %d", img_idx, page_num, exc_info=True)
                continue

    return results


# ── Per-report extraction helper ──────────────────────────────────────────────

def _process_single_report(report, pdf_bytes) -> tuple[int, int]:
    """
    Extract and persist pages/chunks/images for one already-downloaded report.

    Deletes any stale ReportPage / ReportImage rows for this report, then
    writes fresh data.  Extraction errors are logged and cause (0, 0) to be
    returned so callers can skip adding the report to processed_report_ids.

    Returns (n_pages, n_images).
    """
    try:
        page_data = _extract_pages(pdf_bytes)
    except Exception:
        logger.warning("Failed to extract pages from report %s", report.report_id, exc_info=True)
        return 0, 0

    if not page_data:
        logger.warning("Report %s produced no pages", report.report_id)
        return 0, 0

    try:
        image_data = _extract_images(pdf_bytes)
    except Exception:
        logger.warning("Failed to extract images from report %s", report.report_id, exc_info=True)
        image_data = []

    # Atomically replace stale extraction data.
    ReportPage.objects.filter(report=report).delete()   # cascades to ReportChunk
    ReportImage.objects.filter(report=report).delete()

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

    if image_data:
        ReportImage.objects.bulk_create([
            ReportImage(
                report=report,
                page_number=img["page_number"],
                image_index=img["image_index"],
                phash=img["phash"],
                width=img["width"],
                height=img["height"],
            )
            for img in image_data
        ])

    logger.info(
        "Report %s: extracted %d pages, %d images",
        report.report_id, len(page_data), len(image_data),
    )
    return len(page_data), len(image_data)


# ── Celery task ───────────────────────────────────────────────────────────────

@shared_task
def extract_single_report(job_id: int, report_id: int) -> None:
    """
    Download and extract one report PDF.  Designed to run inside a Celery
    chord group so multiple workers process reports in parallel.

    Always returns without raising so the chord callback fires even when a
    single report fails.  Updates the parent AnalysisJob counters atomically
    via F() so concurrent workers don't clobber each other.
    """
    n_pages = n_images = 0
    try:
        report = Report.objects.get(pk=report_id)

        ext = os.path.splitext(report.report_link)[1].lower()
        if ext != ".pdf":
            logger.info("Skipping report %s (extension %r)", report_id, ext)
        else:
            token = getattr(settings, "INTERNAL_REPORT_TOKEN", "")
            headers = {"X-Internal-Token": token} if token else {}
            url = f"{PUBLIC_BASE_URL}/reports/{report_id}"
            resp = requests.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            n_pages, n_images = _process_single_report(report, resp.content)
    except Exception:
        logger.warning("extract_single_report failed for report %s", report_id, exc_info=True)

    AnalysisJob.objects.filter(pk=job_id).update(
        reports_processed=F("reports_processed") + 1,
        pages_processed=F("pages_processed") + n_pages,
        images_processed=F("images_processed") + n_images,
    )


@shared_task
def finalize_extraction(job_id: int) -> None:
    """Chord callback: mark the extraction job as SUCCEEDED."""
    AnalysisJob.objects.filter(pk=job_id).update(
        status=AnalysisJob.Statuses.SUCCEEDED,
        completed_at=timezone.now(),
    )
    logger.info("Extraction job %s completed", job_id)


@shared_task
def run_extraction(job_id: int) -> None:
    """
    Coordinator task for extraction-only jobs.

    Marks the job RUNNING, discovers reports, then dispatches one
    extract_single_report sub-task per report using a Celery chord.
    finalize_extraction fires as the chord callback once all sub-tasks finish.

    Requires a Redis (or other) result backend so Celery can track the chord.
    """
    job = AnalysisJob.objects.get(pk=job_id)
    job.status = AnalysisJob.Statuses.RUNNING
    job.started_at = timezone.now()
    job.error_message = None
    job.save(update_fields=["status", "started_at", "error_message"])

    try:
        qs = Report.objects.all()
        if job.report_type is not None:
            qs = qs.filter(report_type=job.report_type)

        report_ids = [
            r.report_id for r in qs
            if os.path.splitext(r.report_link)[1].lower() == ".pdf"
        ]

        job.reports_found = len(report_ids)
        job.save(update_fields=["reports_found"])
        logger.info("Extraction job %s: found %d reports", job_id, len(report_ids))

        if not report_ids:
            job.status = AnalysisJob.Statuses.SUCCEEDED
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "completed_at"])
            return

        chord(
            group(extract_single_report.s(job_id, rid) for rid in report_ids),
            finalize_extraction.si(job_id),
        ).delay()

    except Exception as exc:
        logger.exception("run_extraction %s failed during setup", job_id)
        job.status = AnalysisJob.Statuses.FAILED
        job.completed_at = timezone.now()
        job.error_message = str(exc)[:4000]
        job.save(update_fields=["status", "completed_at", "error_message"])
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def run_plagiarism_analysis(self, job_id: int) -> dict:
    """
    Full plagiarism analysis across all report PDFs.

    Phase 1: Download each PDF and extract ReportPage + ReportChunk + ReportImage records.
    Phase 2: MinHash page-level comparison → PageMatch records.
    Phase 3: Word-set Jaccard chunk comparison within each PageMatch → ChunkMatch records.
    Phase 4: pHash image comparison → ImageMatch records.
    """
    job = AnalysisJob.objects.get(pk=job_id)
    job.status = AnalysisJob.Statuses.RUNNING
    job.started_at = timezone.now()
    job.error_message = None
    job.save(update_fields=["status", "started_at", "error_message"])

    token = getattr(settings, "INTERNAL_REPORT_TOKEN", "")
    headers = {"X-Internal-Token": token} if token else {}

    try:
        # ── Phase 1: extract pages, chunks, and images ───────────────────────
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

            n_pages, n_images = _process_single_report(report, resp.content)
            if n_pages == 0:
                continue

            processed_report_ids.append(report.report_id)
            job.reports_processed += 1
            job.pages_processed += n_pages
            job.images_processed += n_images
            job.save(update_fields=["reports_processed", "pages_processed", "images_processed"])

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

        # ── Phase 4: pHash image comparison ───────────────────────────────────
        all_images = list(
            ReportImage.objects.filter(report_id__in=processed_report_ids)
        )
        logger.info("AnalysisJob %s: comparing %d images", job_id, len(all_images))

        # Clear old image match data for processed reports.
        ImageMatch.objects.filter(
            image_a__report_id__in=processed_report_ids
        ).delete()

        try:
            import imagehash
            new_image_matches = []
            for img_a, img_b in itertools.combinations(all_images, 2):
                if img_a.report_id == img_b.report_id:
                    continue
                distance = imagehash.hex_to_hash(img_a.phash) - imagehash.hex_to_hash(img_b.phash)
                if distance <= IMAGE_HAMMING_THRESHOLD:
                    a, b = (img_a, img_b) if img_a.image_id < img_b.image_id else (img_b, img_a)
                    new_image_matches.append(ImageMatch(image_a=a, image_b=b, hamming_distance=distance))
            ImageMatch.objects.bulk_create(new_image_matches, ignore_conflicts=True)
            logger.info("AnalysisJob %s: created %d ImageMatch records", job_id, len(new_image_matches))
        except ImportError:
            logger.warning("imagehash not available; skipping image comparison")
            new_image_matches = []

        job.status = AnalysisJob.Statuses.SUCCEEDED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])

        return {
            "job_id": job_id,
            "status": job.status,
            "reports_processed": job.reports_processed,
            "pages_processed": job.pages_processed,
            "images_processed": job.images_processed,
            "page_matches": len(new_page_matches),
            "chunk_matches": created_chunk_matches,
            "image_matches": len(new_image_matches),
        }

    except Exception as exc:
        logger.exception("AnalysisJob %s failed", job_id)
        job.status = AnalysisJob.Statuses.FAILED
        job.completed_at = timezone.now()
        job.error_message = str(exc)[:4000]
        job.save(update_fields=["status", "completed_at", "error_message"])
        raise
