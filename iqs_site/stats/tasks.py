import logging
from pathlib import Path

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)

NGINX_LOG_FILES = [
    "/var/log/nginx/quarterscale_access.log",
    "/var/log/nginx/testing_access.log",
    "/var/log/nginx/api_access.log",
    "/var/log/nginx/ingest_access.log",
]


@shared_task(bind=True, name="stats.import_nginx_logs")
def import_nginx_logs(self):
    """Import any new nginx log lines since the last run. Safe to run repeatedly — duplicates are skipped."""
    files_found = [f for f in NGINX_LOG_FILES if Path(f).exists()]
    if not files_found:
        logger.warning("import_nginx_logs: no log files found at %s", NGINX_LOG_FILES)
        return {"imported_files": 0}

    args = []
    for f in files_found:
        args += ["--log-file", f]

    logger.info("import_nginx_logs: importing %s", files_found)
    call_command("import_nginx_logs", *args)
    return {"imported_files": len(files_found)}
