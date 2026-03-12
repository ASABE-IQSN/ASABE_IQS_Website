import random

from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.utils import timezone

from events.models import EventTeam
from users.models import GroupProfile
from .models import (
    CompForm, EventForm, FormResponse, Question, QuestionResponse,
    QuestionGroup, GroupQuestion,
    TeamQuestionAssignment, QuestionSwap,
    MAX_QUESTION_SWAPS, get_or_create_group_assignments,
)


def _user_on_team(user, team):
    """Return True if user is a member of the given team via GroupProfile."""
    gp = getattr(team, 'group_profile', None)
    if gp is None:
        return False
    return gp.group.user_set.filter(pk=user.pk).exists()


def _build_sections(event_form, event_team, existing_answers, flagged_qids):
    """Return merged, order-sorted sections list for submit_form and swap_question."""
    flat_fqs = list(
        event_form.form.form_questions.select_related('question').order_by('order')
    )
    groups = list(event_form.form.question_groups.order_by('order'))

    group_assignments = {
        group.group_id: get_or_create_group_assignments(event_team, group)
        for group in groups
    }

    sections = []
    for fq in flat_fqs:
        sections.append({
            'type': 'flat',
            'order': fq.order,
            'fq': fq,
            'answer': existing_answers.get(fq.question.question_id, ''),
        })
    for group in groups:
        assigned = group_assignments[group.group_id]
        sections.append({
            'type': 'group',
            'order': group.order,
            'group': group,
            'swappable': group.num_assigned > 0,
            'questions': [
                (q, existing_answers.get(q.question_id, ''), flagged_qids.get(q.question_id))
                for q in assigned
            ],
        })
    sections.sort(key=lambda s: s['order'])

    # Also return flat list of valid question IDs for POST whitelisting
    valid_ids = {fq.question.question_id for fq in flat_fqs}
    for qs in group_assignments.values():
        for q in qs:
            valid_ids.add(q.question_id)

    return sections, valid_ids


@login_required
def submit_form(request, event_form_id, team_id):
    event_form = get_object_or_404(
        EventForm.objects.select_related('form', 'event'),
        pk=event_form_id,
    )
    event_team = get_object_or_404(
        EventTeam.objects.select_related('team', 'event'),
        event=event_form.event,
        team_id=team_id,
    )
    team = event_team.team

    if not _user_on_team(request.user, team):
        return HttpResponseForbidden("You are not a member of this team.")

    existing_response = FormResponse.objects.filter(
        event_form=event_form,
        event_team=event_team,
    ).prefetch_related('answers__question').first()

    existing_answers = {}
    flagged_qids = {}  # {question_id: flag_reason}
    if existing_response:
        for ans in existing_response.answers.all():
            existing_answers[ans.question_id] = ans.answer
            if ans.flagged:
                flagged_qids[ans.question_id] = ans.flag_reason

    sections, valid_question_ids = _build_sections(
        event_form, event_team, existing_answers, flagged_qids
    )

    if request.method == 'POST':
        if not event_form.is_open:
            messages.error(request, "This form is closed and can no longer be edited.")
            return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

        form_response, _ = FormResponse.objects.get_or_create(
            event_form=event_form,
            event_team=event_team,
        )
        form_response.submitted_by = request.user
        form_response.save()

        for key, value in request.POST.items():
            if not key.startswith('question_'):
                continue
            try:
                qid = int(key[len('question_'):])
            except ValueError:
                continue
            if qid not in valid_question_ids:
                continue
            qr, _ = QuestionResponse.objects.update_or_create(
                form_response=form_response,
                question_id=qid,
                defaults={'answer': value.strip()},
            )
            # Re-answering a flagged question auto-clears the flag
            if qr.flagged:
                qr.flagged = False
                qr.flagged_by = None
                qr.flagged_at = None
                qr.flag_reason = ''
                qr.save(update_fields=['flagged', 'flagged_by', 'flagged_at', 'flag_reason'])

        messages.success(request, "Your answers have been saved.")
        return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

    swaps_used = QuestionSwap.objects.filter(
        event_team=event_team,
        event_form=event_form,
        is_flag_driven=False,
    ).count()
    swaps_remaining = MAX_QUESTION_SWAPS - swaps_used

    return render(request, 'compforms/submit_form.html', {
        'event_form': event_form,
        'team': team,
        'sections': sections,
        'existing_response': existing_response,
        'swaps_remaining': swaps_remaining,
        'swaps_remaining_after': max(swaps_remaining - 1, 0),
        'max_swaps': MAX_QUESTION_SWAPS,
        'has_flagged': bool(flagged_qids),
        'active_page': 'my account',
    })


