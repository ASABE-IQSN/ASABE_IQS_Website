"""
Import 2013 IQS results from historical score sheets.

Category max points:
  Written Design: 500  Oral Presentation: 500  Design Judging: 420
  Tractor Pull:   800  Maneuverability:   100  Weight-In Bonus: 100
  (No Durability in 2013.)

29 teams. 4-hook pull (1000 lb #1, 1000 lb #2, 1500 lb #1, 1500 lb #2), 200 pts/hook.

DATA NOTES:
  - WD for 22 teams taken directly from page 3 normalized totals (500-pt scale).
  - WD for 7 teams (Univ of Nebraska through Univ of Wisconsin - River Falls) computed
    from 8 per-judge WD sub-category averages using the additive normalization:
    normalized = sum(sub-averages) + 39.00 (Universite Laval anchors the scale at 500).
  - Pull data in the PDF only covers 16 teams alphabetically (Cal Poly through The Ohio
    State). The 13 teams from Universite Laval through Univ of Wisconsin - River Falls
    were absent from the pull table; their pull scores are NOT imported (left as unscored).
  - "University of Saskatchewan 2" is a second team from the same university; if this
    team is not in the DB, the script will warn and skip it.

Usage:
    python manage.py import_2013_results              # dry-run
    python manage.py import_2013_results --commit     # write to DB
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
    "technion – israel institute of technology": "technion - israel insititute of technology",
    "technion - israel institute of technology": "technion - israel insititute of technology",
    "michigan state university": "michigan state",
    "mississippi state university": "mississippi state",
    "university of tennessee - martin": "university of tennessee martin",
    "university of wisconsin - madison": "university of wisconsin-madison",
    "university of wisconsin - platteville": "university of wisconsin-platteville",
    "universite laval": "université laval",
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

# All scores keyed by DB team name (lowercased).
# WD values marked with (*) are computed from sub-category averages + 39.00 offset;
# they may differ from the true normalized value by up to ±0.2 due to rounding.
SCORES = {
    "cal poly state university": {
        "Written Design": 427.00, "Oral Presentation": 445.83, "Design Judging": 306.20,
        "Tractor Pull": 602.4, "Maneuverability": 98.0, "Weight-In Bonus": 0,
    },
    "ferris state": {
        "Written Design": 0.00, "Oral Presentation": 324.61, "Design Judging": 177.20,
        "Tractor Pull": 0.0, "Maneuverability": 0.0, "Weight-In Bonus": 0,
    },
    "iowa state university": {
        "Written Design": 467.67, "Oral Presentation": 445.97, "Design Judging": 301.00,
        "Tractor Pull": 385.0, "Maneuverability": 0.0, "Weight-In Bonus": 0,
    },
    "kansas state university": {
        "Written Design": 498.67, "Oral Presentation": 497.80, "Design Judging": 415.80,
        "Tractor Pull": 738.9, "Maneuverability": 100.0, "Weight-In Bonus": 100,
    },
    "lamar university": {
        "Written Design": 351.67, "Oral Presentation": 0.00, "Design Judging": 237.60,
        "Tractor Pull": 132.9, "Maneuverability": 0.0, "Weight-In Bonus": 0,
    },
    "mcgill university": {
        "Written Design": 428.00, "Oral Presentation": 417.17, "Design Judging": 348.00,
        "Tractor Pull": 592.6, "Maneuverability": 0.0, "Weight-In Bonus": 100,
    },
    "modesto junior college": {
        "Written Design": 464.67, "Oral Presentation": 450.59, "Design Judging": 374.80,
        "Tractor Pull": 728.0, "Maneuverability": 79.6, "Weight-In Bonus": 100,
    },
    "north carolina state university": {
        "Written Design": 437.33, "Oral Presentation": 459.83, "Design Judging": 326.35,
        "Tractor Pull": 594.3, "Maneuverability": 98.0, "Weight-In Bonus": 100,
    },
    "north dakota state university": {
        "Written Design": 426.67, "Oral Presentation": 396.35, "Design Judging": 331.40,
        "Tractor Pull": 519.1, "Maneuverability": 100.0, "Weight-In Bonus": 100,
    },
    "oklahoma state university": {
        "Written Design": 417.67, "Oral Presentation": 380.99, "Design Judging": 313.20,
        "Tractor Pull": 484.0, "Maneuverability": 0.0, "Weight-In Bonus": 100,
    },
    "penn state university": {
        "Written Design": 458.33, "Oral Presentation": 461.34, "Design Judging": 330.80,
        "Tractor Pull": 668.8, "Maneuverability": 99.0, "Weight-In Bonus": 100,
    },
    "purdue": {
        "Written Design": 460.33, "Oral Presentation": 442.50, "Design Judging": 349.00,
        "Tractor Pull": 321.2, "Maneuverability": 0.0, "Weight-In Bonus": 100,
    },
    "south dakota state university": {
        "Written Design": 421.00, "Oral Presentation": 351.97, "Design Judging": 292.60,
        "Tractor Pull": 671.0, "Maneuverability": 0.0, "Weight-In Bonus": 0,
    },
    "southern illinois university": {
        "Written Design": 389.33, "Oral Presentation": 0.00, "Design Judging": 329.40,
        "Tractor Pull": 563.4, "Maneuverability": 0.0, "Weight-In Bonus": 0,
    },
    "texas a&m university": {
        "Written Design": 409.00, "Oral Presentation": 412.22, "Design Judging": 306.55,
        "Tractor Pull": 645.4, "Maneuverability": 95.9, "Weight-In Bonus": 100,
    },
    "ohio state": {
        "Written Design": 476.33, "Oral Presentation": 455.26, "Design Judging": 365.20,
        "Tractor Pull": 665.6, "Maneuverability": 0.0, "Weight-In Bonus": 0,
    },
    # Pull data not available in PDF for teams below (left as 0; see script docstring)
    "université laval": {
        "Written Design": 500.00, "Oral Presentation": 460.98, "Design Judging": 379.00,
        "Tractor Pull": 0, "Maneuverability": 98.0, "Weight-In Bonus": 100,
    },
    "university of florida": {
        "Written Design": 322.67, "Oral Presentation": 383.19, "Design Judging": 279.00,
        "Tractor Pull": 0, "Maneuverability": 0.0, "Weight-In Bonus": 0,
    },
    "university of illinois": {
        "Written Design": 468.33, "Oral Presentation": 434.38, "Design Judging": 300.80,
        "Tractor Pull": 0, "Maneuverability": 0.0, "Weight-In Bonus": 0,
    },
    "university of kentucky": {
        "Written Design": 497.67, "Oral Presentation": 499.06, "Design Judging": 420.00,
        "Tractor Pull": 0, "Maneuverability": 0.0, "Weight-In Bonus": 100,
    },
    "university of manitoba": {
        "Written Design": 467.00, "Oral Presentation": 436.88, "Design Judging": 318.80,
        "Tractor Pull": 0, "Maneuverability": 0.0, "Weight-In Bonus": 100,
    },
    "university of missouri": {
        "Written Design": 435.33, "Oral Presentation": 436.16, "Design Judging": 307.00,
        "Tractor Pull": 0, "Maneuverability": 96.9, "Weight-In Bonus": 0,
    },
    "university of nebraska": {
        "Written Design": 378.33, "Oral Presentation": 453.55, "Design Judging": 310.60,  # WD computed*
        "Tractor Pull": 0, "Maneuverability": 0.0, "Weight-In Bonus": 100,
    },
    "university of saskatchewan": {
        "Written Design": 409.33, "Oral Presentation": 494.30, "Design Judging": 390.20,  # WD computed*
        "Tractor Pull": 0, "Maneuverability": 99.0, "Weight-In Bonus": 100,
    },
    "university of saskatchewan-emerging markets": {
        "Written Design": 435.70, "Oral Presentation": 416.11, "Design Judging": 260.80,  # WD computed*
        "Tractor Pull": 0, "Maneuverability": 0.0, "Weight-In Bonus": 100,
    },
    "university of tennessee martin": {
        "Written Design": 361.40, "Oral Presentation": 383.29, "Design Judging": 286.80,  # WD computed*
        "Tractor Pull": 0, "Maneuverability": 96.9, "Weight-In Bonus": 0,
    },
    "university of wisconsin-madison": {
        "Written Design": 491.40, "Oral Presentation": 500.00, "Design Judging": 342.60,  # WD computed*
        "Tractor Pull": 0, "Maneuverability": 74.5, "Weight-In Bonus": 0,
    },
    "university of wisconsin-platteville": {
        "Written Design": 341.93, "Oral Presentation": 339.45, "Design Judging": 271.20,  # WD computed*
        "Tractor Pull": 0, "Maneuverability": 0.0, "Weight-In Bonus": 0,
    },
    "university of wisconsin - river falls": {
        "Written Design": 377.60, "Oral Presentation": 400.73, "Design Judging": 345.80,  # WD computed*
        "Tractor Pull": 0, "Maneuverability": 95.9, "Weight-In Bonus": 100,
    },
}

# Hook point scores available only for 16 teams (Cal Poly through The Ohio State).
# Format: [H1000#1_pts, H1000#2_pts, H1500#1_pts, H1500#2_pts]
PULL_DATA = {
    "cal poly state university":      [74.38, 154.35, 191.84, 181.82],
    "ferris state":                   [0.00, 0.00, 0.00, 0.00],
    "iowa state university":          [52.02, 46.24, 146.31, 140.41],
    "kansas state university":        [183.84, 186.28, 190.42, 178.37],
    "lamar university":               [44.97, 1.47, 47.01, 39.45],
    "mcgill university":              [117.43, 147.30, 181.13, 146.70],
    "modesto junior college":         [200.00, 164.84, 196.72, 166.46],
    "north carolina state university": [93.20, 165.50, 185.69, 149.95],
    "north dakota state university":  [79.13, 156.72, 158.31, 124.94],
    "oklahoma state university":      [91.31, 159.55, 147.25, 85.87],
    "penn state university":          [172.20, 152.29, 185.79, 158.56],
    "purdue":                         [0.00, 3.23, 178.89, 139.09],
    "south dakota state university":  [132.67, 165.73, 184.48, 188.09],
    "southern illinois university":   [118.43, 159.64, 150.85, 134.43],
    "texas a&m university":           [177.21, 158.38, 173.55, 136.25],
    "ohio state":                     [186.31, 165.20, 175.42, 138.64],
}


class Command(BaseCommand):
    help = "Import 2013 IQS historical results. Pull data is partial (16 of 29 teams)."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, default=13, help="Event id (default 13)")
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
            f"import_2013_results — event {event_id} ({event}) — {mode}"))
        self.stdout.write("\n--- Category scores ---")
        for cat_name, max_pts, _ in CATEGORIES:
            self.stdout.write(f"  {cat_name:<20} max={max_pts:>4}  teams={len(plan_cat[cat_name]):>2}")
        self.stdout.write("\n--- Pull subcategory scores (16 of 29 teams) ---")
        for hook_name, max_pts in PULL_HOOKS:
            self.stdout.write(f"  {hook_name:<14} max={max_pts:>4}  teams={len(plan_pull[hook_name]):>2}")
        self.stdout.write(self.style.WARNING(
            "\nWARNING: Pull data missing from PDF for 13 teams (Universite Laval "
            "through Univ. of Wisconsin-River Falls). Their Tractor Pull scores are "
            "set to 0 in SCORES; hook subcategory records will not be created for them."))

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
