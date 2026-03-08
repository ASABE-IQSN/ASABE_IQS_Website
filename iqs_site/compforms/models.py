from django.db import models
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

    class Meta:
        unique_together = ('form_response', 'question')

    def __str__(self):
        return f"Answer to '{self.question}': {self.answer[:50]}"