@login_required
def swap_question(request, event_form_id, team_id):
    if request.method != 'POST':
        return HttpResponseForbidden()

    event_form = get_object_or_404(
        EventForm.objects.select_related('form', 'event'),
        pk=event_form_id,
    )
    event_team = get_object_or_404(
        EventTeam.objects.select_related('team', 'event'),
        event=event_form.event,
        team_id=team_id,
    )

    if not _user_on_team(request.user, event_team.team):
        return HttpResponseForbidden("You are not a member of this team.")

    if not event_form.is_open:
        messages.error(request, "This form is closed.")
        return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

    try:
        group_id = int(request.POST.get('group_id', ''))
        old_question_id = int(request.POST.get('question_id', ''))
    except (ValueError, TypeError):
        messages.error(request, "Invalid request.")
        return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

    group = get_object_or_404(QuestionGroup, pk=group_id, form=event_form.form)

    if group.num_assigned == 0:
        messages.error(request, "This section does not support question swaps.")
        return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

    try:
        current_assignment = TeamQuestionAssignment.objects.get(
            event_team=event_team, group=group, question_id=old_question_id
        )
    except TeamQuestionAssignment.DoesNotExist:
        messages.error(request, "That question is not in your current assignment.")
        return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

    # Determine server-side whether this is flag-driven (team cannot lie via POST data)
    is_flag_driven = QuestionResponse.objects.filter(
        form_response__event_form=event_form,
        form_response__event_team=event_team,
        question_id=old_question_id,
        flagged=True,
    ).exists()

    if not is_flag_driven:
        swaps_used = QuestionSwap.objects.filter(
            event_team=event_team, event_form=event_form, is_flag_driven=False
        ).count()
        if swaps_used >= MAX_QUESTION_SWAPS:
            messages.error(request, f"You have used all {MAX_QUESTION_SWAPS} question swaps for this form.")
            return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

    # Pool = all group questions minus currently assigned minus previously swapped-away
    currently_assigned_ids = set(
        TeamQuestionAssignment.objects.filter(event_team=event_team, group=group)
        .values_list('question_id', flat=True)
    )
    previously_swapped_away_ids = set(
        QuestionSwap.objects.filter(event_team=event_team, group=group)
        .values_list('old_question_id', flat=True)
    )
    excluded = currently_assigned_ids | previously_swapped_away_ids

    available = list(
        GroupQuestion.objects.filter(group=group)
        .exclude(question_id__in=excluded)
        .select_related('question')
    )

    if not available:
        messages.error(request, "There are no more available questions in this section to swap in.")
        return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

    new_gq = random.choice(available)

    from django.db import transaction
    with transaction.atomic():
        current_assignment.question = new_gq.question
        current_assignment.save(update_fields=['question'])

        QuestionSwap.objects.create(
            event_team=event_team,
            event_form=event_form,
            group=group,
            old_question_id=old_question_id,
            new_question=new_gq.question,
            swapped_by=request.user,
            is_flag_driven=is_flag_driven,
        )

        # Delete the old answer (and its flag, if any)
        QuestionResponse.objects.filter(
            form_response__event_form=event_form,
            form_response__event_team=event_team,
            question_id=old_question_id,
        ).delete()

    messages.success(request, "You have a new question. Your previous answer was cleared.")
    return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)


