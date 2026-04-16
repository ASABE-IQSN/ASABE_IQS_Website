import bisect
import io
import itertools
import logging
import os
import re
import time

import pdfplumber
import requests
from celery import chord, group, shared_task
from django.conf import settings
from django.db.models import F
from django.utils import timezone

from events.models import Report
from iqs_site.storage import ReportStorage
from .models import (
    AIDetectedSentence, AIDetectionResult,
    AnalysisJob, ChunkMatch, ImageMatch, PageMatch,
    ReportChunk, ReportImage, ReportPage,
)

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
IMAGE_COMPARE_CHUNK_SIZE = 500     # image IDs per parallel comparison sub-task
IMAGE_LOG_INTERVAL = 500_000       # log a progress line every N pair comparisons
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
            try:
                words = page.extract_words(use_text_flow=True)
            except Exception:
                logger.warning(
                    "extract_words failed on page %d (likely malformed font); falling back to OCR",
                    page_num, exc_info=True,
                )
                chunk_dicts = _ocr_page(pdf_bytes, page_num)
                if chunk_dicts:
                    pages.append({"page_number": page_num, "chunks": chunk_dicts})
                continue
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
                if prev_top is not None and abs(top - prev_top) > PARAGRAPH_GAP_PTS:
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
    seen_phashes: set[str] = set()
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
                # Skip exact duplicates (e.g. logos repeated on every page)
                if ph in seen_phashes:
                    logger.debug(
                        "Skipping duplicate image %d on page %d (phash=%s)",
                        img_idx, page_num, ph,
                    )
                    continue
                seen_phashes.add(ph)
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
            storage = ReportStorage()
            with storage.open(report.report_link, "rb") as f:
                pdf_bytes = f.read()
            n_pages, n_images = _process_single_report(report, pdf_bytes)
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


@shared_task
def compare_images_chunk(
    job_id: int,
    chunk_idx: int,
    total_chunks: int,
    image_a_ids: list,
    report_type,
) -> None:
    """
    Compare one partition of images (image_a_ids) against every image with a
    higher image_id, recording matches below IMAGE_HAMMING_THRESHOLD.

    Designed to run inside a Celery chord group so workers operate in parallel.
    Always returns without raising — chord callback fires even on individual errors.
    Uses bisect to skip lower-id candidates without iterating the whole list.
    """
    try:
        import imagehash
    except ImportError:
        logger.warning("imagehash not available; skipping image chunk %d", chunk_idx)
        AnalysisJob.objects.filter(pk=job_id).update(
            reports_processed=F("reports_processed") + 1,
        )
        return

    # Load all relevant images once; each worker performs this cheap query.
    image_qs = (
        ReportImage.objects
        .order_by("image_id")
        .values("image_id", "report_id", "phash")
    )
    if report_type is not None:
        image_qs = image_qs.filter(report__report_type=report_type)

    all_images = list(image_qs)
    if not all_images:
        AnalysisJob.objects.filter(pk=job_id).update(
            reports_processed=F("reports_processed") + 1,
        )
        return

    # Pre-compute hash objects and build lookup maps (done once per worker).
    sorted_ids   = [img["image_id"] for img in all_images]   # already sorted
    hash_cache   = {img["image_id"]: imagehash.hex_to_hash(img["phash"]) for img in all_images}
    report_cache = {img["image_id"]: img["report_id"] for img in all_images}

    image_a_id_set = set(image_a_ids)
    new_matches    = []
    pair_count     = 0

    for a_id in image_a_ids:
        if a_id not in hash_cache:
            continue  # image was deleted between coordinator and worker

        hash_a    = hash_cache[a_id]
        report_a  = report_cache[a_id]

        # bisect past a_id so we only visit b_id > a_id, avoiding duplicate pairs.
        start = bisect.bisect_right(sorted_ids, a_id)

        for b_id in sorted_ids[start:]:
            if report_cache[b_id] == report_a:
                continue  # same report — never a match

            distance = hash_a - hash_cache[b_id]
            pair_count += 1

            if pair_count % IMAGE_LOG_INTERVAL == 0:
                logger.info(
                    "Image chunk %d/%d (job %s): %d pairs checked, %d matches so far",
                    chunk_idx + 1, total_chunks, job_id, pair_count, len(new_matches),
                )

            if distance <= IMAGE_HAMMING_THRESHOLD:
                new_matches.append(ImageMatch(
                    image_a_id=a_id,
                    image_b_id=b_id,
                    hamming_distance=distance,
                ))

    if new_matches:
        ImageMatch.objects.bulk_create(new_matches, ignore_conflicts=True)

    logger.info(
        "Image chunk %d/%d (job %s): done — %d pairs checked, %d matches found",
        chunk_idx + 1, total_chunks, job_id, pair_count, len(new_matches),
    )

    AnalysisJob.objects.filter(pk=job_id).update(
        reports_processed=F("reports_processed") + 1,
        images_processed=F("images_processed") + len(new_matches),
    )


