"""
Import 2012 IQS results from historical score sheets.

NOTE: The source PDF is labeled "2011 ASABE" but the user confirmed this is
actually 2012 competition data. It imports to event_id=12 by default.

Category max points:
  Written Design: 500  Oral Presentation: 500  Design Judging: 420
  Tractor Pull:   800  Maneuverability:   100  Weight-In Bonus: 100
  (No Durability category in 2012.)

24 teams competed. 4-hook pull (1050 lb #1, 1050 lb #2, 1550 lb #1, 1550 lb #2),
200 pts/hook. Pull distances in feet are recorded in PULL_DATA and will be
written to Pull.final_distance if Pull records already exist for event hooks.

Usage:
    python manage.py import_2012_results              # dry-run
    python manage.py import_2012_results --commit     # write to DB
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from events.models import (
    Event, Team, EventTeam, Pull, Hook,
    ScoreCategory, ScoreCategoryInstance, ScoreCategoryScore,
    ScoreSubCategory, ScoreSubCategoryInstance, ScoreSubCategoryScore,
)
from events.management.commands.import_scores import NAME_ALIASES

EXTRA_ALIASES = {
    "the ohio state university": "ohio state",
    "ohio state university, the": "ohio state",
    "ohio state university": "ohio state",
    "california polytechnic state university": "cal poly state university",
    "cal poly san luis obispo": "cal poly state university",
    "texas a & m university": "texas a&m university",
    "mississippi state university": "mississippi state",
    "michigan state university": "michigan state",
    "university of tennessee - martin": "university of tennessee martin",
    "tennessee - martin, university of": "university of tennessee martin",
    "university of wisconsin - madison": "university of wisconsin-madison",
    "university of wisconsin - platteville": "university of wisconsin-platteville",
    "illinois, university of": "university of illinois",
    "kentucky, university of": "university of kentucky",
    "laval, université": "université laval",
    "manitoba, university of": "university of manitoba",
    "missouri, university of": "university of missouri",
    "nebraska, university of": "university of nebraska",
    "saskatchewan, university of": "university of saskatchewan",
    "wisconsin - madison, university of": "university of wisconsin-madison",
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

# (hook_name, max_points, display_order)
PULL_HOOKS = [
    ("1050 lb #1", 200),
    ("1050 lb #2", 200),
    ("1550 lb #1", 200),
    ("1550 lb #2", 200),
]

# Keyed by DB team name (lowercased).
# Category scores from the overall scores table.
SCORES = {
    "cal poly state university": {
        "Written Design": 453, "Oral Presentation": 466, "Design Judging": 300,
        "Tractor Pull": 533, "Maneuverability": 48, "Weight-In Bonus": 100,
    },
    "university of illinois": {
        "Written Design": 482, "Oral Presentation": 500, "Design Judging": 367,
        "Tractor Pull": 584, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "iowa state university": {
        "Written Design": 478, "Oral Presentation": 426, "Design Judging": 294,
        "Tractor Pull": 280, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "kansas state university": {
        "Written Design": 500, "Oral Presentation": 411, "Design Judging": 322,
        "Tractor Pull": 797, "Maneuverability": 69, "Weight-In Bonus": 100,
    },
    "university of kentucky": {
        "Written Design": 472, "Oral Presentation": 442, "Design Judging": 420,
        "Tractor Pull": 671, "Maneuverability": 82, "Weight-In Bonus": 100,
    },
    "université laval": {
        "Written Design": 489, "Oral Presentation": 470, "Design Judging": 368,
        "Tractor Pull": 604, "Maneuverability": 82, "Weight-In Bonus": 100,
    },
    "university of manitoba": {
        "Written Design": 447, "Oral Presentation": 428, "Design Judging": 374,
        "Tractor Pull": 766, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "milwaukee school of engineering": {
        "Written Design": 481, "Oral Presentation": 441, "Design Judging": 358,
        "Tractor Pull": 379, "Maneuverability": 87, "Weight-In Bonus": 100,
    },
    "mississippi state": {
        "Written Design": 0, "Oral Presentation": 33, "Design Judging": 63,
        "Tractor Pull": 286, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of missouri": {
        "Written Design": 413, "Oral Presentation": 438, "Design Judging": 342,
        "Tractor Pull": 643, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "modesto junior college": {
        "Written Design": 436, "Oral Presentation": 496, "Design Judging": 337,
        "Tractor Pull": 572, "Maneuverability": 80, "Weight-In Bonus": 100,
    },
    "north carolina state university": {
        "Written Design": 378, "Oral Presentation": 365, "Design Judging": 355,
        "Tractor Pull": 325, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "north dakota state university": {
        "Written Design": 327, "Oral Presentation": 426, "Design Judging": 335,
        "Tractor Pull": 604, "Maneuverability": 35, "Weight-In Bonus": 100,
    },
    "ohio state": {
        "Written Design": 453, "Oral Presentation": 416, "Design Judging": 297,
        "Tractor Pull": 554, "Maneuverability": 97, "Weight-In Bonus": 100,
    },
    "oklahoma state university": {
        "Written Design": 460, "Oral Presentation": 438, "Design Judging": 323,
        "Tractor Pull": 477, "Maneuverability": 68, "Weight-In Bonus": 100,
    },
    "penn state university": {
        "Written Design": 456, "Oral Presentation": 453, "Design Judging": 333,
        "Tractor Pull": 616, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "purdue": {
        "Written Design": 443, "Oral Presentation": 450, "Design Judging": 361,
        "Tractor Pull": 732, "Maneuverability": 100, "Weight-In Bonus": 100,
    },
    "university of saskatchewan": {
        "Written Design": 484, "Oral Presentation": 438, "Design Judging": 364,
        "Tractor Pull": 677, "Maneuverability": 88, "Weight-In Bonus": 100,
    },
    "south dakota state university": {
        "Written Design": 454, "Oral Presentation": 480, "Design Judging": 312,
        "Tractor Pull": 614, "Maneuverability": 51, "Weight-In Bonus": 100,
    },
    "southern illinois university": {
        "Written Design": 399, "Oral Presentation": 327, "Design Judging": 310,
        "Tractor Pull": 450, "Maneuverability": 96, "Weight-In Bonus": 100,
    },
    "texas a&m university": {
        "Written Design": 429, "Oral Presentation": 465, "Design Judging": 321,
        "Tractor Pull": 563, "Maneuverability": 94, "Weight-In Bonus": 100,
    },
    "university of tennessee martin": {
        "Written Design": 208, "Oral Presentation": 343, "Design Judging": 203,
        "Tractor Pull": 273, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
    "university of wisconsin-madison": {
        "Written Design": 443, "Oral Presentation": 414, "Design Judging": 288,
        "Tractor Pull": 660, "Maneuverability": 76, "Weight-In Bonus": 100,
    },
    "university of wisconsin - river falls": {
        "Written Design": 422, "Oral Presentation": 387, "Design Judging": 297,
        "Tractor Pull": 588, "Maneuverability": 0, "Weight-In Bonus": 100,
    },
}

# Per-hook pull data: [points, distance_ft] for each of the 4 hooks in order
# (1050 lb #1, 1050 lb #2, 1550 lb #1, 1550 lb #2).
PULL_DATA = {
    "cal poly state university":         [(94.72, 113.78), (110.58, 120.77), (177.52, 192.44), (150.25, 160.57)],
    "university of illinois":            [(125.42, 150.66), (139.37, 152.21), (182.35, 197.68), (136.70, 146.09)],
    "iowa state university":             [(0.00, 0.00), (0.00, 0.00), (139.57, 151.30), (140.61, 150.27)],
    "kansas state university":           [(200.00, 240.25), (200.00, 218.43), (198.60, 215.29), (198.32, 211.94)],
    "university of kentucky":            [(84.44, 101.43), (195.28, 213.27), (195.19, 211.60), (196.04, 209.51)],
    "université laval":                  [(94.33, 113.31), (163.35, 178.40), (174.14, 188.78), (172.18, 184.01)],
    "university of manitoba":            [(198.91, 238.94), (174.81, 190.92), (195.63, 212.07), (196.20, 209.68)],
    "milwaukee school of engineering":   [(82.47, 99.07), (130.79, 142.84), (103.30, 111.98), (62.24, 66.52)],
    "mississippi state":                 [(76.15, 91.48), (0.00, 0.00), (103.50, 112.20), (106.58, 113.90)],
    "university of missouri":            [(117.74, 141.44), (140.17, 153.09), (200.00, 216.81), (185.41, 198.15)],
    "modesto junior college":            [(138.24, 166.06), (170.78, 186.52), (100.62, 109.08), (162.80, 173.98)],
    "north carolina state university":   [(0.00, 0.00), (159.61, 174.32), (165.07, 178.94), (0.00, 0.00)],
    "north dakota state university":     [(101.45, 121.87), (152.43, 166.48), (191.59, 207.69), (158.37, 169.25)],
    "ohio state":                        [(84.40, 101.39), (117.10, 127.89), (178.54, 193.55), (174.28, 186.25)],
    "oklahoma state university":         [(108.25, 130.03), (164.16, 179.29), (196.87, 213.42), (7.80, 8.34)],
    "penn state university":             [(122.02, 146.58), (129.94, 141.91), (191.93, 208.06), (172.04, 183.86)],
    "purdue":                            [(148.47, 178.35), (184.20, 201.17), (198.98, 215.70), (200.00, 213.74)],
    "university of saskatchewan":        [(141.16, 169.57), (164.09, 179.21), (191.20, 207.27), (180.46, 192.86)],
    "south dakota state university":     [(122.46, 147.10), (129.17, 141.07), (186.27, 201.93), (175.76, 187.84)],
    "southern illinois university":      [(126.79, 152.31), (182.48, 199.30), (9.00, 9.76), (131.92, 140.98)],
    "texas a&m university":              [(101.35, 121.75), (98.35, 107.41), (180.27, 195.42), (182.75, 195.30)],
    "university of tennessee martin":    [(64.12, 77.02), (35.65, 38.93), (65.24, 70.72), (108.19, 115.62)],
    "university of wisconsin-madison":   [(159.96, 192.15), (118.70, 129.64), (196.87, 213.42), (184.47, 197.14)],
    "university of wisconsin - river falls": [(120.80, 145.11), (147.79, 161.41), (170.67, 185.02), (149.01, 159.25)],
}


class Command(BaseCommand):
    help = "Import 2012 IQS historical results with pull subcategory scores and distances."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, default=12, help="Event id (default 12)")
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
            f"import_2012_results — event {event_id} ({event}) — {mode}"))

        # Category scores plan
        plan_cat = {cat_name: {} for cat_name, _, _ in CATEGORIES}
        plan_pull_pts = {hook_name: {} for hook_name, _ in PULL_HOOKS}
        plan_pull_dist = []  # (team, hook_name, distance_ft)
        unmatched = []

        for db_name_lower, cat_scores in SCORES.items():
            team = teams_by_name.get(db_name_lower)
            if team is None:
                unmatched.append(db_name_lower)
                continue
            for cat_name, score in cat_scores.items():
                plan_cat[cat_name][team] = score

        for db_name_lower, hook_data in PULL_DATA.items():
            team = teams_by_name.get(db_name_lower)
            if team is None:
                continue
            for (hook_name, _), (pts, dist_ft) in zip(PULL_HOOKS, hook_data):
                plan_pull_pts[hook_name][team] = pts
                if dist_ft > 0:
                    plan_pull_dist.append((team, hook_name, dist_ft))

        # Check for existing Hook records
        hooks_by_name = {h.hook_name: h for h in Hook.objects.filter(event_id=event_id)}

        self.stdout.write("\n--- Category scores ---")
        for cat_name, max_pts, _ in CATEGORIES:
            self.stdout.write(f"  {cat_name:<20} max={max_pts:>4}  teams={len(plan_cat[cat_name]):>2}")

        self.stdout.write("\n--- Pull subcategory scores ---")
        for hook_name, max_pts in PULL_HOOKS:
            self.stdout.write(f"  {hook_name:<14} max={max_pts:>4}  teams={len(plan_pull_pts[hook_name]):>2}")

        self.stdout.write("\n--- Pull distances ---")
        if hooks_by_name:
            self.stdout.write(f"  {len(plan_pull_dist)} distances to write (hooks found: {list(hooks_by_name.keys())})")
        else:
            self.stdout.write(
                "  No Hook records found for event — pull distances will be skipped.\n"
                "  (Create Hook records for this event first to enable distance imports.)")

        if unmatched:
            self.stdout.write(self.style.WARNING(f"\nUnmatched DB names: {unmatched}"))

        if not commit:
            self.stdout.write(self.style.NOTICE(
                "\nDRY-RUN complete. No DB changes. Re-run with --commit to write."))
            return

        with transaction.atomic():
            # Category scores
            for cat_name, max_pts, display_order in CATEGORIES:
                cat, _ = ScoreCategory.objects.get_or_create(category_name=cat_name)
                inst, _ = ScoreCategoryInstance.objects.update_or_create(
                    event=event, score_category=cat,
                    defaults={"max_points": max_pts, "released": True,
                              "display_order": display_order})
                for team, score in plan_cat[cat_name].items():
                    ScoreCategoryScore.objects.update_or_create(
                        team=team, category_instance=inst, defaults={"score": score})

            # Pull subcategory point scores
            pull_cat, _ = ScoreCategory.objects.get_or_create(category_name="Tractor Pull")
            pull_inst, _ = ScoreCategoryInstance.objects.get_or_create(
                event=event, score_category=pull_cat)
            for hook_name, max_pts in PULL_HOOKS:
                sub, _ = ScoreSubCategory.objects.get_or_create(subcategory_name=hook_name)
                sub_inst, _ = ScoreSubCategoryInstance.objects.update_or_create(
                    event=event, score_subcategory=sub, category_instance=pull_inst,
                    defaults={"max_points": max_pts, "released": True})
                for team, pts in plan_pull_pts[hook_name].items():
                    ScoreSubCategoryScore.objects.update_or_create(
                        team=team, subcategory=sub_inst, defaults={"score": pts})

            # Pull distances (only if Hook records exist)
            dist_written = 0
            if hooks_by_name:
                for team, hook_name, dist_ft in plan_pull_dist:
                    hook = hooks_by_name.get(hook_name)
                    if not hook:
                        continue
                    pull = Pull.objects.filter(
                        event_id=event_id, team_id=team.team_id,
                        hook_id=hook.hook_id).first()
                    if pull:
                        pull.final_distance = dist_ft
                        pull.state = "COMPLETED"
                        pull.updated_by_source = "import_2012"
                        pull.save(update_fields=["final_distance", "state", "updated_by_source"])
                        dist_written += 1

            # Recompute totals
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
            f"{dist_written} pull distances set, "
            f"{updated} EventTeam totals recomputed."))
