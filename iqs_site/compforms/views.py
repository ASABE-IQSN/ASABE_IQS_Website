from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseForbidden
from django.contrib import messages

from events.models import EventTeam
from users.models import GroupProfile
from .models import EventForm, FormResponse, QuestionResponse


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

    questions = list(
        event_form.form.form_questions.select_related('question').order_by('order')
    )

    existing_response = FormResponse.objects.filter(
        event_form=event_form,
        event_team=event_team,
    ).prefetch_related('answers__question').first()

    existing_answers = {}
    if existing_response:
        for ans in existing_response.answers.all():
            existing_answers[ans.question_id] = ans.answer

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

        for fq in questions:
            q = fq.question
            answer_text = request.POST.get(f'question_{q.question_id}', '').strip()
            QuestionResponse.objects.update_or_create(
                form_response=form_response,
                question=q,
                defaults={'answer': answer_text},
            )

        messages.success(request, "Your answers have been saved.")
        return redirect('compforms:submit_form', event_form_id=event_form_id, team_id=team_id)

    # Pair each FormQuestion with its current answer for easy template rendering
    question_rows = [
        (fq, existing_answers.get(fq.question.question_id, ''))
        for fq in questions
    ]

    return render(request, 'compforms/submit_form.html', {
        'event_form': event_form,
        'team': team,
        'question_rows': question_rows,
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

    response_matrix = []
    for resp in responses:
        answer_map = {ans.question_id: ans.answer for ans in resp.answers.all()}
        row = {
            'team': resp.event_team.team,
            'event_team': resp.event_team,
            'response': resp,
            'answers': [answer_map.get(q.question_id, '') for q in question_objs],
        }
        response_matrix.append(row)

    return render(request, 'compforms/form_responses_overview.html', {
        'event_form': event_form,
        'questions': question_objs,
        'response_matrix': response_matrix,
        'submitted_count': submitted_count,
        'total_teams': total_teams,
    })
