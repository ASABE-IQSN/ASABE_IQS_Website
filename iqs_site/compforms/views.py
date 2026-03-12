from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseForbidden
from django.contrib import messages

from events.models import EventTeam
from users.models import GroupProfile
from .models import (
    CompForm, EventForm, FormResponse, Question, QuestionResponse,
    QuestionGroup, GroupQuestion,
    TeamQuestionAssignment, get_or_create_group_assignments,
)


def _user_on_team(user, team):
    """Return True if user is a member of the given team via GroupProfile."""
    gp = getattr(team, 'group_profile', None)
    if gp is None:
        return False
    return gp.group.user_set.filter(pk=user.pk).exists()


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

    flat_fqs = list(
        event_form.form.form_questions.select_related('question').order_by('order')
    )
    groups = list(event_form.form.question_groups.order_by('order'))

    # Build group assignments (lazy, persisted)
    group_assignments = {
        group.group_id: get_or_create_group_assignments(event_team, group)
        for group in groups
    }

    existing_response = FormResponse.objects.filter(
        event_form=event_form,
        event_team=event_team,
    ).prefetch_related('answers__question').first()

    existing_answers = {}
    if existing_response:
        for ans in existing_response.answers.all():
            existing_answers[ans.question_id] = ans.answer

    # Whitelist of question IDs valid for this team (prevents POST manipulation)
    valid_question_ids = {fq.question.question_id for fq in flat_fqs}
    for qs in group_assignments.values():
        for q in qs:
            valid_question_ids.add(q.question_id)

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
            if key.startswith('question_'):
                try:
                    qid = int(key[len('question_'):])
                except ValueError:
                    continue
                if qid not in valid_question_ids:
                    continue
                QuestionResponse.objects.update_or_create(
                    form_response=form_response,
                    question_id=qid,
                    defaults={'answer': value.strip()},
                )

        messages.success(request, "Your answers have been saved.")
        return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

    # Build merged sections list, interleaved by order value
    sections = []
    for fq in flat_fqs:
        sections.append({
            'type': 'flat',
            'order': fq.order,
            'fq': fq,
            'answer': existing_answers.get(fq.question.question_id, ''),
        })
    for group in groups:
        assigned_questions = group_assignments[group.group_id]
        sections.append({
            'type': 'group',
            'order': group.order,
            'group': group,
            'questions': [
                (q, existing_answers.get(q.question_id, ''))
                for q in assigned_questions
            ],
        })
    sections.sort(key=lambda s: s['order'])

    return render(request, 'compforms/submit_form.html', {
        'event_form': event_form,
        'team': team,
        'sections': sections,
        'existing_response': existing_response,
        'active_page': 'my account',
    })


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

    # All event_teams for this event (to count total)
    all_event_teams = EventTeam.objects.filter(event=event_form.event).select_related('team')
    total_teams = all_event_teams.count()
    submitted_count = responses.count()

    # Batch-load all assignments for this event in one query, indexed by (event_team_id, group_id)
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
        group_rows = [
            {
                'group': group,
                'qa_pairs': [
                    (q, answer_map.get(q.question_id, ''))
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

        return redirect('compforms:form_template', form_id=form_id)

    flat_fqs = list(form.form_questions.select_related('question').order_by('order'))
    groups = list(
        form.question_groups
        .prefetch_related('group_questions__question')
        .order_by('order')
    )

    # Build sections interleaved by order, same logic as submit_form
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
