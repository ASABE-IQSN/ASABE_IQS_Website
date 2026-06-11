"""Export an event's hooks / pulls / runs to JSON for the desktop video clipper.

The clipper GUI (tools/video_clipper/clipper.py) runs on a workstation with no
DB access. This command dumps the dropdown data it needs so that tagging a clip
resolves to a concrete performance event (pull / durability / maneuverability).

Usage:
    python manage.py export_event_clips <event_id> [--out event.json]

Output schema (consumed by clipper.EventData):
    {
      "event_id": 12,
      "event_name": "...",
      "hooks": [
        {"hook_id": 3, "hook_name": "Super Stock",
         "pulls": [{"pull_id": 4581, "run_order": 1,
                    "team_number": "5", "team_name": "Iowa State",
                    "team_abbreviation": "ISU"}]}
      ],
      "durability_runs": [{"durability_run_id": 88, "run_order": 1,
                           "team_number": "...", "team_name": "...",
                           "team_abbreviation": "..."}],
      "maneuverability_runs": [{"maneuverability_run_id": 90, ...}]
    }
"""

import json
import sys

from django.core.management.base import BaseCommand, CommandError

from events.models import Event, Hook, Pull, DurabilityRun, ManeuverabilityRun


def _team_fields(team):
    if team is None:
        return {"team_number": None, "team_name": None, "team_abbreviation": None}
    return {
        "team_number": team.team_number,
        "team_name": team.team_name,
        "team_abbreviation": team.team_abbreviation,
    }


class Command(BaseCommand):
    help = "Export an event's hooks/pulls/runs to JSON for the video clipper."

    def add_arguments(self, parser):
        parser.add_argument("event_id", type=int)
        parser.add_argument(
            "--out",
            help="output file path (default: stdout)",
        )

    def handle(self, *args, **options):
        event_id = options["event_id"]
        try:
            event = Event.objects.get(event_id=event_id)
        except Event.DoesNotExist:
            raise CommandError(f"Event {event_id} not found")

        hooks = []
        hook_qs = Hook.objects.filter(event=event).order_by("hook_id")
        for hook in hook_qs:
            pulls = (
                Pull.objects.filter(hook=hook)
                .select_related("team")
                .order_by("run_order")
            )
            hooks.append({
                "hook_id": hook.hook_id,
                "hook_name": hook.hook_name,
                "pulls": [
                    {"pull_id": p.pull_id, "run_order": p.run_order, **_team_fields(p.team)}
                    for p in pulls
                ],
            })

        durability_runs = [
            {"durability_run_id": r.durability_run_id, "run_order": r.run_order,
             **_team_fields(r.team)}
            for r in DurabilityRun.objects.filter(event=event)
            .select_related("team").order_by("run_order")
        ]
        maneuverability_runs = [
            {"maneuverability_run_id": r.maneuverability_run_id, "run_order": r.run_order,
             **_team_fields(r.team)}
            for r in ManeuverabilityRun.objects.filter(event=event)
            .select_related("team").order_by("run_order")
        ]

        payload = {
            "event_id": event.event_id,
            "event_name": event.event_name,
            "hooks": hooks,
            "durability_runs": durability_runs,
            "maneuverability_runs": maneuverability_runs,
        }

        text = json.dumps(payload, indent=2)
        if options.get("out"):
            with open(options["out"], "w") as f:
                f.write(text)
            self.stdout.write(self.style.SUCCESS(
                f"Wrote {options['out']}: {len(hooks)} hook(s), "
                f"{len(durability_runs)} durability, "
                f"{len(maneuverability_runs)} maneuverability run(s)."
            ))
        else:
            sys.stdout.write(text + "\n")
