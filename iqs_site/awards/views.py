from django.shortcuts import render, get_object_or_404
from django.views.decorators.cache import cache_page
from collections import defaultdict
from iqs_site.utilities import log_view
from events.models import Event
from .models import AwardType, Award


@log_view
@cache_page(300)
def award_history(request):
    """All awards across all events, grouped by event (most recent first)."""
    awards = (
        Award.objects
        .select_related('award_type', 'event_team__event', 'event_team__team')
        .order_by('-event_team__event__event_datetime', 'display_order')
    )

    # Group by event
    grouped = defaultdict(list)
    event_order = []
    seen_events = set()
    for award in awards:
        event = award.event_team.event
        if event.event_id not in seen_events:
            event_order.append(event)
            seen_events.add(event.event_id)
        grouped[event.event_id].append(award)

    events_with_awards = [(event, grouped[event.event_id]) for event in event_order]

    return render(request, 'awards/award_history.html', {
        'events_with_awards': events_with_awards,
        'active_page': 'events',
    })


@log_view
@cache_page(300)
def awards_by_event(request, event_id):
    """All awards for a specific event, grouped by category."""
    event = get_object_or_404(Event, pk=event_id)
    awards = (
        Award.objects
        .select_related('award_type', 'event_team__team')
        .filter(event_team__event=event)
        .order_by('award_type__category', 'display_order')
    )

    # Group by category
    CATEGORY_LABELS = dict(AwardType.CATEGORY_CHOICES)
    grouped = defaultdict(list)
    for award in awards:
        grouped[award.award_type.category].append(award)

    categories_with_awards = [
        (CATEGORY_LABELS.get(cat, cat), awards_list)
        for cat, awards_list in grouped.items()
    ]

    return render(request, 'awards/awards_by_event.html', {
        'event': event,
        'categories_with_awards': categories_with_awards,
        'active_page': 'events',
    })


@log_view
@cache_page(300)
def award_type_history(request, award_type_id):
    """All recipients of one award type across all events."""
    award_type = get_object_or_404(AwardType, pk=award_type_id)
    awards = (
        Award.objects
        .select_related('event_team__event', 'event_team__team')
        .filter(award_type=award_type)
        .order_by('-event_team__event__event_datetime')
    )

    return render(request, 'awards/award_type_history.html', {
        'award_type': award_type,
        'awards': awards,
        'active_page': 'events',
    })