@staff_member_required
def form_responses_overview(request, event_form_id):
    event_form = get_object_or_404(
        EventForm.objects.select_related('form', 'event'),
        pk=event_form_id,
    )

    questions = list(
        event_form.form.form_questions.select_related('question').order_by('order')
    )
    question_objs = [fq.question for fq in questions]

    groups = list(event_form.form.question_groups.prefetch_related('group_questions__question').order_by('order'))

    responses = (
        FormResponse.objects
        .filter(event_form=event_form)
        .select_related('event_team__team')
        .prefetch_related('answers__question')
    )

    all_event_teams = EventTeam.objects.filter(event=event_form.event).select_related('team')
    total_teams = all_event_teams.count()
    submitted_count = responses.count()

    event_team_ids = [r.event_team_id for r in responses]
    all_assignments = (
        TeamQuestionAssignment.objects
        .filter(event_team_id__in=event_team_ids, group__in=groups)
        .select_related('question', 'group')
        .order_by('group', 'display_order')
    )
    assignment_index = {}
    for a in all_assignments:
        key = (a.event_team_id, a.group_id)
        assignment_index.setdefault(key, []).append(a.question)

    response_matrix = []
    for resp in responses:
        answer_map = {ans.question_id: ans.answer for ans in resp.answers.all()}
        flagged_map = {ans.question_id: ans for ans in resp.answers.all() if ans.flagged}
        group_rows = [
            {
                'group': group,
                'qa_pairs': [
                    (q, answer_map.get(q.question_id, ''), flagged_map.get(q.question_id))
                    for q in assignment_index.get((resp.event_team_id, group.group_id), [])
                ],
            }
            for group in groups
        ]
        row = {
            'team': resp.event_team.team,
            'event_team': resp.event_team,
            'response': resp,
            'answers': [answer_map.get(q.question_id, '') for q in question_objs],
            'group_rows': group_rows,
            'has_flagged': bool(flagged_map),
        }
        response_matrix.append(row)

    return render(request, 'compforms/form_responses_overview.html', {
        'event_form': event_form,
        'questions': question_objs,
        'groups': groups,
        'response_matrix': response_matrix,
        'submitted_count': submitted_count,
        'total_teams': total_teams,
    })


