"""
Import 2010 IQS results from historical score sheets.

Category max points:
  Written Design: 500  Oral Presentation: 500  Design Judging: 420
  Tractor Pull:   800  Maneuverability:   100  Weight-In Bonus: 100
  (No Durability category in 2010.)

21 teams competed. 4-hook pull (1050 lb #1, 1050 lb #2, 1550 lb #1, 1550 lb #2),
200 pts/hook. Pull distances were not recorded in the score sheets.

Usage:
    python manage.py import_2010_results              # dry-run
    python manage.py import_2010_results --commit     # write to DB
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from events.models import (
    Event, Team, EventTeam,
    ScoreCategory, ScoreCategoryInstance, ScoreCategoryScore,
)
from events.management.commands.import_scores import NAME_ALIASES

EXTRA_ALIASES = {
    "the ohio state university": "ohio state",
    "ohio state university, the": "ohio state",
    "ohio state university": "ohio state",
    "california polytechnic state university": "cal poly state university",
    "cal poly san luis obispo": "cal poly state university",
    "texas a & m university": "texas a&m university",
    "michigan state university": "michigan state",
    "mississippi state university": "mississippi state",
    "illinois, university of": "university of illinois",
    "kentucky, university of": "university of kentucky",
    "laval, université": "université laval",
    "manitoba, university of": "university of manitoba",
    "minnesota, university of": "university of minnesota",
    "missouri, university of": "university of missouri",
    "nebraska, university of": "university of nebraska",
    "saskatchawen, university of": "university of saskatchewan",
    "wisconsin - madison, university of": "university of wisconsin-madison",
    "wisconsin - platteville, university of": "university of wisconsin-platteville",
    "wisconsin - river falls, university of": "university of wisconsin - river falls",
}

CATEGORIES = [
    ("Weight-In Bonus",   100, 1),
    ("Design Judging",    420, 2),
    ("Written Design",    500, 3),
    ("Oral Presentation", 500, 5),
    ("Tractor Pull",      800, 6),
    ("Maneuverability",   100, 7),
]

SCORES = {
    "cal poly state university": {
        "Written Design": 479, "Oral Presentation": 495, "Design Judging": 317,
        "Tractor Pull": 68, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of illinois": {
        "Written Design": 466, "Oral Presentation": 478, "Design Judging": 334,
        "Tractor Pull": 800, "Maneuverability": 99, "Weight-In Bonus": 100,
    },
    "iowa state university": {
        "Written Design": 494, "Oral Presentation": 463, "Design Judging": 331,
        "Tractor Pull": 0, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of kentucky": {
        "Written Design": 468, "Oral Presentation": 427, "Design Judging": 371,
        "Tractor Pull": 761, "Maneuverability": 92, "Weight-In Bonus": 100,
    },
    "université laval": {
        "Written Design": 493, "Oral Presentation": 496, "Design Judging": 410,
        "Tractor Pull": 274, "Maneuverability": 93, "Weight-In Bonus": 100,
    },
    "university of manitoba": {
        "Written Design": 357, "Oral Presentation": 419, "Design Judging": 275,
        "Tractor Pull": 515, "Maneuverability": 92, "Weight-In Bonus": 0,
    },
    "university of minnesota": {
        "Written Design": 484, "Oral Presentation": 442, "Design Judging": 328,
        "Tractor Pull": 596, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "modesto junior college": {
        "Written Design": 498, "Oral Presentation": 479, "Design Judging": 323,
        "Tractor Pull": 435, "Maneuverability": 91, "Weight-In Bonus": 100,
    },
    "north carolina state university": {
        "Written Design": 400, "Oral Presentation": 441, "Design Judging": 282,
        "Tractor Pull": 596, "Maneuverability": 71, "Weight-In Bonus": 100,
    },
    "university of nebraska": {
        "Written Design": 500, "Oral Presentation": 484, "Design Judging": 352,
        "Tractor Pull": 707, "Maneuverability": 100, "Weight-In Bonus": 0,
    },
    "nicholls state university": {
        "Written Design": 450, "Oral Presentation": 468, "Design Judging": 361,
        "Tractor Pull": 733, "Maneuverability": 88, "Weight-In Bonus": 100,
    },
    "north dakota state university": {
        "Written Design": 423, "Oral Presentation": 348, "Design Judging": 420,
        "Tractor Pull": 332, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "ohio state": {
        "Written Design": 494, "Oral Presentation": 409, "Design Judging": 276,
        "Tractor Pull": 394, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "oklahoma state university": {
        "Written Design": 446, "Oral Presentation": 420, "Design Judging": 351,
        "Tractor Pull": 588, "Maneuverability": 95, "Weight-In Bonus": 100,
    },
    "penn state university": {
        "Written Design": 482, "Oral Presentation": 434, "Design Judging": 328,
        "Tractor Pull": 468, "Maneuverability": 91, "Weight-In Bonus": 100,
    },
    "purdue": {
        "Written Design": 492, "Oral Presentation": 463, "Design Judging": 354,
        "Tractor Pull": 691, "Maneuverability": 88, "Weight-In Bonus": 100,
    },
    "university of saskatchewan": {
        "Written Design": 494, "Oral Presentation": 452, "Design Judging": 400,
        "Tractor Pull": 649, "Maneuverability": 96, "Weight-In Bonus": 100,
    },
    "texas a&m university": {
        "Written Design": 465, "Oral Presentation": 427, "Design Judging": 287,
        "Tractor Pull": 557, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of wisconsin-madison": {
        "Written Design": 441, "Oral Presentation": 452, "Design Judging": 367,
        "Tractor Pull": 528, "Maneuverability": 96, "Weight-In Bonus": 100,
    },
    "university of wisconsin-platteville": {
        "Written Design": 384, "Oral Presentation": 322, "Design Judging": 277,
        "Tractor Pull": 611, "Maneuverability": 96, "Weight-In Bonus": 100,
    },
    "university of wisconsin - river falls": {
        "Written Design": 434, "Oral Presentation": 500, "Design Judging": 387,
        "Tractor Pull": 364, "Maneuverability": 84, "Weight-In Bonus": 100,
    },
}


class Command(BaseCommand):
    help = "Import 2010 IQS historical results (hardcoded from score sheets)."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, default=10, help="Event id (default 10)")
        parser.add_argument("--commit", action="store_true", help="Write to DB (default: dry-run)")

    def handle(self, *args, **opts):
        event_id = opts["event"]
        commit = opts["commit"]

        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            raise CommandError(f"Event {event_id} not found.")

        aliases = {**NAME_ALIASES, **EXTRA_ALIASES}
        teams_by_name = {t.team_name.strip().lower(): t for t in Team.objects.all()}

        plan = {cat_name: {} for cat_name, _, _ in CATEGORIES}
        unmatched = []

        for db_name_lower, cat_scores in SCORES.items():
            team = teams_by_name.get(db_name_lower)
            if team is None:
                unmatched.append(db_name_lower)
                continue
            for cat_name, score in cat_scores.items():
                plan[cat_name][team] = score

        mode = "COMMIT" if commit else "DRY-RUN (no DB writes)"
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"import_2010_results — event {event_id} ({event}) — {mode}"))
        self.stdout.write("\n--- Category scores ---")
        for cat_name, max_pts, _ in CATEGORIES:
            self.stdout.write(f"  {cat_name:<20} max={max_pts:>4}  teams={len(plan[cat_name]):>2}")

        if unmatched:
            self.stdout.write(self.style.WARNING(f"\nUnmatched DB names: {unmatched}"))

        if not commit:
            self.stdout.write(self.style.NOTICE(
                "\nDRY-RUN complete. No DB changes. Re-run with --commit to write."))
            return

        with transaction.atomic():
            for cat_name, max_pts, display_order in CATEGORIES:
                cat, _ = ScoreCategory.objects.get_or_create(category_name=cat_name)
                inst, _ = ScoreCategoryInstance.objects.update_or_create(
                    event=event, score_category=cat,
                    defaults={"max_points": max_pts, "released": True,
                              "display_order": display_order})
                for team, score in plan[cat_name].items():
                    ScoreCategoryScore.objects.update_or_create(
                        team=team, category_instance=inst, defaults={"score": score})

            updated = 0
            for et in EventTeam.objects.filter(event=event).select_related("team"):
                total = sum(
                    cs.score for cs in ScoreCategoryScore.objects.filter(
                        team=et.team, category_instance__event=event)
                    if cs.score is not None)
                et.total_score = round(total, 2)
                et.save(update_fields=["total_score"])
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nCOMMIT complete: scores written for {len(SCORES)} teams, "
            f"{updated} EventTeam totals recomputed."))
