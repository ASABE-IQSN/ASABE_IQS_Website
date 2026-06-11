"""Telemetry recording tables.

These are NEW tables owned by Django (``managed = True`` -> created via
migrations), unlike most models in this project which are ``managed = False``
introspections of the pre-existing MySQL schema that Flask also writes to.

Design notes (expect churn):
- Every row keeps a ``raw`` JSON copy of the full ingest payload, so fields that
  change/appear on the device side are never lost before the typed columns catch
  up. Promote a field to a real column once it stabilises.
- ``stream_id`` is the Redis Stream entry id (e.g. ``"1718900000000-0"``). It's
  unique so re-reading the stream after a crash can't create duplicates.
- ``event_ts`` is the device/source timestamp from the payload; ``recorded_at``
  is when *we* persisted it. They can differ a lot under backlog/replay.
- Run association is a loose indexed integer, NOT a ForeignKey. The run tables
  (pulls, durability_runs, ...) are unmanaged and the high-rate data payloads
  don't currently carry a run id at all, so a hard FK would be premature.
"""

from django.db import models


class IngestRecord(models.Model):
    """Common columns for every recorded ingest message."""

    stream_id = models.CharField(max_length=64, unique=True)
    event_ts = models.DateTimeField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    raw = models.JSONField(default=dict)

    class Meta:
        abstract = True


# --- Pull -------------------------------------------------------------------

class PullStatusEvent(IngestRecord):
    pull_id = models.IntegerField(null=True, blank=True, db_index=True)
    status = models.IntegerField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = "rec_pull_status"
        indexes = [models.Index(fields=["pull_id", "event_ts"])]


class PullDataPoint(IngestRecord):
    # NOTE: pull/data currently has no pull_id in the payload. Either add it on
    # the ingest side or have the recorder stamp the active pull. Nullable until
    # then.
    pull_id = models.IntegerField(null=True, blank=True, db_index=True)
    speed = models.FloatField(null=True, blank=True)
    force = models.FloatField(null=True, blank=True)
    distance = models.FloatField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = "rec_pull_data"
        indexes = [models.Index(fields=["pull_id", "event_ts"])]


# --- Durability -------------------------------------------------------------

class DurabilityStatusEvent(IngestRecord):
    run_id = models.IntegerField(null=True, blank=True, db_index=True)
    status = models.IntegerField(null=True, blank=True)
    current_lap = models.IntegerField(null=True, blank=True)
    total_laps = models.IntegerField(null=True, blank=True)
    elapsed_time = models.FloatField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = "rec_dur_status"
        indexes = [models.Index(fields=["run_id", "event_ts"])]


class DurabilityDataPoint(IngestRecord):
    # Same id gap as PullDataPoint. Also partly derived from load_toad today --
    # decide which is the canonical recorded source before relying on both.
    run_id = models.IntegerField(null=True, blank=True, db_index=True)
    speed = models.FloatField(null=True, blank=True)
    pressure = models.FloatField(null=True, blank=True)
    power = models.FloatField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = "rec_dur_data"
        indexes = [models.Index(fields=["run_id", "event_ts"])]


# --- Maneuverability --------------------------------------------------------

class ManeuverabilityStatusEvent(IngestRecord):
    run_id = models.IntegerField(null=True, blank=True, db_index=True)
    status = models.IntegerField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = "rec_man_status"
        indexes = [models.Index(fields=["run_id", "event_ts"])]


# --- Load toad (raw durability telemetry source) ----------------------------

class LoadToadDataPoint(IngestRecord):
    run_id = models.IntegerField(null=True, blank=True, db_index=True)
    speed = models.FloatField(null=True, blank=True)
    drive_pressure = models.FloatField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = "rec_load_toad"
        indexes = [models.Index(fields=["run_id", "event_ts"])]


# --- Engine -----------------------------------------------------------------

class EngineDataPoint(IngestRecord):
    # Fields still loose; lean on `raw` until they settle.
    run_id = models.IntegerField(null=True, blank=True, db_index=True)

    class Meta:
        managed = True
        db_table = "rec_engine_data"
        indexes = [models.Index(fields=["run_id", "event_ts"])]
