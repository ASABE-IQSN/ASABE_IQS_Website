import csv
import json
import logging
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path
from statistics import mean
from zipfile import ZIP_DEFLATED, ZipFile

import redis as redis_lib
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Hook, Pull, PullData, PullExportJob, Team

logger = logging.getLogger(__name__)

def _build_download_url(zip_rel_path: str) -> str:
    rel = zip_rel_path.lstrip("/")
    return f"/media/{rel}"


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

            zip_filename = f"{uuid.uuid4().hex}.zip"
            zip_temp_path = tmp_dir_path / zip_filename

            with ZipFile(zip_temp_path, "w", compression=ZIP_DEFLATED) as zip_file:
                for csv_path in csv_paths:
                    zip_file.write(csv_path, arcname=csv_path.name)

            from iqs_site.storage import StaticStorage
            storage = StaticStorage()
            with open(zip_temp_path, "rb") as f:
                storage.save(f"exports/pull_exports/{zip_filename}", f)
            logger.info("Pull export job %s uploaded zip to SeaweedFS", job.pull_export_job_id)

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

    from iqs_site.storage import StaticStorage
    storage = StaticStorage()

    for job in stale_jobs:
        try:
            storage.delete(job.zip_rel_path.lstrip("/"))
            deleted_files += 1
        except Exception:
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


# ──────────────────────────────────────────────────────────────────────────
# Dynamic pull ETA recomputation
# ──────────────────────────────────────────────────────────────────────────

# Redis channel & snapshot key (mirrors Flask SSE_app.py constants).
CH_PULL_SCHEDULE = "pull:schedule"
K_PULL_SCHEDULE = "pull:schedule:latest"

# Fallback gap (seconds) when we have no completed-pull history.
_DEFAULT_GAP_SECONDS = 30
# Fallback duration (seconds) when we have no completed pulls and no
# hook window to divide. Roughly: pulls take half a minute.
_DEFAULT_DURATION_SECONDS = 30


def _to_epoch(dt) -> int:
    """Convert an aware datetime (UTC under USE_TZ=True) to unix epoch."""
    return int(dt.timestamp())


def _redis_client():
    return redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _publish_pull_schedule(hook: Hook, pulls: list[Pull]) -> None:
    team_ids = {p.team_id for p in pulls if p.team_id}
    teams_by_id = {
        t.team_id: t
        for t in Team.objects.filter(team_id__in=team_ids).only(
            "team_id", "team_name", "team_number"
        )
    } if team_ids else {}

    payload = {
        "hook_id": hook.hook_id,
        "event_id": hook.event_id,
        "computed_at": int(time.time()),
        "pulls": [
            {
                "pull_id": p.pull_id,
                "team_id": p.team_id,
                "team_name": getattr(teams_by_id.get(p.team_id), "team_name", None),
                "team_number": getattr(teams_by_id.get(p.team_id), "team_number", None),
                "run_order": p.run_order,
                "state": p.state,
                "start_time": p.start_time,
                "end_time": p.end_time,
                "expected_start_time": p.expected_start_time,
            }
            for p in sorted(pulls, key=lambda x: x.run_order)
        ],
    }
    body = json.dumps(payload)
    try:
        r = _redis_client()
        r.set(K_PULL_SCHEDULE, body)
        r.publish(CH_PULL_SCHEDULE, body)
    except Exception:
        logger.exception("Failed to publish pull schedule to Redis")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def recompute_pull_etas(self, hook_id: int) -> dict:
    """Recompute expected_start_time for SCHEDULED pulls in `hook_id`.

    Uses average pull duration and average between-pull gap from COMPLETED
    pulls in the hook to project ETAs forward. With no completed history,
    evenly distributes pulls across the hook's [start_time, end_time]
    window. Writes via Pull.objects.filter().update() (which does not fire
    post_save, preventing signal recursion), then publishes the resulting
    schedule to Redis channel `pull:schedule`.

    Returns a dict mapping pull_id → expected_start_time (unix epoch).
    """
    result: dict[int, int] = {}

    with transaction.atomic():
        try:
            hook = Hook.objects.select_for_update().get(pk=hook_id)
        except Hook.DoesNotExist:
            logger.warning("recompute_pull_etas: hook %s not found", hook_id)
            return result

        pulls = list(
            Pull.objects
            .select_for_update()
            .filter(hook_id=hook_id)
            .exclude(state=Pull.States.SCRATCHED)
            .order_by("run_order")
        )
        if not pulls:
            _publish_pull_schedule(hook, [])
            return result

        completed = [
            p for p in pulls
            if p.state == Pull.States.COMPLETED
            and p.start_time and p.end_time
        ]
        running = next(
            (p for p in pulls if p.state == Pull.States.RUNNING), None
        )
        scheduled = [p for p in pulls if p.state == Pull.States.SCHEDULED]

        # ── Case A: cold start ─────────────────────────────────────────
        if not completed and not running:
            if hook.start_time is None or hook.end_time is None:
                logger.info(
                    "recompute_pull_etas: hook %s has no window and no "
                    "history; nothing to compute", hook_id,
                )
                _publish_pull_schedule(hook, pulls)
                return result

            win_s = _to_epoch(hook.start_time)
            win_e = _to_epoch(hook.end_time)
            n = len(pulls)
            step = (win_e - win_s) / n if n else 0
            for i, p in enumerate(pulls):
                p.expected_start_time = int(win_s + step * i)

        # ── Case B: have history ───────────────────────────────────────
        else:
            durations = [p.end_time - p.start_time for p in completed]
            ordered_c = sorted(completed, key=lambda x: x.run_order)
            gaps = [
                b.start_time - a.end_time
                for a, b in zip(ordered_c, ordered_c[1:])
                if b.start_time and a.end_time
                and b.start_time > a.end_time
            ]

            # Hook-window-derived fallback for avg duration: split the
            # window by total pulls (so the cold-start spacing carries
            # over once a pull starts running).
            if hook.start_time and hook.end_time:
                hook_step = max(
                    1,
                    (_to_epoch(hook.end_time) - _to_epoch(hook.start_time))
                    // max(1, len(pulls)),
                )
            else:
                hook_step = _DEFAULT_DURATION_SECONDS + _DEFAULT_GAP_SECONDS

            avg_dur = mean(durations) if durations else max(
                1, hook_step - _DEFAULT_GAP_SECONDS
            )
            avg_gap = mean(gaps) if gaps else _DEFAULT_GAP_SECONDS

            if running:
                # Project from the running pull's actual start; don't
                # overwrite its ETA.
                anchor_start = running.start_time or int(time.time())
                cursor_end = anchor_start + avg_dur
            else:
                cursor_end = max(p.end_time for p in completed)

            for p in sorted(scheduled, key=lambda x: x.run_order):
                est = cursor_end + avg_gap
                p.expected_start_time = int(est)
                cursor_end = est + avg_dur

        # ── persist only SCHEDULED rows ────────────────────────────────
        for p in pulls:
            if (
                p.state == Pull.States.SCHEDULED
                and p.expected_start_time is not None
            ):
                Pull.objects.filter(pk=p.pk).update(
                    expected_start_time=p.expected_start_time,
                    updated_by_source="eta_recompute",
                )
                result[p.pull_id] = p.expected_start_time

        _publish_pull_schedule(hook, pulls)

    return result
