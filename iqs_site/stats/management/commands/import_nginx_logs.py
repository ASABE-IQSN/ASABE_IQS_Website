"""
Management command: import_nginx_logs

Parses one or more nginx access log files (combined or custom format) and
bulk-inserts the records into the nginx_log table.  Re-running is safe —
already-imported lines are skipped via a SHA-256 hash stored on each row.

Usage examples
--------------
  # Import a single file
  python manage.py import_nginx_logs --log-file /var/log/nginx/access.log

  # Import multiple files (e.g. rotated logs)
  python manage.py import_nginx_logs \
      --log-file /var/log/nginx/access.log \
      --log-file /var/log/nginx/access.log.1

  # Only import 404s and image requests (faster for targeted backfill)
  python manage.py import_nginx_logs \
      --log-file /var/log/nginx/access.log \
      --filter-status 404 \
      --filter-ext jpg jpeg png gif webp svg ico

  # Dry-run: print parsed records without writing to the database
  python manage.py import_nginx_logs --log-file /var/log/nginx/access.log --dry-run

Nginx log_format
----------------
The command expects the nginx "combined" format (the default):

    log_format combined '$remote_addr - $remote_user [$time_local] '
                        '"$request" $status $body_bytes_sent '
                        '"$http_referer" "$http_user_agent"';

If you use a custom format, adjust LOG_PATTERN below to match.
"""

from __future__ import annotations

import hashlib
import re
import sys
from datetime import datetime, timezone as dt_tz
from pathlib import Path
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from stats.models import NginxLog

# ---------------------------------------------------------------------------
# nginx combined log line regex
# Example line:
#   1.2.3.4 - - [07/Mar/2026:14:22:01 +0000] "GET /img/logo.png HTTP/1.1" 200 12345 "-" "Mozilla/5.0 ..."
# ---------------------------------------------------------------------------
LOG_PATTERN = re.compile(
    r'(?P<ip>\S+)'           # remote_addr
    r' - \S+'                # remote_user (ignored)
    r' \[(?P<time>[^\]]+)\]' # time_local
    r' "(?P<request>[^"]*)"' # request line  (may be empty / malformed)
    r' (?P<status>\d{3})'    # status code
    r' (?P<bytes>\S+)'       # body_bytes_sent (number or -)
    r' "(?P<referer>[^"]*)"' # http_referer
    r' "(?P<ua>[^"]*)"'      # http_user_agent
)

# nginx time format: 07/Mar/2026:14:22:01 +0000
TIME_FORMAT = "%d/%b/%Y:%H:%M:%S %z"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tiff", ".avif"}

BATCH_SIZE = 2000


def _parse_request(raw: str) -> tuple[str, str, str, str]:
    """Split 'METHOD /path?qs HTTP/1.x' into (method, url, query_string, protocol)."""
    parts = raw.split(" ", 2)
    if len(parts) == 3:
        method, full_path, protocol = parts
    elif len(parts) == 2:
        method, full_path, protocol = parts[0], parts[1], ""
    else:
        return raw[:16], raw, "", ""

    if "?" in full_path:
        url, qs = full_path.split("?", 1)
    else:
        url, qs = full_path, ""

    return method[:16], url[:2048], qs[:2048], protocol[:16]


def _parse_line(line: str) -> Optional[NginxLog]:
    """Return an unsaved NginxLog instance, or None if the line can't be parsed."""
    line = line.rstrip("\n")
    m = LOG_PATTERN.match(line)
    if not m:
        return None

    try:
        ts = datetime.strptime(m.group("time"), TIME_FORMAT)
    except ValueError:
        return None

    # Ensure timezone-aware UTC
    ts = ts.astimezone(dt_tz.utc)

    method, url, qs, protocol = _parse_request(m.group("request"))

    raw_bytes = m.group("bytes")
    bytes_sent = int(raw_bytes) if raw_bytes.isdigit() else 0

    source_hash = hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest()

    return NginxLog(
        ip=m.group("ip")[:45],
        time=ts,
        method=method,
        url=url,
        query_string=qs,
        protocol=protocol,
        status_code=int(m.group("status")),
        bytes_sent=bytes_sent,
        referer=m.group("referer")[:2048],
        user_agent=m.group("ua")[:4096],
        source_hash=source_hash,
    )


