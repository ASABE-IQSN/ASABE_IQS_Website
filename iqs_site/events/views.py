# Create your views here.

from django.shortcuts import render, get_object_or_404
from .models import Event, Pull, Hook


def event_list(request):
    events = Event.objects.order_by("-start_date", "name")
    return render(request, "events/event_list.html", {"events": events})


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)

    # All pulls for this event, with team + hook preloaded
    pulls = (
        Pull.objects.filter(event=event)
        .select_related("team", "hook")
        .order_by("-final_distance")
    )

    # Simple leaderboard: top 3 per (class_name, hook number)
    leaderboard = {}
    for pull in pulls:
        if pull.hook:
            key = (pull.hook.class_name, pull.hook.number)
        else:
            key = ("Unclassified", 0)

        leaderboard.setdefault(key, []).append(pull)

    # Trim to top 3 per class/hook
    for key in leaderboard:
        leaderboard[key] = leaderboard[key][:3]

    context = {
        "event": event,
        "pulls": pulls,
        "leaderboard": leaderboard,
    }
    return render(request, "events/event_detail.html", context)
