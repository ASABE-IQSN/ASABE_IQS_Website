"""Publish clipper output: link each uploaded clip to its performance event by
creating a PerformanceEventMedia row.

Normal flow is two steps in two places:
  1. tools/video_clipper/upload.py runs on the workstation (mp4 files + browser
     OAuth live there), uploading each clip to YouTube and writing its youtube_id
     into the manifest.
  2. THIS command runs in the web container (Django + DB) and reads those
     youtube_ids to create PerformanceEventMedia rows on the site.

This command operates on the manifest JSON directly, so it is self-contained and
needs nothing from the tools/ directory (which isn't present in the container) —
just copy the manifest.json in and run.

Usage:
    python manage.py publish_clips path/to/manifest.json \
        [--approve] [--user <username>] [--dry-run]

    # all-in-one (only where the YouTube libs + OAuth + mp4s are available):
    python manage.py publish_clips manifest.json --upload --client-secrets cs.json

Idempotent: each clip is marked `media_linked` in the manifest once its DB row
exists, so re-running skips it. Clips without a youtube_id (not uploaded yet) and
untagged clips (no performance event) are skipped with a note.
"""

import json
import sys
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from events.models import PerformanceEventMedia


def _resolve_user(username):
    User = get_user_model()
    if username:
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User {username!r} not found")
    user = User.objects.filter(is_superuser=True).order_by("id").first()
    if not user:
        raise CommandError("No --user given and no superuser exists to attribute uploads to")
    return user


def _find_youtube_uploader(client_secrets):
    """Lazily locate tools/video_clipper/youtube.py (only needed for --upload)."""
    candidates = list(Path(__file__).resolve().parents) + list(Path.cwd().resolve().parents) + [Path.cwd()]
    for base in candidates:
        tool_dir = base / "tools" / "video_clipper"
        if (tool_dir / "youtube.py").exists():
            if str(tool_dir) not in sys.path:
                sys.path.insert(0, str(tool_dir))
            from youtube import YouTubeUploader  # noqa: E402
            return YouTubeUploader(client_secrets=client_secrets)
    raise CommandError(
        "--upload needs tools/video_clipper/youtube.py, which isn't reachable here. "
        "Upload on the workstation with upload.py instead, then run this without --upload."
    )


class Command(BaseCommand):
    help = "Link uploaded clips to performance events (create PerformanceEventMedia rows)."

    def add_arguments(self, parser):
        parser.add_argument("manifest", help="manifest.json produced by the clipper")
        parser.add_argument("--approve", action="store_true",
                            help="mark created media approved=True (visible immediately)")
        parser.add_argument("--user", help="username to attribute media to (default: a superuser)")
        parser.add_argument("--dry-run", action="store_true",
                            help="print intended actions without writing")
        # --upload: only usable where YouTube libs + OAuth + mp4s exist.
        parser.add_argument("--upload", action="store_true",
                            help="also upload clips lacking a youtube_id (rare; normally use upload.py)")
        parser.add_argument("--privacy", default="unlisted",
                            choices=["public", "unlisted", "private"])
        parser.add_argument("--client-secrets", help="OAuth client secrets JSON (with --upload)")

    def handle(self, *args, **opts):
        manifest_path = Path(opts["manifest"])
        if not manifest_path.exists():
            raise CommandError(f"manifest not found: {manifest_path}")
        data = json.loads(manifest_path.read_text())
        clips = data.get("clips", [])
        if not clips:
            raise CommandError("manifest has no clips")

        user = _resolve_user(opts.get("user"))
        dry = opts["dry_run"]

        uploader = None
        if opts["upload"] and not dry:
            uploader = _find_youtube_uploader(opts.get("client_secrets"))

        def save():
            manifest_path.write_text(json.dumps(data, indent=2))

        linked = uploaded = skipped = 0

        for clip in clips:
            label = clip.get("label") or "(unlabeled)"
            start, end = clip.get("start"), clip.get("end")
            if start is None or end is None or end <= start:
                raise CommandError(f"invalid start/end on clip {label!r}")

            if clip.get("media_linked"):
                skipped += 1
                self.stdout.write(f"skip (already linked): {label}")
                continue

            # Optional upload here (only if asked and not yet on YouTube).
            if not clip.get("youtube_id") and uploader and clip.get("file"):
                video_path = Path(clip["file"])
                if not video_path.is_absolute():
                    video_path = manifest_path.parent / video_path
                if not video_path.exists():
                    raise CommandError(f"clip file missing: {video_path}")
                self.stdout.write(f"uploading: {label} …")
                clip["youtube_id"] = uploader.upload(
                    video_path, title=label, description=clip.get("caption") or "",
                    privacy=opts["privacy"])
                clip["published"] = True
                uploaded += 1
                save()

            if not clip.get("youtube_id"):
                self.stderr.write(self.style.WARNING(
                    f"skip (not on YouTube yet — run upload.py first): {label}"))
                skipped += 1
                continue

            pe_type = clip.get("performance_event_type")
            pe_id = clip.get("performance_event_id")
            if not (pe_type and pe_id):
                self.stdout.write(self.style.WARNING(
                    f"skip (untagged, no performance event): {label}"))
                skipped += 1
                continue

            yid = clip["youtube_id"]
            if dry:
                self.stdout.write(
                    f"[dry-run] link youtu.be/{yid} -> type={pe_type} id={pe_id} "
                    f"(approved={opts['approve']})")
                continue

            PerformanceEventMedia.objects.create(
                performance_event_type=pe_type,
                performance_event_id=pe_id,
                media_type=PerformanceEventMedia.MediaTypes.YOUTUBE_VIDEO,
                # Templates embed via https://www.youtube.com/embed/{{vid.link}},
                # so link must be the BARE video id, not a full URL.
                link=yid,
                caption=(clip.get("caption") or None),
                approved=opts["approve"],
                uploaded_by=user,
                submitted_from_ip="127.0.0.1",
            )
            clip["media_linked"] = True
            linked += 1
            save()
            self.stdout.write(self.style.SUCCESS(
                f"linked youtu.be/{yid} -> type={pe_type} id={pe_id}"))

        if dry:
            self.stdout.write(self.style.SUCCESS("dry-run complete"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"done: {uploaded} uploaded, {linked} linked, {skipped} skipped"))
