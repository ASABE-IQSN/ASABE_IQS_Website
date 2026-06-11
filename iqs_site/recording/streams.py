"""Stream contract shared between the Flask producer and the Django recorder.

Flask appends each ingest payload to a Redis Stream with ``XADD`` under a single
field ``data`` holding the JSON string (in addition to the existing pub/sub
publish, which is left untouched for the SSE fan-out). The recorder reads these
streams with a consumer group.

To record a new channel: add one entry to REGISTRY mapping the stream key to its
model and a parser. The parser receives the decoded JSON payload (a dict) and
returns kwargs for the typed model columns; ``stream_id``/``raw``/``recorded_at``
are filled in by the recorder.
"""

from datetime import datetime, timezone

from . import models


def _ts(payload, *keys):
    """First present unix timestamp among `keys` -> aware datetime, else None."""
    for k in keys:
        v = payload.get(k)
        if v is None:
            continue
        try:
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            continue
    return None


def _pull_status(p):
    return {"pull_id": p.get("pull_id"), "status": p.get("status"),
            "event_ts": _ts(p, "ts")}


def _pull_data(p):
    return {"pull_id": p.get("pull_id"), "speed": p.get("speed"),
            "force": p.get("force"), "distance": p.get("distance"),
            "event_ts": _ts(p, "ts")}


def _dur_status(p):
    return {"run_id": p.get("run_id"), "status": p.get("status"),
            "current_lap": p.get("current_lap"), "total_laps": p.get("total_laps"),
            "elapsed_time": p.get("elapsed_time"), "event_ts": _ts(p, "ts")}


def _dur_data(p):
    return {"run_id": p.get("run_id"), "speed": p.get("speed"),
            "pressure": p.get("pressure"), "power": p.get("power"),
            "event_ts": _ts(p, "timestamp", "ts")}


def _man_status(p):
    return {"run_id": p.get("run_id"), "status": p.get("status"),
            "event_ts": _ts(p, "ts")}


def _load_toad(p):
    return {"run_id": p.get("run_id"), "speed": p.get("speed"),
            "drive_pressure": p.get("drive_pressure"), "event_ts": _ts(p, "ts")}


def _engine_data(p):
    return {"run_id": p.get("run_id"), "event_ts": _ts(p, "ts")}


# stream key -> (model, parser)
REGISTRY = {
    "ingest:pull:status":  (models.PullStatusEvent,            _pull_status),
    "ingest:pull:data":    (models.PullDataPoint,              _pull_data),
    "ingest:dur:status":   (models.DurabilityStatusEvent,      _dur_status),
    "ingest:dur:data":     (models.DurabilityDataPoint,        _dur_data),
    "ingest:man:status":   (models.ManeuverabilityStatusEvent, _man_status),
    "ingest:load_toad":    (models.LoadToadDataPoint,          _load_toad),
    "ingest:engine:data":  (models.EngineDataPoint,            _engine_data),
}

# Cap stream length on the Flask side (XADD MAXLEN ~) so an offline recorder
# can't grow Redis unbounded. Tune per expected backlog tolerance.
STREAM_MAXLEN = 100_000
