from django.db import models
from django.conf import settings


class CrowdSubmission(models.Model):
    SUBMISSION_TYPES = [('comment', 'Comment'), ('photo', 'Photo')]
    STATUS_CHOICES = [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]

    submission_id = models.AutoField(primary_key=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='crowd_submissions',
    )
    submission_type = models.CharField(max_length=10, choices=SUBMISSION_TYPES)
    text = models.TextField(blank=True)
    photo = models.ImageField(upload_to='engagement/submissions/', null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_crowd_submissions',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'engagement_crowd_submissions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.submission_type} by {self.submitted_by} ({self.status})"


class ReactionAggregate(models.Model):
    EMOJI_CHOICES = [('fire', '🔥'), ('clap', '👏'), ('wow', '😮'), ('tractor', '🚜')]

    aggregate_id = models.AutoField(primary_key=True)
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='reaction_aggregates')
    emoji = models.CharField(max_length=10, choices=EMOJI_CHOICES)
    count = models.PositiveBigIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'engagement_reaction_aggregates'
        unique_together = [('event', 'emoji')]

    def __str__(self):
        return f"{self.emoji} on Event {self.event_id}: {self.count}"


class Poll(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('active', 'Active'), ('closed', 'Closed')]

    poll_id = models.AutoField(primary_key=True)
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    question = models.CharField(max_length=500)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'engagement_polls'

    def __str__(self):
        return f"Poll: {self.question[:60]} ({self.status})"


class PollOption(models.Model):
    option_id = models.AutoField(primary_key=True)
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
    option_text = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)
    vote_count = models.PositiveBigIntegerField(default=0)

    class Meta:
        db_table = 'engagement_poll_options'
        ordering = ['order']

    def __str__(self):
        return f"{self.option_text} ({self.vote_count} votes)"


class FanVoteCategory(models.Model):
    category_id = models.AutoField(primary_key=True)
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='fan_vote_categories')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'engagement_fan_vote_categories'

    def __str__(self):
        return f"{self.name} (Event {self.event_id})"


class FanVote(models.Model):
    vote_id = models.AutoField(primary_key=True)
    category = models.ForeignKey(FanVoteCategory, on_delete=models.CASCADE, related_name='votes')
    team = models.ForeignKey('events.Team', on_delete=models.CASCADE, db_constraint=False)
    session_key = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'engagement_fan_votes'
        unique_together = [('category', 'session_key')]
        indexes = [
            models.Index(fields=['category', 'team']),
        ]

    def __str__(self):
        return f"Vote for Team {self.team_id} in {self.category}"