@staff_member_required
def review_response(request, event_form_id, response_id):
    event_form = get_object_or_404(
        EventForm.objects.select_related('form', 'event'),
        pk=event_form_id,
    )
    form_response = get_object_or_404(
        FormResponse.objects.select_related('event_team__team'),
        pk=response_id,
        event_form=event_form,
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        qr_id = request.POST.get('question_response_id')
        qr = get_object_or_404(QuestionResponse, pk=qr_id, form_response=form_response)

        if action == 'flag':
            qr.flagged = True
            qr.flagged_by = request.user
            qr.flagged_at = timezone.now()
            qr.flag_reason = request.POST.get('reason', '').strip()
            qr.save(update_fields=['flagged', 'flagged_by', 'flagged_at', 'flag_reason'])
            messages.success(request, "Response flagged.")
        elif action == 'unflag':
            qr.flagged = False
            qr.flagged_by = None
            qr.flagged_at = None
            qr.flag_reason = ''
            qr.save(update_fields=['flagged', 'flagged_by', 'flagged_at', 'flag_reason'])
            messages.success(request, "Flag removed.")

        return redirect('compforms:review_response', event_form_id=event_form_id, response_id=response_id)

    # Build ordered sections of (question, answer_obj) pairs using same ordering as the form
    flat_fqs = list(
        event_form.form.form_questions.select_related('question').order_by('order')
    )
    groups = list(
        event_form.form.question_groups
        .order_by('order')
    )
    assigned_map = {}
    for a in TeamQuestionAssignment.objects.filter(
        event_team=form_response.event_team, group__in=groups
    ).select_related('question', 'group').order_by('group', 'display_order'):
        assigned_map.setdefault(a.group_id, []).append(a.question)

    answer_obj_map = {ans.question_id: ans for ans in form_response.answers.select_related('question', 'flagged_by').all()}

    sections = []
    for fq in flat_fqs:
        sections.append({
            'type': 'flat',
            'order': fq.order,
            'fq': fq,
            'answer_obj': answer_obj_map.get(fq.question.question_id),
        })
    for group in groups:
        assigned = assigned_map.get(group.group_id, [])
        sections.append({
            'type': 'group',
            'order': group.order,
            'group': group,
            'qa_pairs': [
                (q, answer_obj_map.get(q.question_id))
                for q in assigned
            ],
        })
    sections.sort(key=lambda s: s['order'])

    swaps = QuestionSwap.objects.filter(
        event_team=form_response.event_team,
        event_form=event_form,
    ).select_related('group', 'old_question', 'new_question', 'swapped_by').order_by('swapped_at')

    return render(request, 'compforms/review_response.html', {
        'event_form': event_form,
        'form_response': form_response,
        'team': form_response.event_team.team,
        'sections': sections,
        'swaps': swaps,
    })


@staff_member_required
def form_template(request, form_id):
    form = get_object_or_404(CompForm, pk=form_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_question_to_group':
            group_id = request.POST.get('group_id')
            question_text = request.POST.get('question_text', '').strip()
            question_type = request.POST.get('question_type', Question.LONG_TEXT)
            group = get_object_or_404(QuestionGroup, pk=group_id, form=form)

            if not question_text:
                messages.error(request, "Question text cannot be empty.")
            elif question_type not in (Question.SHORT_TEXT, Question.LONG_TEXT):
                messages.error(request, "Invalid question type.")
            else:
                next_order = (
                    GroupQuestion.objects.filter(group=group)
                    .order_by('-display_order')
                    .values_list('display_order', flat=True)
                    .first() or 0
                ) + 1
                q = Question.objects.create(
                    question_text=question_text,
                    question_type=question_type,
                )
                GroupQuestion.objects.create(
                    group=group,
                    question=q,
                    display_order=next_order,
                )
                messages.success(request, f'Question added to "{group.name}".')

        elif action == 'edit_question':
            question_id = request.POST.get('question_id')
            question_text = request.POST.get('question_text', '').strip()
            question_type = request.POST.get('question_type', Question.LONG_TEXT)
            q = get_object_or_404(Question, pk=question_id)
            # Verify it belongs to this form (flat or group) — prevents editing arbitrary questions
            on_form = (
                FormQuestion.objects.filter(form=form, question=q).exists()
                or GroupQuestion.objects.filter(group__form=form, question=q).exists()
            )
            if not on_form:
                messages.error(request, "Question not found on this form.")
            elif not question_text:
                messages.error(request, "Question text cannot be empty.")
            elif question_type not in (Question.SHORT_TEXT, Question.LONG_TEXT):
                messages.error(request, "Invalid question type.")
            else:
                q.question_text = question_text
                q.question_type = question_type
                q.save(update_fields=['question_text', 'question_type'])
                messages.success(request, "Question updated.")

        elif action == 'delete_flat_question':
            fq = get_object_or_404(FormQuestion, pk=request.POST.get('form_question_id'), form=form)
            fq.delete()
            messages.success(request, "Question removed from form.")

        elif action == 'delete_group_question':
            gq = get_object_or_404(GroupQuestion, pk=request.POST.get('group_question_id'), group__form=form)
            gq.delete()
            messages.success(request, "Question removed from group.")

        return redirect('compforms:form_template', form_id=form_id)

    flat_fqs = list(form.form_questions.select_related('question').order_by('order'))
    groups = list(
        form.question_groups
        .prefetch_related('group_questions__question')
        .order_by('order')
    )

    sections = []
    for fq in flat_fqs:
        sections.append({'type': 'flat', 'order': fq.order, 'fq': fq})
    for group in groups:
        gqs = list(group.group_questions.select_related('question').order_by('display_order'))
        n = group.num_assigned
        shown = n if (n > 0 and n < len(gqs)) else len(gqs)
        sections.append({
            'type': 'group',
            'order': group.order,
            'group': group,
            'group_questions': gqs,
            'shown': shown,
        })
    sections.sort(key=lambda s: s['order'])

    return render(request, 'compforms/form_template.html', {
        'form': form,
        'sections': sections,
        'SHORT_TEXT': Question.SHORT_TEXT,
        'LONG_TEXT': Question.LONG_TEXT,
    })
