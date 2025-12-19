from __future__ import annotations

from datetime import timedelta
from typing import Dict, List

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone


AVAILABLE_METRICS = [
    ("speed", "Speed (ft/s)"),
    ("force", "Force (lbf)"),
    ("distance", "Distance (ft)"),
    ("rpm", "Engine RPM"),
]


def plot_page(request):
    return render(
        request,
        "stats/plot.html",
        {"available_metrics": AVAILABLE_METRICS},
    )


def test_series_api(request):
    """
    Returns deterministic "constant" test series (same every call).
    Query:
      ?metrics=speed&metrics=force
    """
    metrics = request.GET.getlist("metrics") or ["speed"]

    # Time base: last 5 minutes, 1 Hz
    n = 300
    end = timezone.now()
    start = end - timedelta(seconds=n - 1)
    timestamps = [(start + timedelta(seconds=i)).isoformat() for i in range(n)]

    # Generate deterministic data (no randomness)
    # Keep it simple but not flat so zooming is interesting.
    series: Dict[str, Dict[str, List]] = {}

    for m in metrics:
        if m == "speed":
            # speed ramps up then stabilizes
            vals = [min(18.0, 3.0 + i * 0.08) for i in range(n)]
            series[m] = {"timestamps": timestamps, "values": vals, "label": "Speed (ft/s)"}

        elif m == "force":
            # force rises, small oscillation
            vals = [200.0 + i * 2.2 + (15.0 if (i // 10) % 2 == 0 else -15.0) for i in range(n)]
            series[m] = {"timestamps": timestamps, "values": vals, "label": "Force (lbf)"}

        elif m == "distance":
            # distance is cumulative integral-ish of speed
            dist = 0.0
            vals = []
            for i in range(n):
                v = min(18.0, 3.0 + i * 0.08)
                dist += v * 1.0  # dt=1s
                vals.append(dist)
            series[m] = {"timestamps": timestamps, "values": vals, "label": "Distance (ft)"}

        elif m == "rpm":
            # rpm ramps and has a step change
            vals = [1200 + int(i * 6) + (200 if i > 160 else 0) for i in range(n)]
            series[m] = {"timestamps": timestamps, "values": vals, "label": "Engine RPM"}

        else:
            # unknown metric -> empty series
            series[m] = {"timestamps": [], "values": [], "label": m}
    print(series)
    return JsonResponse({"series": series})
