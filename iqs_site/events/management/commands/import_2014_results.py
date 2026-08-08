"""
Import 2014 IQS PRELIMINARY results from historical score sheets.

Category max points:
  Written Design: 500  Oral Presentation: 500  Design Judging: 420
  Tractor Pull:   800  Maneuverability:   100  Weight-In Bonus: 100

27 teams appear in rankings; Milwaukee School of Engineering attended but has no scores
in the preliminary sheet. The 4-hook pull (1000 lb #1, 1000 lb #2, 1500 lb #1, 1500 lb #2)
is worth 200 pts per hook.

DATA NOTES:
  - Scores are PRELIMINARY and may differ from final official results.
  - University of Wisconsin-Madison is ranked in all categories but their individual
    scores are absent from the preliminary PDF (their row is blank in every table).
    This team is excluded from the import; their EventTeam.total_score stays at 0.
  - Lamar University has Team Presentation = -16 (penalty deduction visible in source).
  - Several totals in the source are ±1 from the sum of displayed integer scores;
    this reflects rounding of decimal sub-scores during normalization.
  - The category is labeled "Team Presentation" in this year's sheet but is imported
    under the standard "Oral Presentation" ScoreCategory name.

Usage:
    python manage.py import_2014_results              # dry-run
    python manage.py import_2014_results --commit     # write to DB
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
    "the ohio state university": "ohio state",
    "ohio state university, the": "ohio state",
    "ohio state university": "ohio state",
    "california polytechnic state university": "cal poly state university",
    "texas a & m university": "texas a&m university",
    "university of laval": "université laval",
    "universite laval": "université laval",
    "michigan state university": "michigan state",
    "mississippi state university": "mississippi state",
    "university of tennessee - martin": "university of tennessee martin",
    "purdue university": "purdue",
    "university of wisconsin - madison": "university of wisconsin-madison",
    "university of wisconsin - platteville": "university of wisconsin-platteville",
}

CATEGORIES = [
    ("Weight-In Bonus",   100, 1),
    ("Design Judging",    420, 2),
    ("Written Design",    500, 3),
    ("Oral Presentation", 500, 5),
    ("Tractor Pull",      800, 6),
    ("Maneuverability",   100, 7),
]

PULL_HOOKS = [
    ("1000 lb #1", 200),
    ("1000 lb #2", 200),
    ("1500 lb #1", 200),
    ("1500 lb #2", 200),
]

# 26 teams with data from preliminary score sheet.
# University of Wisconsin-Madison is excluded (scores absent from preliminary PDF).
# Milwaukee School of Engineering attended but has no scores in this PDF.
SCORES = {
    "cal poly state university": {
        "Written Design": 419, "Oral Presentation": 438, "Design Judging": 317,
        "Tractor Pull": 673, "Maneuverability": 30, "Weight-In Bonus": 100,
    },
    "iowa state university": {
        "Written Design": 476, "Oral Presentation": 500, "Design Judging": 384,
        "Tractor Pull": 602, "Maneuverability": 56, "Weight-In Bonus": 100,
    },
    "kansas state university": {
        "Written Design": 490, "Oral Presentation": 469, "Design Judging": 403,
        "Tractor Pull": 759, "Maneuverability": 61, "Weight-In Bonus": 100,
    },
    "lamar university": {
        "Written Design": 374, "Oral Presentation": -16, "Design Judging": 220,
        "Tractor Pull": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "mcgill university": {
        "Written Design": 398, "Oral Presentation": 473, "Design Judging": 348,
        "Tractor Pull": 591, "Maneuverability": 60, "Weight-In Bonus": 100,
    },
    "modesto junior college": {
        "Written Design": 375, "Oral Presentation": 443, "Design Judging": 400,
        "Tractor Pull": 717, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "north carolina state university": {
        "Written Design": 429, "Oral Presentation": 425, "Design Judging": 320,
        "Tractor Pull": 606, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "north dakota state university": {
        "Written Design": 417, "Oral Presentation": 370, "Design Judging": 346,
        "Tractor Pull": 569, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "oklahoma state university": {
        "Written Design": 484, "Oral Presentation": 431, "Design Judging": 325,
        "Tractor Pull": 645, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "penn state university": {
        "Written Design": 396, "Oral Presentation": 253, "Design Judging": 330,
        "Tractor Pull": 601, "Maneuverability": 83, "Weight-In Bonus": 0,
    },
    "purdue": {
        "Written Design": 471, "Oral Presentation": 465, "Design Judging": 325,
        "Tractor Pull": 658, "Maneuverability": 96, "Weight-In Bonus": 100,
    },
    "south dakota state university": {
        "Written Design": 383, "Oral Presentation": 407, "Design Judging": 300,
        "Tractor Pull": 626, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "southern illinois university": {
        "Written Design": 350, "Oral Presentation": 409, "Design Judging": 336,
        "Tractor Pull": 671, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "texas a&m university": {
        "Written Design": 494, "Oral Presentation": 416, "Design Judging": 311,
        "Tractor Pull": 724, "Maneuverability": 51, "Weight-In Bonus": 100,
    },
    "ohio state": {
        "Written Design": 474, "Oral Presentation": 413, "Design Judging": 369,
        "Tractor Pull": 713, "Maneuverability": 52, "Weight-In Bonus": 100,
    },
    "university of florida": {
        "Written Design": 283, "Oral Presentation": 289, "Design Judging": 264,
        "Tractor Pull": 0, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of illinois": {
        "Written Design": 463, "Oral Presentation": 391, "Design Judging": 270,
        "Tractor Pull": 530, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of kentucky": {
        "Written Design": 500, "Oral Presentation": 491, "Design Judging": 420,
        "Tractor Pull": 799, "Maneuverability": 85, "Weight-In Bonus": 100,
    },
    "université laval": {
        "Written Design": 484, "Oral Presentation": 467, "Design Judging": 363,
        "Tractor Pull": 581, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of manitoba": {
        "Written Design": 484, "Oral Presentation": 416, "Design Judging": 290,
        "Tractor Pull": 224, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of missouri": {
        "Written Design": 444, "Oral Presentation": 375, "Design Judging": 377,
        "Tractor Pull": 589, "Maneuverability": 59, "Weight-In Bonus": 0,
    },
    "university of nebraska": {
        "Written Design": 488, "Oral Presentation": 385, "Design Judging": 364,
        "Tractor Pull": 715, "Maneuverability": 0, "Weight-In Bonus": 0,
    },
    "university of saskatchewan": {
        "Written Design": 466, "Oral Presentation": 438, "Design Judging": 392,
        "Tractor Pull": 502, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of tennessee martin": {
        "Written Design": 370, "Oral Presentation": 339, "Design Judging": 268,
        "Tractor Pull": 410, "Maneuverability": 32, "Weight-In Bonus": 0,
    },
    "university of wisconsin-platteville": {
        "Written Design": 298, "Oral Presentation": 402, "Design Judging": 283,
        "Tractor Pull": 392, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of wisconsin - river falls": {
        "Written Design": 304, "Oral Presentation": 339, "Design Judging": 310,
        "Tractor Pull": 679, "Maneuverability": 100, "Weight-In Bonus": 0,
    },
}

# Hook point scores from preliminary pull page (page 4).
# University of Wisconsin-Madison ranked 25th in all hooks but scores absent from PDF.
PULL_DATA = {
    "cal poly state university":          [180.3, 191.5, 143.8, 157.7],
    "iowa state university":              [111.6, 182.1, 128.2, 180.5],
    "kansas state university":            [173.9, 194.6, 193.7, 196.7],
    "lamar university":                   [0.0, 0.0, 0.0, 0.0],
    "mcgill university":                  [108.0, 184.8, 145.9, 152.0],
    "modesto junior college":             [154.9, 192.3, 169.7, 200.0],
    "north carolina state university":    [116.5, 191.4, 145.0, 153.0],
    "north dakota state university":      [117.4, 190.5, 148.7, 111.9],
    "oklahoma state university":          [164.7, 194.2, 169.4, 116.9],
    "penn state university":              [96.6, 185.7, 120.0, 198.7],
    "purdue":                             [134.4, 153.9, 191.2, 178.9],
    "south dakota state university":      [169.9, 154.4, 155.6, 146.1],
    "southern illinois university":       [170.3, 192.6, 168.0, 140.3],
    "texas a&m university":               [172.2, 191.5, 179.5, 180.7],
    "ohio state":                         [155.5, 190.2, 185.1, 182.2],
    "university of florida":              [0.0, 0.0, 0.0, 0.0],
    "university of illinois":             [96.5, 183.7, 60.9, 188.6],
    "university of kentucky":             [200.0, 200.0, 200.0, 198.6],
    "université laval":                   [117.8, 170.3, 168.3, 124.1],
    "university of manitoba":             [87.7, 89.3, 46.6, 0.2],
    "university of missouri":             [151.5, 193.1, 154.2, 89.9],
    "university of nebraska":             [168.4, 192.9, 178.4, 175.5],
    "university of saskatchewan":         [87.2, 156.2, 130.5, 128.5],
    "university of tennessee martin":     [95.5, 76.8, 122.2, 115.3],
    "university of wisconsin-platteville": [75.4, 123.7, 103.8, 88.6],
    "university of wisconsin - river falls": [191.4, 190.5, 143.0, 153.9],
}

MISSING_TEAMS = [
    "University of Wisconsin-Madison (ranked 25th in all hooks; individual scores absent from preliminary PDF)",
    "Milwaukee School of Engineering (attended but not scored in preliminary PDF)",
]


class Command(BaseCommand):
    help = "Import 2014 IQS PRELIMINARY results (26 of 27 scored teams; UW-Madison scores missing)."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, default=14, help="Event id (default 14)")
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

        mode = "COMMIT" if commit else "DRY-RUN (no DB writes)"
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"import_2014_results — event {event_id} ({event}) — {mode}"))
        self.stdout.write(self.style.WARNING(
            "\nNOTE: Scores are PRELIMINARY. UW-Madison and MSOE excluded (see script docstring)."))
        self.stdout.write("\n--- Category scores ---")
        for cat_name, max_pts, _ in CATEGORIES:
            self.stdout.write(f"  {cat_name:<20} max={max_pts:>4}  teams={len(plan_cat[cat_name]):>2}")
        self.stdout.write("\n--- Pull subcategory scores ---")
        for hook_name, max_pts in PULL_HOOKS:
            self.stdout.write(f"  {hook_name:<14} max={max_pts:>4}  teams={len(plan_pull[hook_name]):>2}")
        self.stdout.write("\nTeams not imported:")
        for t in MISSING_TEAMS:
            self.stdout.write(f"  - {t}")

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
