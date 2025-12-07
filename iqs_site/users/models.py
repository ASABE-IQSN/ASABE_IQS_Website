from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from events.models import Team

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