class Command(BaseCommand):
    help = "Import nginx access log lines into the nginx_log database table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-file",
            dest="log_files",
            action="append",
            metavar="PATH",
            required=True,
            help="Path to an nginx access.log file. Repeat to import multiple files.",
        )
        parser.add_argument(
            "--filter-status",
            dest="filter_status",
            nargs="*",
            type=int,
            metavar="CODE",
            help="Only import lines with these HTTP status codes (e.g. --filter-status 404 301).",
        )
        parser.add_argument(
            "--filter-ext",
            dest="filter_ext",
            nargs="*",
            metavar="EXT",
            help=(
                "Only import lines whose URL ends with these extensions "
                "(e.g. --filter-ext jpg png). "
                "Use 'images' as a shortcut for all common image extensions."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and print records without writing to the database.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=BATCH_SIZE,
            help=f"Rows per bulk_create batch (default {BATCH_SIZE}).",
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        log_files: list[str] = options["log_files"]
        filter_status: Optional[set[int]] = set(options["filter_status"]) if options["filter_status"] else None
        dry_run: bool = options["dry_run"]
        batch_size: int = options["batch_size"]

        # Resolve --filter-ext
        raw_exts = options.get("filter_ext") or []
        filter_ext: Optional[set[str]] = None
        if raw_exts:
            expanded: set[str] = set()
            for e in raw_exts:
                if e.lower() == "images":
                    expanded |= IMAGE_EXTENSIONS
                else:
                    expanded.add(("." if not e.startswith(".") else "") + e.lower())
            filter_ext = expanded

        total_parsed = 0
        total_skipped_filter = 0
        total_inserted = 0
        total_duplicate = 0
        total_errors = 0

        for log_path_str in log_files:
            log_path = Path(log_path_str)
            if not log_path.exists():
                raise CommandError(f"Log file not found: {log_path}")

            self.stdout.write(f"Reading {log_path} …")

            batch: list[NginxLog] = []

            def flush_batch():
                nonlocal total_inserted, total_duplicate
                if not batch:
                    return
                if dry_run:
                    for obj in batch:
                        self.stdout.write(
                            f"  DRY-RUN  {obj.time.isoformat()} {obj.ip:>15}  "
                            f"{obj.status_code}  {obj.bytes_sent:>10} B  {obj.method} {obj.url}"
                        )
                    batch.clear()
                    return
                with transaction.atomic():
                    created = NginxLog.objects.bulk_create(batch, ignore_conflicts=True)
                inserted = len(created)
                dupes = len(batch) - inserted
                total_inserted += inserted
                total_duplicate += dupes
                batch.clear()

            with log_path.open("r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    total_parsed += 1

                    obj = _parse_line(raw_line)
                    if obj is None:
                        total_errors += 1
                        continue

                    # Apply filters
                    if filter_status and obj.status_code not in filter_status:
                        total_skipped_filter += 1
                        continue

                    if filter_ext:
                        suffix = Path(obj.url).suffix.lower()
                        if suffix not in filter_ext:
                            total_skipped_filter += 1
                            continue

                    batch.append(obj)

                    if len(batch) >= batch_size:
                        flush_batch()
                        sys.stdout.flush()

            flush_batch()

        label = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{label}Done.\n"
            f"  Lines parsed  : {total_parsed:,}\n"
            f"  Skipped (filter): {total_skipped_filter:,}\n"
            f"  Parse errors  : {total_errors:,}\n"
            f"  Inserted      : {total_inserted:,}\n"
            f"  Duplicates    : {total_duplicate:,}  (already in DB)\n"
        ))
