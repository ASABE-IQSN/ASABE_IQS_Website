"""
Import 2015 IQS results from historical score sheets.

Category max points:
  Written Design: 500  Oral Presentation: 500  Design Judging: 420
  Tractor Pull:   600  Durability:        200  Maneuverability: 100
  Weight-In Bonus: 100

28 teams competed. 3-hook pull (1000 lb #1, 1000 lb #2, 1500 lb #1), 200 pts/hook.

Usage:
    python manage.py import_2015_results              # dry-run
    python manage.py import_2015_results --commit     # write to DB
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
    "ohio state university": "ohio state",
    "california polytechnic state university": "cal poly state university",
    "cal poly san luis obispo": "cal poly state university",
    "university of northern iowa": "univeristy of northern iowa",
    "university of wisconsin - madison": "university of wisconsin-madison",
    "university of wisconsin - platteville": "university of wisconsin-platteville",
    "texas a & m university": "texas a&m university",
    "technion": "technion - israel insititute of technology",
    "technion – israel institute of technology": "technion - israel insititute of technology",
    "technion - israel institute of technology": "technion - israel insititute of technology",
    "michigan state university": "michigan state",
    "mississippi state university": "mississippi state",
    "wright state university": "wright state university",
}

CATEGORIES = [
    ("Weight-In Bonus",   100, 1),
    ("Design Judging",    420, 2),
    ("Written Design",    500, 3),
    ("Oral Presentation", 500, 5),
    ("Tractor Pull",      600, 6),
    ("Maneuverability",   100, 7),
    ("Durability",        200, 8),
]

SCORES = {
    "auburn university": {
        "Written Design": 0, "Oral Presentation": 0, "Design Judging": 34,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "cal poly state university": {
        "Written Design": 370, "Oral Presentation": 410, "Design Judging": 291,
        "Tractor Pull": 404, "Durability": 88, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "iowa state university": {
        "Written Design": 500, "Oral Presentation": 457, "Design Judging": 368,
        "Tractor Pull": 395, "Durability": 13, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "kansas state university": {
        "Written Design": 458, "Oral Presentation": 443, "Design Judging": 367,
        "Tractor Pull": 598, "Durability": 135, "Maneuverability": 46, "Weight-In Bonus": 100,
    },
    "mcgill university": {
        "Written Design": 407, "Oral Presentation": 361, "Design Judging": 350,
        "Tractor Pull": 427, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "north carolina state university": {
        "Written Design": 378, "Oral Presentation": 455, "Design Judging": 326,
        "Tractor Pull": 493, "Durability": 0, "Maneuverability": 89, "Weight-In Bonus": 100,
    },
    "north dakota state university": {
        "Written Design": 368, "Oral Presentation": 272, "Design Judging": 324,
        "Tractor Pull": 432, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "ohio state": {
        "Written Design": 437, "Oral Presentation": 394, "Design Judging": 420,
        "Tractor Pull": 536, "Durability": 0, "Maneuverability": 24, "Weight-In Bonus": 100,
    },
    "oklahoma state university": {
        "Written Design": 418, "Oral Presentation": 301, "Design Judging": 261,
        "Tractor Pull": 294, "Durability": 63, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "penn state university": {
        "Written Design": 427, "Oral Presentation": 429, "Design Judging": 316,
        "Tractor Pull": 493, "Durability": 13, "Maneuverability": 100, "Weight-In Bonus": 100,
    },
    "purdue": {
        "Written Design": 410, "Oral Presentation": 376, "Design Judging": 311,
        "Tractor Pull": 318, "Durability": 188, "Maneuverability": 48, "Weight-In Bonus": 0,
    },
    "south dakota state university": {
        "Written Design": 449, "Oral Presentation": 0, "Design Judging": 34,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "southern illinois university": {
        "Written Design": 155, "Oral Presentation": 0, "Design Judging": 311,
        "Tractor Pull": 307, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "technion - israel insititute of technology": {
        "Written Design": 426, "Oral Presentation": 417, "Design Judging": 338,
        "Tractor Pull": 181, "Durability": 88, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "texas a&m university": {
        "Written Design": 466, "Oral Presentation": 459, "Design Judging": 294,
        "Tractor Pull": 529, "Durability": 75, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "université laval": {
        "Written Design": 468, "Oral Presentation": 446, "Design Judging": 287,
        "Tractor Pull": 283, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of florida": {
        "Written Design": 0, "Oral Presentation": 0, "Design Judging": 34,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of illinois": {
        "Written Design": 458, "Oral Presentation": 428, "Design Judging": 285,
        "Tractor Pull": 454, "Durability": 13, "Maneuverability": 10, "Weight-In Bonus": 0,
    },
    "university of kentucky": {
        "Written Design": 469, "Oral Presentation": 500, "Design Judging": 380,
        "Tractor Pull": 600, "Durability": 200, "Maneuverability": 76, "Weight-In Bonus": 100,
    },
    "university of manitoba": {
        "Written Design": 437, "Oral Presentation": 348, "Design Judging": 305,
        "Tractor Pull": 453, "Durability": 0, "Maneuverability": 22, "Weight-In Bonus": 0,
    },
    "university of missouri": {
        "Written Design": 420, "Oral Presentation": 379, "Design Judging": 348,
        "Tractor Pull": 509, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of nebraska": {
        "Written Design": 452, "Oral Presentation": 416, "Design Judging": 284,
        "Tractor Pull": 96, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of saskatchewan": {
        "Written Design": 477, "Oral Presentation": 386, "Design Judging": 331,
        "Tractor Pull": 127, "Durability": 38, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of tennessee martin": {
        "Written Design": 370, "Oral Presentation": 419, "Design Judging": 257,
        "Tractor Pull": 283, "Durability": 196, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of wisconsin-madison": {
        "Written Design": 415, "Oral Presentation": 393, "Design Judging": 258,
        "Tractor Pull": 216, "Durability": 13, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of wisconsin-platteville": {
        "Written Design": 0, "Oral Presentation": 0, "Design Judging": 34,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of wisconsin - river falls": {
        "Written Design": 284, "Oral Presentation": 343, "Design Judging": 287,
        "Tractor Pull": 480, "Durability": 182, "Maneuverability": 72, "Weight-In Bonus": 0,
    },
    "wright state university": {
        "Written Design": 424, "Oral Presentation": 328, "Design Judging": 313,
        "Tractor Pull": 271, "Durability": 136, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
}


class Command(BaseCommand):
    help = "Import 2015 IQS historical results (hardcoded from score sheets)."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, default=15, help="Event id (default 15)")
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
            f"import_2015_results — event {event_id} ({event}) — {mode}"))
        self.stdout.write("\n--- Category scores ---")
        for cat_name, max_pts, _ in CATEGORIES:
            self.stdout.write(f"  {cat_name:<20} max={max_pts:>4}  teams={len(plan[cat_name]):>2}")

        if unmatched:
            self.stdout.write(self.style.WARNING(
                f"\nUnmatched DB names (check spelling): {unmatched}"))

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
