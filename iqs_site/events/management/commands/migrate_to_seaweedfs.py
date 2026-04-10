"""
One-time management command to migrate existing files from the local
filesystem into SeaweedFS S3 buckets.

Usage:
    python manage.py migrate_to_seaweedfs              # full migration
    python manage.py migrate_to_seaweedfs --dry-run     # preview only
    python manage.py migrate_to_seaweedfs --only static # just one category
"""

import os
from pathlib import Path

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand


CATEGORIES = {
    "static": {
        "local_dir": "/var/www/quarterscale/static",
        "bucket": "iqs-static",
    },
    "media": {
        "local_dir": "/var/www/quarterscale/static",  # MEDIA_ROOT == STATIC_ROOT (known quirk)
        "bucket": "iqs-media",
        # Only migrate known media subdirectories to avoid duplicating static files
        "subdirs": ["engagement", "form_responses", "awards", "photos", "exports", "techin"],
    },
    "reports": {
        "local_dir": "/var/www/quarterscale/reports",
        "bucket": "iqs-reports",
    },
}


class Command(BaseCommand):
    help = "Migrate local files to SeaweedFS S3 buckets"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List files that would be uploaded without actually uploading.",
        )
        parser.add_argument(
            "--only",
            choices=list(CATEGORIES.keys()),
            help="Migrate only one category (static, media, or reports).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        only = options.get("only")

        s3 = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )

        categories = {only: CATEGORIES[only]} if only else CATEGORIES

        for name, cfg in categories.items():
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {name} ==="))
            local_dir = Path(cfg["local_dir"])

            if not local_dir.exists():
                self.stdout.write(self.style.WARNING(f"  Directory {local_dir} does not exist, skipping."))
                continue

            bucket = cfg["bucket"]
            subdirs = cfg.get("subdirs")

            # Ensure bucket exists
            if not dry_run:
                try:
                    s3.head_bucket(Bucket=bucket)
                except Exception:
                    try:
                        self.stdout.write(f"  Creating bucket {bucket}...")
                        s3.create_bucket(Bucket=bucket)
                    except s3.exceptions.BucketAlreadyExists:
                        self.stdout.write(f"  Bucket {bucket} already exists, continuing.")

            uploaded = 0
            skipped = 0

            if subdirs:
                # Only walk specific subdirectories
                for subdir in subdirs:
                    subpath = local_dir / subdir
                    if not subpath.exists():
                        continue
                    uploaded, skipped = self._upload_tree(
                        s3, subpath, local_dir, bucket, dry_run, uploaded, skipped
                    )
            else:
                uploaded, skipped = self._upload_tree(
                    s3, local_dir, local_dir, bucket, dry_run, uploaded, skipped
                )

            action = "Would upload" if dry_run else "Uploaded"
            self.stdout.write(
                self.style.SUCCESS(f"  {action} {uploaded} files, skipped {skipped}")
            )

    def _upload_tree(self, s3, walk_root, base_dir, bucket, dry_run, uploaded, skipped):
        for dirpath, _dirnames, filenames in os.walk(walk_root):
            for filename in filenames:
                filepath = Path(dirpath) / filename
                key = str(filepath.relative_to(base_dir))

                if dry_run:
                    self.stdout.write(f"  [dry-run] {key}")
                    uploaded += 1
                    continue

                try:
                    s3.head_object(Bucket=bucket, Key=key)
                    skipped += 1  # already exists
                except Exception:
                    s3.upload_file(str(filepath), bucket, key)
                    uploaded += 1

        return uploaded, skipped