@shared_task
def finalize_similarity(job_id: int) -> None:
    """Chord callback: mark the similarity analysis job as SUCCEEDED."""
    AnalysisJob.objects.filter(pk=job_id).update(
        status=AnalysisJob.Statuses.SUCCEEDED,
        completed_at=timezone.now(),
    )
    logger.info("Similarity job %s completed", job_id)


@shared_task
def run_similarity_analysis(job_id: int) -> None:
    """
    Coordinator for similarity-only jobs.

    Reads existing extracted data from the DB — run an extraction job first.

    Phase 2: MinHash page-level comparison → PageMatch + ChunkMatch (sequential).
    Phase 4: pHash image comparison → ImageMatch (parallel chord, one task per
             IMAGE_COMPARE_CHUNK_SIZE images).

    Counter semantics for this job type:
      pages_processed  — pages fed into MinHash
      reports_found    — total image comparison chunks
      reports_processed — chunks completed (updated atomically by each worker)
      images_processed — total ImageMatch records created
    """
    job = AnalysisJob.objects.get(pk=job_id)
    job.status = AnalysisJob.Statuses.RUNNING
    job.started_at = timezone.now()
    job.error_message = None
    job.save(update_fields=["status", "started_at", "error_message"])

    try:
        rt_filter = {"report__report_type": job.report_type} if job.report_type is not None else {}

        # ── Phase 2: MinHash page comparison ─────────────────────────────────
        all_pages = list(
            ReportPage.objects
            .filter(**rt_filter)
            .prefetch_related("chunks")
            .order_by("page_id")
        )
        logger.info("Similarity job %s: %d pages to compare via MinHash", job_id, len(all_pages))

        page_hashes = []
        for rpage in all_pages:
            full_text = " ".join(c.text for c in rpage.chunks.all())
            words = _normalize(full_text)
            shs = _shingles(words, SHINGLE_SIZE_WORDS)
            if shs:
                page_hashes.append((rpage, _minhash(shs)))

        # Clear stale PageMatch (and cascaded ChunkMatch) for this scope.
        if job.report_type is not None:
            PageMatch.objects.filter(page_a__report__report_type=job.report_type).delete()
        else:
            PageMatch.objects.all().delete()

        new_page_matches = []
        pairs_checked = 0
        for (pa, mh_a), (pb, mh_b) in itertools.combinations(page_hashes, 2):
            if pa.report_id == pb.report_id:
                continue
            pairs_checked += 1
            if pairs_checked % 1_000_000 == 0:
                logger.info(
                    "Similarity job %s: %d page pairs compared, %d matches so far",
                    job_id, pairs_checked, len(new_page_matches),
                )
            sim = mh_a.jaccard(mh_b)
            if sim >= PAGE_SIMILARITY_THRESHOLD:
                a, b = (pa, pb) if pa.page_id < pb.page_id else (pb, pa)
                new_page_matches.append(PageMatch(page_a=a, page_b=b, similarity=sim))

        PageMatch.objects.bulk_create(new_page_matches, ignore_conflicts=True)
        logger.info(
            "Similarity job %s: %d page pairs checked, %d PageMatch records created",
            job_id, pairs_checked, len(new_page_matches),
        )

        # ── Phase 3: chunk-level matching ─────────────────────────────────────
        page_ids = [p.page_id for p, _ in page_hashes]
        created_chunk_matches = 0
        for pm in PageMatch.objects.filter(page_a_id__in=page_ids).prefetch_related(
            "page_a__chunks", "page_b__chunks"
        ):
            batch = [
                ChunkMatch(page_match=pm, chunk_a=ca, chunk_b=cb, similarity=sim)
                for ca in pm.page_a.chunks.all()
                for cb in pm.page_b.chunks.all()
                if (sim := _word_set_jaccard(ca.text, cb.text)) >= CHUNK_SIMILARITY_THRESHOLD
            ]
            if batch:
                ChunkMatch.objects.bulk_create(batch)
                created_chunk_matches += len(batch)

        logger.info(
            "Similarity job %s: %d ChunkMatch records created",
            job_id, created_chunk_matches,
        )

        job.pages_processed = len(page_hashes)
        job.save(update_fields=["pages_processed"])

        # ── Phase 4: parallel image comparison ───────────────────────────────
        all_image_ids = list(
            ReportImage.objects
            .filter(**rt_filter)
            .order_by("image_id")
            .values_list("image_id", flat=True)
        )
        logger.info("Similarity job %s: %d images — building comparison chunks", job_id, len(all_image_ids))

        # Clear stale ImageMatch for this scope.
        if job.report_type is not None:
            ImageMatch.objects.filter(image_a__report__report_type=job.report_type).delete()
        else:
            ImageMatch.objects.all().delete()

        if not all_image_ids:
            job.status = AnalysisJob.Statuses.SUCCEEDED
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "completed_at"])
            return

        chunks = [
            all_image_ids[i: i + IMAGE_COMPARE_CHUNK_SIZE]
            for i in range(0, len(all_image_ids), IMAGE_COMPARE_CHUNK_SIZE)
        ]
        total_chunks = len(chunks)

        # Use reports_found / reports_processed to track chunk progress on the dashboard.
        job.reports_found = total_chunks
        job.reports_processed = 0
        job.save(update_fields=["reports_found", "reports_processed"])

        logger.info(
            "Similarity job %s: spawning %d image comparison chunks (chunk_size=%d)",
            job_id, total_chunks, IMAGE_COMPARE_CHUNK_SIZE,
        )

        chord(
            group(
                compare_images_chunk.s(job_id, idx, total_chunks, chunk_ids, job.report_type)
                for idx, chunk_ids in enumerate(chunks)
            ),
            finalize_similarity.si(job_id),
        ).delay()

    except Exception as exc:
        logger.exception("run_similarity_analysis %s failed", job_id)
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

    storage = ReportStorage()

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

            try:
                with storage.open(report.report_link, "rb") as f:
                    pdf_bytes = f.read()
            except Exception:
                logger.warning("Failed to read report %s from storage", report.report_id, exc_info=True)
                continue

            n_pages, n_images = _process_single_report(report, pdf_bytes)
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


