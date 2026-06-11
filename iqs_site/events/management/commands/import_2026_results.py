"""
Import 2026 IQS results from the master score spreadsheet (.xlsx).

Loads, for the 2026 event (default event_id=26):
  * Category scores (normalized totals) for all 8 categories.
  * Raw subcategory scores for Written Design, Defense of Design, Design Judging
    and Tractor Pull (the judging subcategories are raw / pre-normalization and
    intentionally do NOT sum to the normalized category total).
  * Pull final_distance for the three A-team hooks (1100#1, 1100#2, 1600#1).
  * DurabilityRun.total_laps.
  * ManeuverabilityRun.score (100-pt total).
  * Recomputes EventTeam.total_score as the sum of category scores.

Source layout was derived from the 2026 workbook:
  * Category totals come from each main category sheet (team = col A, total = col C).
  * Raw subcategories come from each "<Category> Ranking & Scores" sheet's
    right-hand RAW SCORES block (team + subcat columns recorded below).
  * Pull distances / durability laps / maneuverability totals come from the
    main Tractor Pull / Durability / Maneuverability sheets.

Usage (dry-run prints planned changes, makes NO database writes):
    python manage.py import_2026_results --master /path/to/master.xlsx
    python manage.py import_2026_results --master /path/to/master.xlsx --commit
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from events.models import (
    Event, Team, EventTeam, Pull, Hook, DurabilityRun, ManeuverabilityRun,
    ScoreCategory, ScoreCategoryInstance, ScoreCategoryScore,
    ScoreSubCategory, ScoreSubCategoryInstance, ScoreSubCategoryScore,
)
# Reuse the existing normalization helper + alias table.
from events.management.commands.import_scores import _safe_float, NAME_ALIASES

# Spreadsheet team names that the base alias table does not yet cover.
EXTRA_ALIASES = {
    "itaq": "institut de technologie",
    "university of wisconsin river falls": "university of wisconsin - river falls",
}

# (sheet, ScoreCategory name, max_points, display_order). Team = col A (0),
# normalized total = col C (2) on every main sheet.
CATEGORY_TOTALS = [
    ("Weight-In Bonus",     "Weight-In Bonus",   100, 1),
    ("Design Judging",      "Design Judging",    420, 2),
    ("Written Design",      "Written Design",    500, 3),
    ("Defense of Design",   "Defense of Design",  85, 4),
    ("Presentation Points", "Oral Presentation", 500, 5),
    ("Tractor Pull",        "Tractor Pull",      600, 6),
    ("Maneuverability",     "Maneuverability",   100, 7),
    ("Durability",          "Durability",        200, 8),
]
TOTAL_COL = 2  # column C on every main category sheet

# Raw-subcategory blocks: category -> (ranking sheet, team_col_idx,
# [(subcategory name, data_col_idx, max_points), ...]). 0-based indices.
SUBCATS = {
    "Written Design": ("Written Design Ranking & Scores", 12, [
        ("Criteria & Objectives", 14, 5), ("Format", 15, 15),
        ("Design Details", 16, 270), ("Testing & Development", 17, 70),
        ("Design Log", 18, 20), ("Judges Discretion", 19, 20),
        ("Cost Strategy", 20, 50), ("Cost Analysis", 21, 50),
    ]),
    "Defense of Design": ("Defense of Design Ranking & Sco", 8, [
        ("Design Goal", 10, 70), ("Design Considerations", 11, 70),
        ("Company/Project Lim.", 12, 70), ("Data Driven Decisions", 13, 70),
    ]),
    "Design Judging": ("Design Judging Ranking & Scores", 9, [
        ("Serviceability", 11, 70), ("Manufacturability", 12, 70),
        ("Safety", 13, 70), ("Ergonomics", 14, 70),
        ("Test & Development", 15, 70),
    ]),
    "Tractor Pull": ("Tractor Pull Ranking & Scores", 7, [
        ("Hook 1 - 1000 lbs", 9, 200), ("Hook 2 - 1500 lbs", 10, 200),
        ("Hook 3 - 1500 lbs", 11, 200),
    ]),
}

# Pull DISTANCE columns on the main "Tractor Pull" sheet -> DB hook name.
PULL_DISTANCE_COLS = [
    ("A Team 1100 Hook 1", 4),
    ("A Team Hook 2",      6),
    ("A Team 1600 Hook 3", 8),
]
DURABILITY_LAPS_COL = 3      # main "Durability" sheet
MANEUVER_SCORE_COL = 2       # main "Maneuverability" sheet (100-pt total)


class Command(BaseCommand):
    help = "Import 2026 IQS results (scores, pull distances, laps, maneuverability) from the master xlsx."

    def add_arguments(self, parser):
        parser.add_argument("--master", required=True, help="Path to the 2026 master score .xlsx")
        parser.add_argument("--event", type=int, default=26, help="Event id (default 26)")
        parser.add_argument("--commit", action="store_true", help="Write to the database (default: dry-run)")

    def handle(self, *args, **opts):
        try:
            import openpyxl
        except ImportError:
            raise CommandError("openpyxl is required (pip install openpyxl).")

        path = opts["master"]
        event_id = opts["event"]
        commit = opts["commit"]

        if not os.path.isfile(path):
            raise CommandError(f"File not found: {path}")
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            raise CommandError(f"Event {event_id} does not exist.")

        wb = openpyxl.load_workbook(path, data_only=True)

        aliases = dict(NAME_ALIASES)
        aliases.update(EXTRA_ALIASES)
        teams_by_name = {t.team_name.strip().lower(): t for t in Team.objects.all()}

        def match_team(raw):
            if raw is None:
                return None
            s = str(raw).strip().rstrip("*").strip()
            if not s:
                return None
            key = aliases.get(s.lower(), s.lower())
            return teams_by_name.get(key)

        def rows(sheet_name):
            ws = wb[sheet_name]
            return [list(r) for r in ws.iter_rows(values_only=True)]

        def cell(row, idx):
            return row[idx] if idx < len(row) else None

        mode = "COMMIT" if commit else "DRY-RUN (no DB writes)"
        self.stdout.write(self.style.MIGRATE_HEADING(f"import_2026_results — event {event_id} ({event}) — {mode}"))

        # Collect planned work; only execute when commit=True.
        unmatched = set()

        # ---- 1. Category + subcategory scores --------------------------------
        # plan_cat: {category_name: {"cfg": (max,order), "totals": {team: val},
        #            "subs": [(name, max, {team: val})]}}
        plan_cat = {}
        for sheet, cat_name, max_pts, order in CATEGORY_TOTALS:
            totals = {}
            for row in rows(sheet):
                team = match_team(cell(row, 0))
                if team is None:
                    if cell(row, 0) and any(k in str(cell(row, 0)).lower() for k in ("university", "state", "college", "institut", "itaq", "poly", "mcgill")):
                        unmatched.add(str(cell(row, 0)).strip())
                    continue
                val = _safe_float(cell(row, TOTAL_COL))
                if val is not None:
                    totals[team] = val
            plan_cat[cat_name] = {"cfg": (max_pts, order), "totals": totals, "subs": []}

        for cat_name, (sheet, team_col, subdefs) in SUBCATS.items():
            data = rows(sheet)
            for sub_name, col_idx, sub_max in subdefs:
                vals = {}
                for row in data:
                    team = match_team(cell(row, team_col))
                    if team is None:
                        continue
                    vals[team] = _safe_float(cell(row, col_idx))
                plan_cat[cat_name]["subs"].append((sub_name, sub_max, vals))

        # ---- 2. Pull distances ----------------------------------------------
        hooks_by_name = {h.hook_name: h for h in Hook.objects.filter(event_id=event_id)}
        # plan_pulls: list of (team, hook_name, distance)
        plan_pulls = []
        missing_pull = []
        for row in rows("Tractor Pull"):
            team = match_team(cell(row, 0))
            if team is None:
                continue
            for hook_name, col_idx in PULL_DISTANCE_COLS:
                dist = _safe_float(cell(row, col_idx))
                # Leave 0-ft (and blank) pulls untouched: null distance, state unchanged.
                if dist is None or dist == 0:
                    continue
                hook = hooks_by_name.get(hook_name)
                pull = (Pull.objects.filter(event_id=event_id, team_id=team.team_id,
                                            hook_id=hook.hook_id).first() if hook else None)
                if pull is None:
                    missing_pull.append((team.team_name, hook_name))
                    continue
                plan_pulls.append((pull, team, hook_name, dist))

        # ---- 3. Durability laps ---------------------------------------------
        plan_dur = []
        for row in rows("Durability"):
            team = match_team(cell(row, 0))
            if team is None:
                continue
            laps = _safe_float(cell(row, DURABILITY_LAPS_COL))
            run = DurabilityRun.objects.filter(event_id=event_id, team_id=team.team_id).first()
            if run is None:
                continue
            plan_dur.append((run, team, int(round(laps)) if laps is not None else None))

        # ---- 4. Maneuverability score ---------------------------------------
        plan_man = []
        for row in rows("Maneuverability"):
            team = match_team(cell(row, 0))
            if team is None:
                continue
            score = _safe_float(cell(row, MANEUVER_SCORE_COL))
            # Defer `score`: its DB column may not exist yet (migration gated),
            # and dry-run must not SELECT it.
            run = ManeuverabilityRun.objects.filter(
                event_id=event_id, team_id=team.team_id
            ).only("maneuverability_run_id", "team_id", "event_id",
                   "updated_at", "updated_by_source").first()
            if run is None:
                continue
            plan_man.append((run, team, score))

        # ---- Report ----------------------------------------------------------
        self.stdout.write("\n--- Category & subcategory scores ---")
        for _, cat_name, _, _ in CATEGORY_TOTALS:
            p = plan_cat[cat_name]
            subs = ", ".join(f"{n}({len(v)})" for n, _, v in p["subs"]) or "—"
            self.stdout.write(f"  {cat_name:<18} totals: {len(p['totals']):>2} teams   subcats: {subs}")

        self.stdout.write("\n--- Pull distances (final_distance) ---")
        for hook_name, _ in PULL_DISTANCE_COLS:
            n = sum(1 for _, _, h, _ in plan_pulls if h == hook_name)
            self.stdout.write(f"  {hook_name:<22} {n} pulls")
        for pull, team, hook_name, dist in plan_pulls[:6]:
            self.stdout.write(f"    e.g. {team.team_name:<28} {hook_name:<20} {dist:.2f} ft (pull_id={pull.pull_id})")
        if missing_pull:
            self.stdout.write(self.style.WARNING(f"  No matching Pull row for: {missing_pull}"))

        self.stdout.write("\n--- Durability laps ---")
        self.stdout.write(f"  {len(plan_dur)} runs; e.g. " +
                          ", ".join(f"{t.team_name.split()[0]}={l}" for _, t, l in plan_dur[:8]))

        self.stdout.write("\n--- Maneuverability scores ---")
        self.stdout.write(f"  {len(plan_man)} runs; e.g. " +
                          ", ".join(f"{t.team_name.split()[0]}={s}" for _, t, s in plan_man[:8]))

        if unmatched:
            self.stdout.write(self.style.WARNING("\nUnmatched team names (skipped): " + "; ".join(sorted(unmatched))))

        if not commit:
            self.stdout.write(self.style.NOTICE("\nDRY-RUN complete. No database changes were made. Re-run with --commit to write."))
            return

        # ---- Execute ---------------------------------------------------------
        now = timezone.now()
        with transaction.atomic():
            for _, cat_name, _, _ in CATEGORY_TOTALS:
                p = plan_cat[cat_name]
                max_pts, order = p["cfg"]
                cat, _ = ScoreCategory.objects.get_or_create(category_name=cat_name)
                inst, _ = ScoreCategoryInstance.objects.update_or_create(
                    event=event, score_category=cat,
                    defaults={"max_points": max_pts, "released": True, "display_order": order},
                )
                for team, val in p["totals"].items():
                    ScoreCategoryScore.objects.update_or_create(
                        team=team, category_instance=inst, defaults={"score": val})
                for sub_name, sub_max, vals in p["subs"]:
                    sub, _ = ScoreSubCategory.objects.get_or_create(subcategory_name=sub_name)
                    sub_inst, _ = ScoreSubCategoryInstance.objects.update_or_create(
                        event=event, score_subcategory=sub, category_instance=inst,
                        defaults={"max_points": sub_max, "released": True})
                    for team, val in vals.items():
                        ScoreSubCategoryScore.objects.update_or_create(
                            team=team, subcategory=sub_inst, defaults={"score": val})

            for pull, team, hook_name, dist in plan_pulls:
                pull.final_distance = dist
                pull.state = "COMPLETED"
                pull.updated_by_source = "import_2026"
                pull.save(update_fields=["final_distance", "state", "updated_by_source"])

            for run, team, laps in plan_dur:
                run.total_laps = laps
                run.updated_at = now
                run.updated_by_source = "import_2026"
                run.save(update_fields=["total_laps", "updated_at", "updated_by_source"])

            for run, team, score in plan_man:
                run.score = score
                run.updated_at = now
                run.updated_by_source = "import_2026"
                run.save(update_fields=["score", "updated_at", "updated_by_source"])

            # Recompute EventTeam totals (sum of category scores).
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
            f"\nCOMMIT complete: scores written, {len(plan_pulls)} pull distances, "
            f"{len(plan_dur)} durability laps, {len(plan_man)} maneuverability scores, "
            f"{updated} EventTeam totals updated."))
