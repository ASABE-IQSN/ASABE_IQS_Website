from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.cache import cache_page
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Coalesce
from collections import defaultdict
from events.models import Event, EventTeam, EventTeamPhoto
from .models import AwardType, Award


def _team_photo_annotation():
    """Return a Coalesce(official photo, any approved photo) subquery for Award querysets."""
    official = (
        EventTeamPhoto.objects
        .filter(event_team=OuterRef('event_team'), official=True, approved=True)
        .order_by('event_team_photo_id')
        .values('photo_path')[:1]
    )
    any_approved = (
        EventTeamPhoto.objects
        .filter(event_team=OuterRef('event_team'), approved=True)
        .order_by('event_team_photo_id')
        .values('photo_path')[:1]
    )
    return Coalesce(Subquery(official), Subquery(any_approved))


@cache_page(300)
def award_history(request):
    """All awards across all events, grouped by event (most recent first)."""
    awards = (
        Award.objects
        .select_related('award_type__team_class', 'event_team__event', 'event_team__team')
        .annotate(team_photo_path=_team_photo_annotation())
        .order_by('-event_team__event__event_datetime', 'award_type__display_order', 'placement')
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


@cache_page(300)
def awards_by_event(request, event_id):
    """All awards for a specific event, grouped by category."""
    event = get_object_or_404(Event, pk=event_id)
    awards = (
        Award.objects
        .select_related('award_type__team_class', 'event_team__team')
        .filter(event_team__event=event)
        .annotate(team_photo_path=_team_photo_annotation())
        .order_by('award_type__display_order', 'placement')
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


@cache_page(300)
def award_type_history(request, award_type_id):
    """All recipients of one award type across all events."""
    award_type = get_object_or_404(AwardType, pk=award_type_id)
    awards = (
        Award.objects
        .select_related('event_team__event', 'event_team__team')
        .filter(award_type=award_type)
        .order_by('-event_team__event__event_datetime', 'placement')
    )

    return render(request, 'awards/award_type_history.html', {
        'award_type': award_type,
        'awards': awards,
        'active_page': 'events',
    })


@login_required
def manage_event_list(request):
    """Staff-only: pick an event to manage awards for."""
    if not request.user.is_staff:
        raise PermissionDenied

    events = Event.objects.order_by('-event_datetime')
    return render(request, 'awards/manage_event_list.html', {
        'events': events,
        'active_page': 'events',
    })


@login_required
def manage_event_awards(request, event_id):
    """Staff-only: assign awards for all award types at a given event."""
    if not request.user.is_staff:
        raise PermissionDenied

    event = get_object_or_404(Event, pk=event_id)

    # All EventTeams for this event, with team class info
    event_teams_qs = (
        EventTeam.objects
        .select_related('team__team_class')
        .filter(event=event)
        .order_by('team__team_name')
    )

    # Group EventTeams by class id (None = no class)
    teams_by_class = defaultdict(list)
    all_event_teams = list(event_teams_qs)
    for et in all_event_teams:
        class_id = et.team.team_class_id if et.team.team_class else None
        teams_by_class[class_id].append(et)

    # All award types, grouped by class
    award_types = (
        AwardType.objects
        .select_related('team_class')
        .order_by('team_class__name', 'display_order', 'name')
    )

    # Existing awards for this event grouped by award_type_id, sorted by placement
    existing_by_at = defaultdict(list)
    for award in Award.objects.filter(event_team__event=event).order_by('placement'):
        existing_by_at[award.award_type_id].append({
            'placement': award.placement,
            'event_team_id': award.event_team_id,
        })

    if request.method == 'POST':
        try:
            with transaction.atomic():
                Award.objects.filter(event_team__event=event).delete()
                seen_pairs = set()
                for at in award_types:
                    count = int(request.POST.get(f'row_count_{at.award_type_id}', 0))
                    for i in range(count):
                        p_val = request.POST.get(f'p_{at.award_type_id}_{i}', '').strip()
                        t_val = request.POST.get(f't_{at.award_type_id}_{i}', '').strip()
                        if p_val and t_val:
                            pair = (at.award_type_id, int(t_val))
                            if pair not in seen_pairs:
                                seen_pairs.add(pair)
                                Award.objects.create(
                                    award_type=at,
                                    event_team_id=int(t_val),
                                    placement=int(p_val),
                                )
        except Exception as e:
            messages.error(request, f"Error saving awards: {e}")
        else:
            messages.success(request, f"Awards for {event.event_name} saved.")
            return redirect('awards:manage_event_awards', event_id=event_id)

    # Build display structure
    at_by_class = defaultdict(list)
    seen_class_ids = []
    for at in award_types:
        cid = at.team_class_id
        at_by_class[cid].append(at)
        if cid not in seen_class_ids:
            seen_class_ids.append(cid)

    class_groups = []
    for cid in seen_class_ids:
        at_list = at_by_class[cid]
        first_at = at_list[0]
        label = first_at.team_class.name if first_at.team_class else 'General'
        teams = (
            teams_by_class.get(cid, [])
            if cid is not None
            else all_event_teams
        )

        award_rows = []
        for at in at_list:
            # Initial rows: existing awards or a single blank 1st-place row
            initial_rows = existing_by_at.get(at.award_type_id) or [{'placement': 1, 'event_team_id': None}]
            award_rows.append({
                'award_type': at,
                'team_options': teams,
                'initial_rows': initial_rows,
            })

        class_groups.append({'label': label, 'award_rows': award_rows})

    return render(request, 'awards/manage_event_awards.html', {
        'event': event,
        'class_groups': class_groups,
        'placement_choices': Award.PLACEMENT_CHOICES,
        'active_page': 'events',
    })
