"""
Import 2016 IQS results from historical score sheets.

Category max points:
  Written Design: 500  Oral Presentation: 500  Design Judging: 420
  Tractor Pull:   600  Durability:        200  Maneuverability: 100
  Weight-In Bonus: 100

27 teams competed. 3-hook pull (1000 lb, 1500 lb #1, 1500 lb #2), 200 pts/hook.

Usage:
    python manage.py import_2016_results              # dry-run
    python manage.py import_2016_results --commit     # write to DB
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
        "Written Design": 426, "Oral Presentation": 318, "Design Judging": 278,
        "Tractor Pull": 333, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "cal poly state university": {
        "Written Design": 331, "Oral Presentation": 209, "Design Judging": 79,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "iowa state university": {
        "Written Design": 500, "Oral Presentation": 430, "Design Judging": 420,
        "Tractor Pull": 431, "Durability": 0, "Maneuverability": 61, "Weight-In Bonus": 100,
    },
    "kansas state university": {
        "Written Design": 486, "Oral Presentation": 454, "Design Judging": 377,
        "Tractor Pull": 574, "Durability": 170, "Maneuverability": 80, "Weight-In Bonus": 100,
    },
    "mcgill university": {
        "Written Design": 270, "Oral Presentation": 395, "Design Judging": 358,
        "Tractor Pull": 342, "Durability": 10, "Maneuverability": 54, "Weight-In Bonus": 0,
    },
    "modesto junior college": {
        "Written Design": 406, "Oral Presentation": 373, "Design Judging": 356,
        "Tractor Pull": 555, "Durability": 170, "Maneuverability": 62, "Weight-In Bonus": 100,
    },
    "north carolina state university": {
        "Written Design": 431, "Oral Presentation": 0, "Design Judging": 57,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "north dakota state university": {
        "Written Design": 424, "Oral Presentation": 330, "Design Judging": 343,
        "Tractor Pull": 416, "Durability": 200, "Maneuverability": 11, "Weight-In Bonus": 100,
    },
    "ohio state": {
        "Written Design": 437, "Oral Presentation": 369, "Design Judging": 407,
        "Tractor Pull": 388, "Durability": 0, "Maneuverability": 91, "Weight-In Bonus": 100,
    },
    "oklahoma state university": {
        "Written Design": 423, "Oral Presentation": 350, "Design Judging": 283,
        "Tractor Pull": 82, "Durability": 112, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "penn state university": {
        "Written Design": 376, "Oral Presentation": 0, "Design Judging": 57,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "purdue": {
        "Written Design": 480, "Oral Presentation": 399, "Design Judging": 336,
        "Tractor Pull": 192, "Durability": 0, "Maneuverability": 100, "Weight-In Bonus": 100,
    },
    "south dakota state university": {
        "Written Design": 399, "Oral Presentation": 305, "Design Judging": 302,
        "Tractor Pull": 455, "Durability": 20, "Maneuverability": 60, "Weight-In Bonus": 100,
    },
    "technion - israel insititute of technology": {
        "Written Design": 251, "Oral Presentation": 318, "Design Judging": 315,
        "Tractor Pull": 201, "Durability": 0, "Maneuverability": 55, "Weight-In Bonus": 0,
    },
    "texas a&m university": {
        "Written Design": 161, "Oral Presentation": 376, "Design Judging": 278,
        "Tractor Pull": 464, "Durability": 0, "Maneuverability": 51, "Weight-In Bonus": 0,
    },
    "université laval": {
        "Written Design": 452, "Oral Presentation": 366, "Design Judging": 337,
        "Tractor Pull": 558, "Durability": 132, "Maneuverability": 14, "Weight-In Bonus": 100,
    },
    "university of florida": {
        "Written Design": 389, "Oral Presentation": 263, "Design Judging": 282,
        "Tractor Pull": 378, "Durability": 60, "Maneuverability": 45, "Weight-In Bonus": 0,
    },
    "university of illinois": {
        "Written Design": 486, "Oral Presentation": 406, "Design Judging": 307,
        "Tractor Pull": 225, "Durability": 30, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of kentucky": {
        "Written Design": 474, "Oral Presentation": 379, "Design Judging": 376,
        "Tractor Pull": 588, "Durability": 188, "Maneuverability": 85, "Weight-In Bonus": 0,
    },
    "university of manitoba": {
        "Written Design": 475, "Oral Presentation": 403, "Design Judging": 339,
        "Tractor Pull": 390, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of missouri": {
        "Written Design": 107, "Oral Presentation": 348, "Design Judging": 347,
        "Tractor Pull": 561, "Durability": 146, "Maneuverability": 42, "Weight-In Bonus": 100,
    },
    "university of nebraska": {
        "Written Design": 485, "Oral Presentation": 500, "Design Judging": 407,
        "Tractor Pull": 564, "Durability": 173, "Maneuverability": 56, "Weight-In Bonus": 100,
    },
    "university of saskatchewan": {
        "Written Design": 175, "Oral Presentation": 353, "Design Judging": 342,
        "Tractor Pull": 495, "Durability": 0, "Maneuverability": 63, "Weight-In Bonus": 0,
    },
    "university of tennessee martin": {
        "Written Design": 142, "Oral Presentation": 354, "Design Judging": 264,
        "Tractor Pull": 387, "Durability": 20, "Maneuverability": 58, "Weight-In Bonus": 0,
    },
    "university of wisconsin-madison": {
        "Written Design": 439, "Oral Presentation": 371, "Design Judging": 290,
        "Tractor Pull": 46, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of wisconsin-platteville": {
        "Written Design": 300, "Oral Presentation": 311, "Design Judging": 244,
        "Tractor Pull": 450, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of wisconsin - river falls": {
        "Written Design": 187, "Oral Presentation": 0, "Design Judging": 57,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
}


class Command(BaseCommand):
    help = "Import 2016 IQS historical results (hardcoded from score sheets)."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, default=16, help="Event id (default 16)")
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
            f"import_2016_results — event {event_id} ({event}) — {mode}"))
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
