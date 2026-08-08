"""
Import 2018 IQS results from historical score sheets.

Category max points:
  Written Design: 500  Oral Presentation: 500  Design Judging: 420
  Tractor Pull:   600  Durability:        200  Maneuverability: 100
  Weight-In Bonus: 100  (100-pt bonus for passing initial weigh-in)

28 teams competed. 2 teams (Colorado Mesa, RV College of Engineering) are
not in the DB and are skipped with a warning.

Usage:
    python manage.py import_2018_results              # dry-run
    python manage.py import_2018_results --commit     # write to DB
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from events.models import (
    Event, Team, EventTeam,
    ScoreCategory, ScoreCategoryInstance, ScoreCategoryScore,
    ScoreSubCategory, ScoreSubCategoryInstance, ScoreSubCategoryScore,
)
from events.management.commands.import_scores import NAME_ALIASES

EXTRA_ALIASES = {
    "ariel university": "areil university (israel)",
    "the ohio state university": "ohio state",
    "ohio state university": "ohio state",
    "california polytechnic state university": "cal poly state university",
    "cal poly san luis obispo": "cal poly state university",
    "university of northern iowa": "univeristy of northern iowa",
    "university of wisconsin - madison": "university of wisconsin-madison",
    "university of wisconsin - platteville": "university of wisconsin-platteville",
    "texas a & m university": "texas a&m university",
    "michigan state university": "michigan state",
    "mississippi state university": "mississippi state",
}

# (category_name, max_points, display_order)
CATEGORIES = [
    ("Weight-In Bonus",   100, 1),
    ("Design Judging",    420, 2),
    ("Written Design",    500, 3),
    ("Oral Presentation", 500, 5),
    ("Tractor Pull",      600, 6),
    ("Maneuverability",   100, 7),
    ("Durability",        200, 8),
]

PULL_HOOKS = [
    ("1000 lb", 200),
    ("1500 lb #1", 200),
    ("1500 lb #2", 200),
]

# Hook point scores from page 4 of 2018 score sheet.
# Colorado Mesa University and RV College of Engineering are not in the DB.
PULL_DATA = {
    "areil university (israel)":          [121.8, 121.3, 84.6],
    "auburn university":                  [0.0, 0.0, 0.0],
    "cal poly state university":          [71.0, 1.2, 0.0],
    "iowa state university":              [65.2, 142.3, 133.4],
    "kansas state university":            [165.4, 183.7, 181.7],
    "mcgill university":                  [0.0, 0.0, 0.0],
    "north carolina state university":    [0.0, 0.0, 0.0],
    "north dakota state university":      [115.1, 152.3, 168.2],
    "ohio state":                         [144.8, 133.3, 149.4],
    "oklahoma state university":          [0.0, 0.0, 0.0],
    "penn state university":              [0.0, 0.0, 0.0],
    "purdue":                             [165.8, 143.0, 173.9],
    "south dakota state university":      [167.8, 200.0, 199.5],
    "texas a&m university":               [0.0, 0.0, 0.0],
    "texas tech university":              [0.0, 0.0, 0.0],
    "university of illinois":             [127.7, 88.3, 87.3],
    "university of kentucky":             [197.3, 186.6, 200.0],
    "université laval":                   [134.4, 151.8, 173.0],
    "university of manitoba":             [171.6, 149.9, 172.8],
    "university of missouri":             [200.0, 192.3, 197.5],
    "university of nebraska":             [5.2, 154.4, 0.0],
    "univeristy of northern iowa":        [135.0, 71.6, 0.0],
    "university of saskatchewan":         [146.8, 186.4, 192.4],
    "university of tennessee martin":     [143.2, 144.0, 185.8],
    "university of wisconsin-madison":    [110.9, 110.3, 81.3],
    "university of wisconsin-platteville": [0.0, 0.0, 0.0],
    "university of wisconsin - river falls": [141.1, 149.9, 170.1],
}

# Keyed by DB team name (lowercased). Values: per-category scores.
# 3-hook pull (1000 lb, 1500 lb #1, 1500 lb #2), 200 pts/hook = 600 max.
SCORES = {
    "areil university (israel)": {
        "Written Design": 336, "Oral Presentation": 387, "Design Judging": 345,
        "Tractor Pull": 328, "Durability": 29, "Maneuverability": 99, "Weight-In Bonus": 100,
    },
    "auburn university": {
        "Written Design": 0, "Oral Presentation": 0, "Design Judging": 79,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "cal poly state university": {
        "Written Design": 362, "Oral Presentation": 326, "Design Judging": 330,
        "Tractor Pull": 72, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "iowa state university": {
        "Written Design": 500, "Oral Presentation": 462, "Design Judging": 385,
        "Tractor Pull": 341, "Durability": 0, "Maneuverability": 100, "Weight-In Bonus": 100,
    },
    "kansas state university": {
        "Written Design": 469, "Oral Presentation": 483, "Design Judging": 373,
        "Tractor Pull": 531, "Durability": 0, "Maneuverability": 81, "Weight-In Bonus": 100,
    },
    "mcgill university": {
        "Written Design": 453, "Oral Presentation": 468, "Design Judging": 325,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "north carolina state university": {
        "Written Design": 407, "Oral Presentation": 0, "Design Judging": 79,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "north dakota state university": {
        "Written Design": 304, "Oral Presentation": 367, "Design Judging": 340,
        "Tractor Pull": 436, "Durability": 200, "Maneuverability": 93, "Weight-In Bonus": 100,
    },
    "ohio state": {
        "Written Design": 429, "Oral Presentation": 418, "Design Judging": 393,
        "Tractor Pull": 428, "Durability": 0, "Maneuverability": 71, "Weight-In Bonus": 100,
    },
    "oklahoma state university": {
        "Written Design": 454, "Oral Presentation": 0, "Design Judging": 79,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "penn state university": {
        "Written Design": 0, "Oral Presentation": 190, "Design Judging": 221,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "purdue": {
        "Written Design": 420, "Oral Presentation": 392, "Design Judging": 337,
        "Tractor Pull": 483, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "south dakota state university": {
        "Written Design": 480, "Oral Presentation": 500, "Design Judging": 390,
        "Tractor Pull": 567, "Durability": 57, "Maneuverability": 84, "Weight-In Bonus": 100,
    },
    "texas a&m university": {
        "Written Design": 197, "Oral Presentation": 348, "Design Judging": 79,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "texas tech university": {
        "Written Design": 295, "Oral Presentation": 355, "Design Judging": 253,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of illinois": {
        "Written Design": 453, "Oral Presentation": 332, "Design Judging": 332,
        "Tractor Pull": 303, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of kentucky": {
        "Written Design": 442, "Oral Presentation": 405, "Design Judging": 394,
        "Tractor Pull": 584, "Durability": 95, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "université laval": {
        "Written Design": 403, "Oral Presentation": 440, "Design Judging": 377,
        "Tractor Pull": 459, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of manitoba": {
        "Written Design": 474, "Oral Presentation": 491, "Design Judging": 370,
        "Tractor Pull": 494, "Durability": 152, "Maneuverability": 7, "Weight-In Bonus": 0,
    },
    "university of missouri": {
        "Written Design": 438, "Oral Presentation": 397, "Design Judging": 372,
        "Tractor Pull": 590, "Durability": 76, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of nebraska": {
        "Written Design": 500, "Oral Presentation": 494, "Design Judging": 420,
        "Tractor Pull": 160, "Durability": 0, "Maneuverability": 54, "Weight-In Bonus": 100,
    },
    "univeristy of northern iowa": {
        "Written Design": 134, "Oral Presentation": 249, "Design Judging": 282,
        "Tractor Pull": 207, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of saskatchewan": {
        "Written Design": 262, "Oral Presentation": 434, "Design Judging": 389,
        "Tractor Pull": 526, "Durability": 19, "Maneuverability": 84, "Weight-In Bonus": 100,
    },
    "university of tennessee martin": {
        "Written Design": 302, "Oral Presentation": 287, "Design Judging": 254,
        "Tractor Pull": 473, "Durability": 0, "Maneuverability": 86, "Weight-In Bonus": 0,
    },
    "university of wisconsin-madison": {
        "Written Design": 440, "Oral Presentation": 382, "Design Judging": 325,
        "Tractor Pull": 303, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of wisconsin-platteville": {
        "Written Design": 270, "Oral Presentation": 0, "Design Judging": 79,
        "Tractor Pull": 0, "Durability": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of wisconsin - river falls": {
        "Written Design": 220, "Oral Presentation": 418, "Design Judging": 319,
        "Tractor Pull": 461, "Durability": 86, "Maneuverability": 89, "Weight-In Bonus": 100,
    },
}

# Teams in the PDF not present in the DB (skipped with a warning).
SKIPPED_TEAMS = ["Colorado Mesa", "RV College of Engineering"]


class Command(BaseCommand):
    help = "Import 2018 IQS historical results (hardcoded from score sheets)."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, default=18, help="Event id (default 18)")
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

        def match_team(name):
            key = aliases.get(name.lower(), name.lower())
            return teams_by_name.get(key)

        mode = "COMMIT" if commit else "DRY-RUN (no DB writes)"
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"import_2018_results — event {event_id} ({event}) — {mode}"))

        self.stdout.write(f"\nSkipped teams (not in DB): {', '.join(SKIPPED_TEAMS)}")

        plan_cat = {cat_name: {} for cat_name, _, _ in CATEGORIES}
        plan_pull = {hook_name: {} for hook_name, _ in PULL_HOOKS}
        unmatched = []

        for db_name_lower, cat_scores in SCORES.items():
            team = teams_by_name.get(db_name_lower)
            if team is None:
                unmatched.append(db_name_lower)
                continue
            for cat_name, score in cat_scores.items():
                plan_cat[cat_name][team] = score

        for db_name_lower, hook_pts in PULL_DATA.items():
            team = teams_by_name.get(db_name_lower)
            if team is None:
                continue
            for (hook_name, _), pts in zip(PULL_HOOKS, hook_pts):
                plan_pull[hook_name][team] = pts

        self.stdout.write("\n--- Category scores ---")
        for cat_name, max_pts, _ in CATEGORIES:
            self.stdout.write(f"  {cat_name:<20} max={max_pts:>4}  teams={len(plan_cat[cat_name]):>2}")
        self.stdout.write("\n--- Pull subcategory scores ---")
        for hook_name, max_pts in PULL_HOOKS:
            self.stdout.write(f"  {hook_name:<14} max={max_pts:>4}  teams={len(plan_pull[hook_name]):>2}")

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
                for team, score in plan_cat[cat_name].items():
                    ScoreCategoryScore.objects.update_or_create(
                        team=team, category_instance=inst, defaults={"score": score})

            pull_cat, _ = ScoreCategory.objects.get_or_create(category_name="Tractor Pull")
            pull_inst, _ = ScoreCategoryInstance.objects.get_or_create(
                event=event, score_category=pull_cat)
            for hook_name, max_pts in PULL_HOOKS:
                sub, _ = ScoreSubCategory.objects.get_or_create(subcategory_name=hook_name)
                sub_inst, _ = ScoreSubCategoryInstance.objects.update_or_create(
                    event=event, score_subcategory=sub, category_instance=pull_inst,
                    defaults={"max_points": max_pts, "released": True})
                for team, pts in plan_pull[hook_name].items():
                    ScoreSubCategoryScore.objects.update_or_create(
                        team=team, subcategory=sub_inst, defaults={"score": pts})

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
