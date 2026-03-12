import random

from django.db import models, transaction
from django.contrib.auth import get_user_model


class Question(models.Model):
    SHORT_TEXT = 'SHORT_TEXT'
    LONG_TEXT = 'LONG_TEXT'
    QUESTION_TYPE_CHOICES = [
        (SHORT_TEXT, 'Short Text'),
        (LONG_TEXT, 'Long Text'),
    ]

    question_id = models.AutoField(primary_key=True)
    question_text = models.TextField()
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default=LONG_TEXT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question_text[:80]


class CompForm(models.Model):
    form_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    questions = models.ManyToManyField(
        Question,
        through='FormQuestion',
        related_name='forms',
    )

    def __str__(self):
        return self.name


class FormQuestion(models.Model):
    form_question_id = models.AutoField(primary_key=True)
    form = models.ForeignKey(
        CompForm,
        on_delete=models.CASCADE,
        related_name='form_questions',
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='form_questions',
    )
    order = models.PositiveIntegerField()
    required = models.BooleanField(default=True)

    class Meta:
        unique_together = ('form', 'question')
        ordering = ['order']

    def __str__(self):
        return f"{self.form} – Q{self.order}: {self.question}"


class EventForm(models.Model):
    event_form_id = models.AutoField(primary_key=True)
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.DO_NOTHING,
        related_name='event_forms',
    )
    form = models.ForeignKey(
        CompForm,
        on_delete=models.DO_NOTHING,
        related_name='event_forms',
    )
    is_open = models.BooleanField(default=True)

    class Meta:
        unique_together = ('event', 'form')

    def __str__(self):
        return f"{self.form.name} — {self.event}"


class FormResponse(models.Model):
    response_id = models.AutoField(primary_key=True)
    event_form = models.ForeignKey(
        EventForm,
        on_delete=models.CASCADE,
        related_name='responses',
    )
    event_team = models.ForeignKey(
        'events.EventTeam',
        on_delete=models.DO_NOTHING,
        related_name='form_responses',
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='form_responses_submitted',
    )

    class Meta:
        unique_together = ('event_form', 'event_team')

    def __str__(self):
        return f"Response {self.response_id} – {self.event_team}"


class QuestionResponse(models.Model):
    question_response_id = models.AutoField(primary_key=True)
    form_response = models.ForeignKey(
        FormResponse,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.DO_NOTHING,
        related_name='answers',
    )
    answer = models.TextField(blank=True)
    flagged = models.BooleanField(default=False)
    flagged_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='flagged_responses',
    )
    flagged_at = models.DateTimeField(null=True, blank=True)
    flag_reason = models.TextField(blank=True)

    class Meta:
        unique_together = ('form_response', 'question')

    def __str__(self):
        return f"Answer to '{self.question}': {self.answer[:50]}"


class QuestionGroup(models.Model):
    group_id = models.AutoField(primary_key=True)
    form = models.ForeignKey(CompForm, on_delete=models.CASCADE, related_name='question_groups')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    num_assigned = models.PositiveIntegerField(
        default=0,
        help_text="Questions randomly assigned per team. 0 = show all.",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Shared namespace with FormQuestion.order — controls interleave order on form.",
    )

    class Meta:
        ordering = ['order']
        unique_together = ('form', 'name')

    def __str__(self):
        return f"{self.form} — Group: {self.name}"


class GroupQuestion(models.Model):
    group_question_id = models.AutoField(primary_key=True)
    group = models.ForeignKey(QuestionGroup, on_delete=models.CASCADE, related_name='group_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='group_questions')
    display_order = models.PositiveIntegerField(default=0)
    required = models.BooleanField(default=True)

    class Meta:
        unique_together = ('group', 'question')
        ordering = ['display_order']

    def __str__(self):
        return f"{self.group.name} — {self.question}"


class TeamQuestionAssignment(models.Model):
    assignment_id = models.AutoField(primary_key=True)
    event_team = models.ForeignKey(
        'events.EventTeam', on_delete=models.CASCADE, related_name='question_assignments'
    )
    group = models.ForeignKey(QuestionGroup, on_delete=models.CASCADE, related_name='assignments')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='team_assignments')
    display_order = models.PositiveIntegerField()

    class Meta:
        unique_together = ('event_team', 'group', 'question')
        ordering = ['group', 'display_order']
        indexes = [models.Index(fields=['event_team', 'group'])]

    def __str__(self):
        return f"{self.event_team} — {self.group.name} — {self.question}"


MAX_QUESTION_SWAPS = 5


class QuestionSwap(models.Model):
    swap_id = models.AutoField(primary_key=True)
    event_team = models.ForeignKey(
        'events.EventTeam', on_delete=models.CASCADE, related_name='question_swaps'
    )
    event_form = models.ForeignKey(
        EventForm, on_delete=models.CASCADE, related_name='question_swaps'
    )
    group = models.ForeignKey(QuestionGroup, on_delete=models.CASCADE, related_name='swaps')
    old_question = models.ForeignKey(
        Question, on_delete=models.DO_NOTHING, related_name='swapped_away_from'
    )
    new_question = models.ForeignKey(
        Question, on_delete=models.DO_NOTHING, related_name='swapped_in_to'
    )
    swapped_at = models.DateTimeField(auto_now_add=True)
    swapped_by = models.ForeignKey(
        get_user_model(), on_delete=models.SET_NULL, null=True, blank=True,
        related_name='initiated_swaps',
    )
    is_flag_driven = models.BooleanField(
        default=False,
        help_text="True when swap was triggered by a staff-flagged response. Does not count against team limit.",
    )

    class Meta:
        ordering = ['-swapped_at']

    def __str__(self):
        return f"{self.event_team} swapped Q{self.old_question_id} → Q{self.new_question_id}"


def get_or_create_group_assignments(event_team, question_group):
    """Return list of Questions assigned to event_team for question_group, creating rows if needed."""
    existing = list(
        TeamQuestionAssignment.objects
        .filter(event_team=event_team, group=question_group)
        .select_related('question').order_by('display_order')
    )
    if existing:
        return [a.question for a in existing]

    with transaction.atomic():
        locked = (
            TeamQuestionAssignment.objects
            .select_for_update()
            .filter(event_team=event_team, group=question_group)
        )
        if locked.exists():
            return [a.question for a in locked.order_by('display_order').select_related('question')]

        bank = list(
            GroupQuestion.objects.filter(group=question_group)
            .select_related('question').order_by('display_order')
        )
        n = question_group.num_assigned
        selected = bank if (n == 0 or n >= len(bank)) else random.sample(bank, n)

        to_create = [
            TeamQuestionAssignment(
                event_team=event_team,
                group=question_group,
                question=gq.question,
                display_order=i,
            )
            for i, gq in enumerate(selected, start=1)
        ]
        TeamQuestionAssignment.objects.bulk_create(to_create)
        return [a.question for a in to_create]