# ── AI Detection ──────────────────────────────────────────────────────────────

ZEROGPT_API_URL = "https://api.zerogpt.com/api/detect/detectText"
ZEROGPT_INTER_REQUEST_DELAY = 0.5  # seconds between API calls


def _zerogpt_process_page(page, api_key: str) -> bool:
    """
    Send one ReportPage to ZeroGPT and persist the result.

    Returns True if the page was submitted and a result saved, False if
    skipped (no text).  Raises on API errors so callers can decide whether
    to continue or abort.
    """
    chunks = list(page.chunks.order_by("chunk_index"))
    text = "\n\n".join(c.text for c in chunks).strip()
    if not text:
        return False

    headers = {"ApiKey": api_key, "Content-Type": "application/json"}
    resp = requests.post(
        ZEROGPT_API_URL,
        headers=headers,
        json={"input_text": text},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})

    def _float(val, default=0.0):
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _int(val, default=0):
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    result, _ = AIDetectionResult.objects.update_or_create(
        page=page,
        defaults={
            "fake_percentage": _float(data.get("fakePercentage")),
            "ai_words": _int(data.get("aiWords")),
            "text_words": _int(data.get("textWords")),
            "h_score": None,
            "collection_id": str(data.get("collection_id") or ""),
            "zerogpt_id": str(data.get("id") or ""),
            "feedback": str(data.get("feedback") or ""),
        },
    )

    result.sentences.all().delete()
    raw_sentences = list(data.get("h") or []) + list(data.get("hi") or [])
    if raw_sentences:
        sentence_objs = []
        for idx, item in enumerate(raw_sentences):
            if isinstance(item, dict):
                sentence_text = str(item.get("sentence") or item.get("text") or "")
                prob = _float(item.get("generated_probability") or item.get("probability"), default=None)
                prob = prob if prob is not None else None
            else:
                sentence_text = str(item)
                prob = None
            if sentence_text:
                sentence_objs.append(AIDetectedSentence(
                    result=result,
                    sentence_index=idx,
                    text=sentence_text,
                    generated_probability=prob,
                ))
        if sentence_objs:
            AIDetectedSentence.objects.bulk_create(sentence_objs)

    return True


