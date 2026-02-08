from django.conf import settings
from django.contrib.auth.models import Group, User
from django.db import models
from events.models import Team
from datetime import datetime
from django.utils import timezone
class GroupProfile(models.Model):
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    team = models.OneToOneField(
        Team,
        on_delete=models.CASCADE,
        
        db_column="team_id",
        related_name="group_profile",
        null=True,
        blank=True,
        db_constraint=False

    )
    admins = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="admin_team_groups",
        blank=True,
    )

    def __str__(self):
        return f"Profile for group {self.group.name}"
    
class View(models.Model):
    view_id=models.AutoField(primary_key=True)
    user=models.ForeignKey(User,
                            models.DO_NOTHING,
                            db_column="user_id",
                            blank=True,
                            null=True)
    url=models.CharField(max_length=255)
    time=models.DateTimeField(default=timezone.now)
    ip=models.CharField(max_length=45)
    response_time_s=models.FloatField()
    response_code=models.IntegerField()
    class Meta:
        managed = False
        db_table = "views"


class TeamEmail(models.Model):
    """
    Pre-authorized emails for automatic team assignment.
    Users who register with matching emails are automatically added
    as team admins via GroupProfile.admins and as members via Group.user_set.
    """
    team_email_id = models.AutoField(primary_key=True)
    role = models.IntegerField(blank=True, null=True)  # Not currently used
    email = models.EmailField(max_length=255, db_index=True)
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        db_column='team_id',
        related_name='authorized_emails',
    )
    collected = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False  # Existing table, don't let Django manage it
        db_table = 'team_emails'
        indexes = [
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return f"{self.email} → {self.team}"
