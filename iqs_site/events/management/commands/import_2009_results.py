"""
Import 2009 IQS results from historical score sheets.

Category max points:
  Written Design: 500  Oral Presentation: 500  Design Judging: 350
  Tractor Pull:   800  Maneuverability:   100  Weight-In Bonus: 100
  (No Durability. DJ max is 350 in 2009, not 420 — only 5 judging sections.)

23 teams competed. 4-hook pull (1050 lb #1, 1050 lb #2, 1550 lb #1, 1550 lb #2),
200 pts/hook. Scores have decimal precision. Pull hook scores are also stored as
subcategory scores. The "Initial Tech Quarantine" column maps to Weight-In Bonus.

Usage:
    python manage.py import_2009_results              # dry-run
    python manage.py import_2009_results --commit     # write to DB
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
    "university of wisconsin - madison": "university of wisconsin-madison",
    "university of wisconsin - platteville": "university of wisconsin-platteville",
    "university of wisconsin - river falls": "university of wisconsin - river falls",
    "michigan state university": "michigan state",
}

CATEGORIES = [
    ("Weight-In Bonus",   100, 1),
    ("Design Judging",    350, 2),
    ("Written Design",    500, 3),
    ("Oral Presentation", 500, 5),
    ("Tractor Pull",      800, 6),
    ("Maneuverability",   100, 7),
]

PULL_HOOKS = [
    ("1050 lb #1", 200),
    ("1050 lb #2", 200),
    ("1550 lb #1", 200),
    ("1550 lb #2", 200),
]

# Keyed by DB team name (lowercased). Decimal scores preserved from source PDF.
SCORES = {
    "cal poly state university": {
        "Written Design": 434.3, "Oral Presentation": 489.8, "Design Judging": 327.2,
        "Tractor Pull": 425.9, "Maneuverability": 0.0, "Weight-In Bonus": 100.0,
    },
    "iowa state university": {
        "Written Design": 466.7, "Oral Presentation": 405.1, "Design Judging": 334.0,
        "Tractor Pull": 723.3, "Maneuverability": 84.4, "Weight-In Bonus": 100.0,
    },
    "kansas state university": {
        "Written Design": 500.0, "Oral Presentation": 482.3, "Design Judging": 343.3,
        "Tractor Pull": 629.4, "Maneuverability": 93.8, "Weight-In Bonus": 100.0,
    },
    "modesto junior college": {
        "Written Design": 390.3, "Oral Presentation": 428.3, "Design Judging": 301.4,
        "Tractor Pull": 724.6, "Maneuverability": 96.9, "Weight-In Bonus": 100.0,
    },
    "nicholls state university": {
        "Written Design": 370.7, "Oral Presentation": 384.1, "Design Judging": 305.6,
        "Tractor Pull": 795.3, "Maneuverability": 97.9, "Weight-In Bonus": 100.0,
    },
    "north carolina state university": {
        "Written Design": 453.3, "Oral Presentation": 416.6, "Design Judging": 277.3,
        "Tractor Pull": 690.9, "Maneuverability": 69.8, "Weight-In Bonus": 100.0,
    },
    "north dakota state university": {
        "Written Design": 457.0, "Oral Presentation": 408.0, "Design Judging": 277.7,
        "Tractor Pull": 7.6, "Maneuverability": 0.0, "Weight-In Bonus": 0.0,
    },
    "ohio state": {
        "Written Design": 459.0, "Oral Presentation": 403.7, "Design Judging": 279.8,
        "Tractor Pull": 672.9, "Maneuverability": 63.5, "Weight-In Bonus": 100.0,
    },
    "oklahoma state university": {
        "Written Design": 441.0, "Oral Presentation": 442.8, "Design Judging": 263.1,
        "Tractor Pull": 504.7, "Maneuverability": 52.1, "Weight-In Bonus": 100.0,
    },
    "penn state university": {
        "Written Design": 417.7, "Oral Presentation": 333.1, "Design Judging": 277.2,
        "Tractor Pull": 26.0, "Maneuverability": 0.0, "Weight-In Bonus": 100.0,
    },
    "purdue": {
        "Written Design": 451.7, "Oral Presentation": 396.9, "Design Judging": 346.2,
        "Tractor Pull": 740.4, "Maneuverability": 96.9, "Weight-In Bonus": 100.0,
    },
    "southern illinois university": {
        "Written Design": 397.0, "Oral Presentation": 433.1, "Design Judging": 302.8,
        "Tractor Pull": 718.8, "Maneuverability": 100.0, "Weight-In Bonus": 100.0,
    },
    "texas a&m university": {
        "Written Design": 453.7, "Oral Presentation": 440.2, "Design Judging": 306.5,
        "Tractor Pull": 687.7, "Maneuverability": 82.3, "Weight-In Bonus": 100.0,
    },
    "university of illinois": {
        "Written Design": 490.3, "Oral Presentation": 500.0, "Design Judging": 323.7,
        "Tractor Pull": 784.4, "Maneuverability": 99.0, "Weight-In Bonus": 100.0,
    },
    "university of kentucky": {
        "Written Design": 439.7, "Oral Presentation": 434.5, "Design Judging": 303.4,
        "Tractor Pull": 774.9, "Maneuverability": 0.0, "Weight-In Bonus": 100.0,
    },
    "université laval": {
        "Written Design": 480.0, "Oral Presentation": 432.6, "Design Judging": 298.3,
        "Tractor Pull": 361.8, "Maneuverability": 82.3, "Weight-In Bonus": 100.0,
    },
    "university of missouri": {
        "Written Design": 440.7, "Oral Presentation": 420.1, "Design Judging": 283.9,
        "Tractor Pull": 335.0, "Maneuverability": 81.3, "Weight-In Bonus": 100.0,
    },
    "university of nebraska": {
        "Written Design": 115.3, "Oral Presentation": 478.4, "Design Judging": 321.3,
        "Tractor Pull": 757.2, "Maneuverability": 67.7, "Weight-In Bonus": 100.0,
    },
    "university of saskatchewan": {
        "Written Design": 464.3, "Oral Presentation": 378.7, "Design Judging": 350.0,
        "Tractor Pull": 551.2, "Maneuverability": 0.0, "Weight-In Bonus": 100.0,
    },
    "university of wisconsin-madison": {
        "Written Design": 400.0, "Oral Presentation": 437.5, "Design Judging": 260.1,
        "Tractor Pull": 0.0, "Maneuverability": 0.0, "Weight-In Bonus": 0.0,
    },
    "university of wisconsin-platteville": {
        "Written Design": 290.7, "Oral Presentation": 353.7, "Design Judging": 225.3,
        "Tractor Pull": 0.0, "Maneuverability": 94.8, "Weight-In Bonus": 100.0,
    },
    "university of wisconsin - river falls": {
        "Written Design": 378.7, "Oral Presentation": 487.1, "Design Judging": 294.3,
        "Tractor Pull": 126.5, "Maneuverability": 24.0, "Weight-In Bonus": 100.0,
    },
    "university of wyoming": {
        "Written Design": 0.0, "Oral Presentation": 0.0, "Design Judging": 93.5,
        "Tractor Pull": 0.0, "Maneuverability": 0.0, "Weight-In Bonus": 0.0,
    },
}

# Per-hook pull point scores (not distances — source PDF shows points only).
PULL_DATA = {
    "cal poly state university":           [54.3, 0.0, 182.3, 189.3],
    "iowa state university":               [185.3, 190.5, 176.6, 170.9],
    "kansas state university":             [189.3, 69.0, 182.7, 188.3],
    "modesto junior college":              [180.3, 169.3, 184.4, 190.6],
    "nicholls state university":           [196.1, 199.2, 200.0, 200.0],
    "north carolina state university":     [146.1, 169.2, 186.3, 189.3],
    "north dakota state university":       [0.0, 0.0, 0.0, 7.6],
    "ohio state":                          [190.0, 137.7, 165.4, 179.8],
    "oklahoma state university":           [109.6, 99.9, 124.5, 170.6],
    "penn state university":               [0.0, 25.2, 0.8, 0.0],
    "purdue":                              [185.7, 184.5, 186.0, 184.2],
    "southern illinois university":        [174.2, 168.6, 184.0, 191.9],
    "texas a&m university":                [190.0, 126.7, 184.7, 186.2],
    "university of illinois":              [200.0, 199.0, 191.8, 193.7],
    "university of kentucky":              [193.0, 200.0, 187.6, 194.3],
    "université laval":                    [38.8, 111.9, 143.4, 67.7],
    "university of missouri":              [104.2, 44.6, 70.7, 115.4],
    "university of nebraska":              [184.5, 191.4, 186.3, 195.0],
    "university of saskatchewan":          [107.5, 111.0, 159.3, 173.5],
    "university of wisconsin-madison":     [0.0, 0.0, 0.0, 0.0],
    "university of wisconsin-platteville": [0.0, 0.0, 0.0, 0.0],
    "university of wisconsin - river falls": [0.0, 52.9, 15.6, 58.0],
    "university of wyoming":               [0.0, 0.0, 0.0, 0.0],
}


class Command(BaseCommand):
    help = "Import 2009 IQS historical results with pull subcategory scores."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, default=9, help="Event id (default 9)")
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
            f"import_2009_results — event {event_id} ({event}) — {mode}"))
        self.stdout.write("\n--- Category scores ---")
        for cat_name, max_pts, _ in CATEGORIES:
            self.stdout.write(f"  {cat_name:<20} max={max_pts:>4}  teams={len(plan_cat[cat_name]):>2}")
        self.stdout.write("\n--- Pull subcategory scores ---")
        for hook_name, max_pts in PULL_HOOKS:
            self.stdout.write(f"  {hook_name:<14} max={max_pts:>4}  teams={len(plan_pull[hook_name]):>2}")

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
