import json
import time

import redis as redis_lib
from django.conf import settings as django_settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from django.db.models import Count
from events.models import Event, EventTeam, Team
from .forms import CrowdSubmissionForm
from .models import (
    CrowdSubmission,
    FanVote,
    FanVoteCategory,
    Poll,
    PollOption,
    ReactionAggregate,
)


# ── Redis helpers ────────────────────────────────────────────────────────────

def _redis():
    return redis_lib.Redis.from_url(django_settings.REDIS_URL, decode_responses=True)


def _publish(r, snapshot_key, channel, payload):
    s = json.dumps(payload)
    r.set(snapshot_key, s)
    r.publish(channel, s)


def _active_event():
    return Event.objects.filter(event_active=True).first()


# ── Feature 1: Crowd Submission ──────────────────────────────────────────────

@login_required
def submit_form(request):
    throttle_key = f"engagement:throttle:submit:{request.user.id}"
    r = _redis()
    throttled = r.exists(throttle_key)

    if request.method == 'POST':
        if throttled:
            return render(request, 'engagement/submit.html', {
                'form': CrowdSubmissionForm(),
                'error': 'You submitted recently. Please wait a moment before submitting again.',
                'throttled': True,
            })

        form = CrowdSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.submitted_by = request.user
            submission.event = _active_event()
            submission.save()
            r.set(throttle_key, '1', ex=180)
            return render(request, 'engagement/submit.html', {
                'form': CrowdSubmissionForm(),
                'success': True,
            })
    else:
        form = CrowdSubmissionForm()

    return render(request, 'engagement/submit.html', {
        'form': form,
        'throttled': throttled,
    })


@staff_member_required
def staff_hub(request):
    return render(request, 'engagement/staff_hub.html')


@staff_member_required
def producer_queue(request):
    pending = CrowdSubmission.objects.filter(status='pending').select_related('submitted_by', 'event')
    return render(request, 'engagement/producer_queue.html', {'submissions': pending})


@staff_member_required
@require_POST
def approve_submission(request, submission_id):
    sub = get_object_or_404(CrowdSubmission, pk=submission_id, status='pending')
    sub.status = 'approved'
    sub.reviewed_by = request.user
    sub.reviewed_at = timezone.now()
    sub.save()

    r = _redis()
    if sub.submission_type == 'photo' and sub.photo:
        image_url = request.build_absolute_uri(sub.photo.url)
        caption = sub.text or ''
        payload = {
            'layout': 'image',
            'image_url': image_url,
            'question': f'From: {sub.submitted_by.username if sub.submitted_by else "Fan"}',
            'answer': caption,
            'form_name': 'Fan Submission',
            'team_name': '',
            'ts': time.time(),
        }
    else:
        username = sub.submitted_by.username if sub.submitted_by else 'Fan'
        payload = {
            'layout': 'stat',
            'question': f'From: {username}',
            'answer': sub.text,
            'form_name': 'Fan Comment',
            'team_name': '',
            'ts': time.time(),
        }

    _publish(r, 'overlay:card:latest', 'overlay:card', payload)
    return JsonResponse({'ok': True})


@staff_member_required
@require_POST
def reject_submission(request, submission_id):
    sub = get_object_or_404(CrowdSubmission, pk=submission_id, status='pending')
    sub.status = 'rejected'
    sub.reviewed_by = request.user
    sub.reviewed_at = timezone.now()
    sub.save()
    return JsonResponse({'ok': True})


# ── Feature 2: Emoji Reactions ───────────────────────────────────────────────

VALID_EMOJIS = {'fire', 'clap', 'wow', 'tractor'}


@require_POST
def react(request):
    if not request.session.session_key:
        request.session.create()

    emoji = request.POST.get('emoji', '')
    if emoji not in VALID_EMOJIS:
        return JsonResponse({'error': 'invalid emoji'}, status=400)

    session_key = request.session.session_key
    throttle_key = f"engagement:throttle:react:{session_key}:{emoji}"
    r = _redis()

    if r.exists(throttle_key):
        return JsonResponse({'error': 'throttled'}, status=429)

    event = _active_event()
    if not event:
        return JsonResponse({'error': 'no active event'}, status=400)

    agg, _ = ReactionAggregate.objects.get_or_create(event=event, emoji=emoji, defaults={'count': 0})
    ReactionAggregate.objects.filter(pk=agg.pk).update(count=F('count') + 1)
    r.set(throttle_key, '1', ex=60)

    all_agg = ReactionAggregate.objects.filter(event=event)
    counts = {a.emoji: a.count for a in all_agg}
    # refetch the one we just incremented
    agg.refresh_from_db()
    counts[emoji] = agg.count

    payload = {
        'event_id': event.event_id,
        'counts': counts,
        'ts': time.time(),
    }
    _publish(r, 'engagement:reactions:latest', 'engagement:reactions', payload)
    return JsonResponse({'ok': True, 'counts': counts})


# ── Feature 3: Polls ─────────────────────────────────────────────────────────

