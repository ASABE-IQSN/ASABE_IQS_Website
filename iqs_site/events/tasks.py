import csv
import logging
import shutil
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import PullData, PullExportJob

logger = logging.getLogger(__name__)

STATIC_ROOT_PATH = Path(getattr(settings, "STATIC_ROOT", "/var/www/quarterscale/static/"))
EXPORT_STATIC_DIR = STATIC_ROOT_PATH / "exports" / "pull_exports"
PUBLIC_BASE_URL = "https://iqsconnect.org"


def _build_download_url(zip_rel_path: str) -> str:
    rel = zip_rel_path.lstrip("/")
    return f"{PUBLIC_BASE_URL}/static/{rel}"


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def generate_pull_export_zip(self, job_id: int) -> dict:
    job = PullExportJob.objects.select_related("user").get(pk=job_id)

    job.status = PullExportJob.Statuses.RUNNING
    job.started_at = timezone.now()
    job.processed_pulls = 0
    job.error_message = None
    job.save(update_fields=["status", "started_at", "processed_pulls", "error_message"])

    final_zip_path = None

    try:
        export_items = list(
            job.items
            .select_related("pull__team", "pull__hook", "pull__event")
            .order_by("pull_id")
        )
        total = len(export_items)
        if job.total_pulls != total:
            job.total_pulls = total
            job.save(update_fields=["total_pulls"])

        with tempfile.TemporaryDirectory(prefix=f"pull_export_{job.pull_export_job_id}_") as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            csv_paths = []

            for idx, item in enumerate(export_items, start=1):
                pull = item.pull
                pull_id = pull.pull_id
                team_name = pull.team.team_name if pull.team else "team"
                hook_name = pull.hook.hook_name if pull.hook and pull.hook.hook_name else "hook"
                event_name = pull.event.event_name if pull.event and pull.event.event_name else "event"
                csv_name = f"{event_name}_{hook_name}_{team_name}_pull_{pull_id}.csv".replace(" ","_")
                csv_path = tmp_dir_path / csv_name

                rows = PullData.objects.filter(pull_id=pull_id).order_by("pull_time", "data_id")

                with csv_path.open("w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["pull_time", "distance", "speed", "chain_force"])
                    for row in rows:
                        writer.writerow([row.pull_time, row.distance, row.speed, row.chain_force])

                csv_paths.append(csv_path)

                if idx == total or idx % 10 == 0:
                    job.processed_pulls = idx
                    job.save(update_fields=["processed_pulls"])

            EXPORT_STATIC_DIR.mkdir(parents=True, exist_ok=True)
            zip_filename = f"{uuid.uuid4().hex}.zip"
            zip_temp_path = tmp_dir_path / zip_filename

            with ZipFile(zip_temp_path, "w", compression=ZIP_DEFLATED) as zip_file:
                for csv_path in csv_paths:
                    zip_file.write(csv_path, arcname=csv_path.name)

            final_zip_path = EXPORT_STATIC_DIR / zip_filename
            # Use move instead of replace to handle cross-device moves (/tmp -> mounted static dir).
            shutil.move(str(zip_temp_path), str(final_zip_path))
            logger.info("Pull export job %s wrote zip to %s", job.pull_export_job_id, final_zip_path)

        finished_at = timezone.now()
        zip_rel_path = f"exports/pull_exports/{zip_filename}"

        job.status = PullExportJob.Statuses.SUCCEEDED
        job.zip_rel_path = zip_rel_path
        job.download_url = _build_download_url(zip_rel_path)
        job.completed_at = finished_at
        job.expires_at = finished_at + timedelta(days=7)
        job.processed_pulls = total
        job.save(
            update_fields=[
                "status",
                "zip_rel_path",
                "download_url",
                "completed_at",
                "expires_at",
                "processed_pulls",
            ]
        )

        if job.user.email:
            message = render_to_string(
                "emails/pull_export_ready.txt",
                {
                    "job": job,
                    "download_url": job.download_url,
                    "expires_at": job.expires_at,
                },
            )
            send_mail(
                subject=f"Pull export ready (job #{job.pull_export_job_id})",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[job.user.email],
                fail_silently=False,
            )

        return {
            "job_id": job.pull_export_job_id,
            "status": job.status,
            "total": total,
            "download_url": job.download_url,
        }

    except Exception as exc:
        logger.exception("Failed pull export job %s", job.pull_export_job_id)

        if final_zip_path and final_zip_path.exists():
            try:
                final_zip_path.unlink()
            except OSError:
                logger.warning("Could not remove failed export zip for job %s", job.pull_export_job_id)

        job.status = PullExportJob.Statuses.FAILED
        job.completed_at = timezone.now()
        job.error_message = str(exc)[:4000]
        job.save(update_fields=["status", "completed_at", "error_message"])

        if job.user.email:
            try:
                message = render_to_string(
                    "emails/pull_export_failed.txt",
                    {"job": job, "error_message": job.error_message},
                )
                send_mail(
                    subject=f"Pull export failed (job #{job.pull_export_job_id})",
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[job.user.email],
                    fail_silently=True,
                )
            except Exception:
                logger.exception("Could not send export failure email for job %s", job.pull_export_job_id)

        raise


@shared_task(bind=True)
def cleanup_expired_pull_export_zips(self) -> dict:
    now = timezone.now()

    stale_jobs = PullExportJob.objects.filter(
        status=PullExportJob.Statuses.SUCCEEDED,
        expires_at__lt=now,
    ).exclude(zip_rel_path__isnull=True).exclude(zip_rel_path="")

    deleted_files = 0
    updated_jobs = 0

    for job in stale_jobs:
        file_path = STATIC_ROOT_PATH / job.zip_rel_path.lstrip("/")
        if file_path.exists():
            try:
                file_path.unlink()
                deleted_files += 1
            except OSError:
                logger.warning("Failed deleting stale export file for job %s", job.pull_export_job_id)

        job.status = PullExportJob.Statuses.EXPIRED
        job.zip_rel_path = None
        job.download_url = None
        job.save(update_fields=["status", "zip_rel_path", "download_url"])
        updated_jobs += 1

    return {
        "checked_at": now.isoformat(),
        "updated_jobs": updated_jobs,
        "deleted_files": deleted_files,
    }
