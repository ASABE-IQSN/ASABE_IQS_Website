"""Drain ingest Redis Streams into the recording tables using the Django ORM.

Run as its own long-lived service:

    python manage.py record_ingest

Properties:
- Consumer group (XREADGROUP + XACK): unacked messages are redelivered after a
  crash/redeploy, so no data loss and no duplicates (stream_id is also unique).
- Batched bulk_create: one INSERT per stream per read, so 10Hz x many runs is
  trivial DB load.
- close_old_connections() between reads keeps the long-lived process from
  tripping MySQL's wait_timeout ("server has gone away").

NOTE: this must read from the SAME Redis DB index that Flask writes to. Flask's
REDIS_URL defaults to db 0; Django settings default to db 1. Pass --redis-url or
make sure both env vars point at the same db.
"""

import json
import time

import redis
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from recording.streams import REGISTRY

GROUP = "recorder"


class Command(BaseCommand):
    help = "Consume ingest Redis Streams and persist telemetry via the ORM."

    def add_arguments(self, parser):
        parser.add_argument("--redis-url", default=getattr(settings, "REDIS_URL", None),
                            help="Override Redis URL (must match Flask's db index).")
        parser.add_argument("--consumer", default="recorder-1",
                            help="Consumer name within the group.")
        parser.add_argument("--block-ms", type=int, default=5000,
                            help="XREADGROUP block timeout per poll.")
        parser.add_argument("--count", type=int, default=500,
                            help="Max entries read per stream per poll.")

    def handle(self, *args, **opts):
        r = redis.from_url(opts["redis_url"], decode_responses=True)
        streams = list(REGISTRY.keys())

        # Create the group on each stream (MKSTREAM so it works before any data).
        for key in streams:
            try:
                r.xgroup_create(key, GROUP, id="0", mkstream=True)
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

        self.stdout.write(self.style.SUCCESS(
            f"record_ingest: consuming {len(streams)} streams as {GROUP}/{opts['consumer']}"))

        read_keys = {key: ">" for key in streams}
        while True:
            resp = r.xreadgroup(GROUP, opts["consumer"], read_keys,
                                count=opts["count"], block=opts["block_ms"])
            if not resp:
                close_old_connections()
                continue

            close_old_connections()
            for stream_key, entries in resp:
                self._persist(r, stream_key, entries)

    def _persist(self, r, stream_key, entries):
        model, parse = REGISTRY[stream_key]
        rows, ack_ids = [], []
        for entry_id, fields in entries:
            try:
                payload = json.loads(fields["data"])
                rows.append(model(stream_id=entry_id, raw=payload, **parse(payload)))
                ack_ids.append(entry_id)
            except Exception as e:  # noqa: BLE001 - bad entry must not stall the stream
                self.stderr.write(f"[{stream_key}] skipping {entry_id}: {e!r}")
                ack_ids.append(entry_id)  # ack so it doesn't redeliver forever

        if rows:
            # ignore_conflicts: re-delivered entries (same unique stream_id) are no-ops.
            model.objects.bulk_create(rows, ignore_conflicts=True)
        if ack_ids:
            r.xack(stream_key, GROUP, *ack_ids)