@staff_member_required
def poll_manage(request):
    polls = Poll.objects.prefetch_related('options').order_by('-created_at')
    return render(request, 'engagement/poll_manage.html', {'polls': polls})


@staff_member_required
@require_POST
def poll_create(request):
    question = request.POST.get('question', '').strip()
    event_id = request.POST.get('event_id')
    options_raw = request.POST.getlist('option_text')
    options_raw = [o.strip() for o in options_raw if o.strip()]

    if not question or len(options_raw) < 2:
        return JsonResponse({'error': 'Question and at least 2 options required.'}, status=400)

    event = None
    if event_id:
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            pass

    poll = Poll.objects.create(
        question=question,
        event=event,
        created_by=request.user,
        status='draft',
    )
    for i, text in enumerate(options_raw):
        PollOption.objects.create(poll=poll, option_text=text, order=i)

    return JsonResponse({'ok': True, 'poll_id': poll.poll_id})


def _poll_payload(poll):
    options = list(poll.options.all())
    total = sum(o.vote_count for o in options)
    return {
        'poll_id': poll.poll_id,
        'question': poll.question,
        'status': poll.status,
        'total_votes': total,
        'options': [
            {
                'option_id': o.option_id,
                'text': o.option_text,
                'votes': o.vote_count,
                'pct': round(o.vote_count / total * 100) if total else 0,
            }
            for o in options
        ],
        'ts': time.time(),
    }


@staff_member_required
@require_POST
def poll_activate(request, poll_id):
    Poll.objects.filter(status='active').update(status='closed')

    poll = get_object_or_404(Poll, pk=poll_id)
    poll.status = 'active'
    poll.activated_at = timezone.now()
    poll.save()

    r = _redis()
    _publish(r, 'engagement:poll:latest', 'engagement:poll', _poll_payload(poll))
    return JsonResponse({'ok': True})


@staff_member_required
@require_POST
def poll_close(request, poll_id):
    poll = get_object_or_404(Poll, pk=poll_id)
    poll.status = 'closed'
    poll.save()

    r = _redis()
    payload = {'status': 'closed', 'poll_id': poll.poll_id, 'ts': time.time()}
    _publish(r, 'engagement:poll:latest', 'engagement:poll', payload)
    return JsonResponse({'ok': True})


@require_POST
def poll_vote(request, poll_id):
    if not request.session.session_key:
        request.session.create()

    session_key = request.session.session_key
    dedup_key = f"poll:{poll_id}:session:{session_key}"
    r = _redis()

    if r.exists(dedup_key):
        return JsonResponse({'error': 'already voted'}, status=409)

    poll = get_object_or_404(Poll, pk=poll_id, status='active')
    option_id = request.POST.get('option_id')
    option = get_object_or_404(PollOption, pk=option_id, poll=poll)

    PollOption.objects.filter(pk=option.pk).update(vote_count=F('vote_count') + 1)
    r.set(dedup_key, '1')

    poll.refresh_from_db()
    _publish(r, 'engagement:poll:latest', 'engagement:poll', _poll_payload(poll))
    return JsonResponse({'ok': True})


# ── Feature 10: Fan Vote ─────────────────────────────────────────────────────

def fan_vote_ballot(request):
    if not request.session.session_key:
        request.session.create()

    session_key = request.session.session_key
    event = _active_event()
    categories = list(FanVoteCategory.objects.filter(is_active=True))
    if event:
        categories = [c for c in categories if c.event_id == event.event_id]

    voted_by_cat = {}
    for vote in FanVote.objects.filter(category__in=categories, session_key=session_key).select_related('team'):
        voted_by_cat[vote.category_id] = vote.team

    categories_data = []
    for cat in categories:
        nominees = list(EventTeam.objects.filter(event=cat.event).select_related('team'))
        voted_team = voted_by_cat.get(cat.category_id)
        categories_data.append({
            'category': cat,
            'nominees': nominees,
            'voted_team': voted_team,
        })

    return render(request, 'engagement/vote.html', {
        'categories_data': categories_data,
    })


@require_POST
def fan_vote_cast(request):
    if not request.session.session_key:
        request.session.create()

    session_key = request.session.session_key
    category_id = request.POST.get('category_id')
    team_id = request.POST.get('team_id')

    category = get_object_or_404(FanVoteCategory, pk=category_id, is_active=True)

    team = get_object_or_404(Team, pk=team_id)

    try:
        FanVote.objects.create(category=category, team=team, session_key=session_key)
    except IntegrityError:
        return JsonResponse({'error': 'already voted in this category'}, status=409)

    return JsonResponse({'ok': True})


def fan_vote_results(request):
    event = _active_event()
    categories = FanVoteCategory.objects.filter(is_active=True)
    if event:
        categories = categories.filter(event=event)

    results = []
    for cat in categories:
        ranked = (
            FanVote.objects
            .filter(category=cat)
            .values('team__team_id', 'team__team_name', 'team__team_number')
            .annotate(vote_count=Count('vote_id'))
            .order_by('-vote_count')
        )
        results.append({'category': cat, 'ranked': list(ranked)})

    return render(request, 'engagement/vote_results.html', {'results': results})
