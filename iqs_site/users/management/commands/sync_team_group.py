from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from events.models import Team
from users.models import GroupProfile  # adjust app name

class Command(BaseCommand):
    help = "Ensure each Team has an associated Group and GroupProfile"

    def handle(self, *args, **options):
        created_count = 0

        for team in Team.objects.all():
            if hasattr(team, "group_profile"):
                continue  # already has one

            # Create a group name that's stable & unique
            group_name = f"team_{team.pk}_{team.team_name}".replace(" ", "_")

            group, _ = Group.objects.get_or_create(name=group_name)
            GroupProfile.objects.create(group=group, team=team)
            created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Synced groups for teams. Created {created_count} new group profiles."
        ))