@shared_task
def run_ai_detection_report(report_id: int):
    """Run ZeroGPT AI detection for every page of a single report."""
    from events.models import Report as ReportModel
    api_key = getattr(settings, "ZEROGPT_API_KEY", "")
    if not api_key:
        raise ValueError("ZEROGPT_API_KEY is not configured in settings.")

    try:
        report = ReportModel.objects.get(pk=report_id)
    except ReportModel.DoesNotExist:
        logger.error("run_ai_detection_report: report %s not found", report_id)
        return

    pages = list(
        ReportPage.objects
        .filter(report=report)
        .prefetch_related("chunks")
        .order_by("page_number")
    )

    logger.info("AI detection (single report %s): %d pages", report_id, len(pages))
    processed = 0
    for page in pages:
        try:
            submitted = _zerogpt_process_page(page, api_key)
            if submitted:
                processed += 1
        except Exception as exc:
            logger.warning(
                "AI detection (single report %s): API error on page %s: %s",
                report_id, page.page_id, exc,
            )
        time.sleep(ZEROGPT_INTER_REQUEST_DELAY)

    logger.info("AI detection (single report %s): done, %d pages processed", report_id, processed)


@shared_task
def run_ai_detection(job_id: int):
    """Call ZeroGPT for each ReportPage in the job's event and store results."""
    job = AnalysisJob.objects.get(pk=job_id)
    job.status = AnalysisJob.Statuses.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    try:
        api_key = getattr(settings, "ZEROGPT_API_KEY", "")
        if not api_key:
            raise ValueError("ZEROGPT_API_KEY is not configured in settings.")

        if not job.event_id:
            raise ValueError("AI detection job requires an event_id.")

        # Build page queryset filtered by event (and optionally report_type).
        pages_qs = (
            ReportPage.objects
            .filter(report__event_team__event_id=job.event_id)
            .prefetch_related("chunks")
            .select_related("report")
            .order_by("report_id", "page_number")
        )
        if job.report_type is not None:
            pages_qs = pages_qs.filter(report__report_type=job.report_type)

        pages = list(pages_qs)

        distinct_reports = len({p.report_id for p in pages})
        job.reports_found = distinct_reports
        job.save(update_fields=["reports_found"])

        logger.info(
            "AI detection job %s: %d pages across %d reports (event %s, report_type %s)",
            job_id, len(pages), distinct_reports, job.event_id, job.report_type,
        )

        for page in pages:
            try:
                submitted = _zerogpt_process_page(page, api_key)
                if submitted:
                    job.pages_processed += 1
                    if job.pages_processed % 10 == 0:
                        job.save(update_fields=["pages_processed"])
            except Exception as exc:
                logger.warning(
                    "AI detection job %s: API error on page %s: %s", job_id, page.page_id, exc
                )
            time.sleep(ZEROGPT_INTER_REQUEST_DELAY)

        job.pages_processed = job.pages_processed  # ensure final count saved
        job.status = AnalysisJob.Statuses.SUCCEEDED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "pages_processed"])

        logger.info("AI detection job %s succeeded (%d pages processed)", job_id, job.pages_processed)

    except Exception as exc:
        logger.exception("AI detection job %s failed", job_id)
        job.status = AnalysisJob.Statuses.FAILED
        job.completed_at = timezone.now()
        job.error_message = str(exc)[:4000]
        job.save(update_fields=["status", "completed_at", "error_message"])
        raise


# ── Bulk PDF export ──────────────────────────────────────────────────────────

@shared_task
def run_bulk_pdf_export(job_id: int) -> None:
    """Generate plagiarism PDF for every report in scope, bundle into a ZIP,
    and upload to S3.  Updates AnalysisJob progress as it goes."""
    import zipfile
    from django.core.files.base import ContentFile
    from reports.views import _generate_plagiarism_pdf

    job = AnalysisJob.objects.get(pk=job_id)
    job.status = AnalysisJob.Statuses.RUNNING
    job.started_at = timezone.now()
    job.error_message = None
    job.save(update_fields=["status", "started_at", "error_message"])

    storage = ReportStorage()

    try:
        qs = Report.objects.select_related("event_team__team", "event_team__event")
        if job.event_id:
            qs = qs.filter(event_team__event_id=job.event_id)
        if job.report_type is not None:
            qs = qs.filter(report_type=job.report_type)

        # Only include reports that have been extracted (have pages).
        report_ids_with_pages = set(
            ReportPage.objects.values_list("report_id", flat=True).distinct()
        )
        reports = [r for r in qs if r.report_id in report_ids_with_pages]

        job.reports_found = len(reports)
        job.save(update_fields=["reports_found"])
        logger.info("Bulk PDF export job %s: found %d reports", job_id, len(reports))

        if not reports:
            job.status = AnalysisJob.Statuses.SUCCEEDED
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "completed_at"])
            return

        # Build the ZIP in memory.
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for report in reports:
                try:
                    pdf_bytes, filename = _generate_plagiarism_pdf(report)
                    zf.writestr(filename, pdf_bytes)
                except Exception:
                    logger.warning(
                        "Bulk PDF export: failed to generate PDF for report %s",
                        report.report_id, exc_info=True,
                    )

                AnalysisJob.objects.filter(pk=job_id).update(
                    reports_processed=F("reports_processed") + 1,
                )

        # Upload ZIP to S3.
        event_label = ""
        if job.event_id:
            from events.models import Event
            try:
                event_label = Event.objects.get(pk=job.event_id).event_name
            except Event.DoesNotExist:
                event_label = str(job.event_id)
        else:
            event_label = "all_events"

        safe_label = re.sub(r"[^\w\-]", "_", event_label)
        type_suffix = f"_type{job.report_type}" if job.report_type is not None else ""
        zip_key = f"exports/plagiarism_{safe_label}{type_suffix}_job{job_id}.zip"

        zip_buf.seek(0)
        storage.save(zip_key, ContentFile(zip_buf.getvalue()))

        job.export_file = zip_key
        job.status = AnalysisJob.Statuses.SUCCEEDED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "export_file"])
        logger.info("Bulk PDF export job %s completed: %s", job_id, zip_key)

    except Exception as exc:
        logger.exception("Bulk PDF export job %s failed", job_id)
        job.status = AnalysisJob.Statuses.FAILED
        job.completed_at = timezone.now()
        job.error_message = str(exc)[:4000]
        job.save(update_fields=["status", "completed_at", "error_message"])
        raise
