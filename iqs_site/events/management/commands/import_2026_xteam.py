"""
Import 2026 X-Team results from the X-Team master spreadsheet (.xlsx).

X teams are scored in their own categories (parallel to, but distinct from, the
A-team categories):
  * Written Design Report   (normalized 1000-pt total, 4 raw subcategories)
  * Team Presentation       (normalized 1000-pt total, 8 raw subcategories)
  * Tractor Pull (X-Team)   (800-pt total = Pull 1 + Pull 2, 400 each)

It also sets Pull.final_distance for the two X hooks (X Team 1600 Hook 1/2) and
recomputes EventTeam.total_score for the event.

Data source: the "Overall Scores" sheet of "2026 X_Team_Scoring_Master.xlsx"
(team in col A; team names are the base names without the " X" suffix).

X-pull record fix: the pull rows for the X hooks were generated with one wrong
team (North Carolina X instead of Penn State X). EventTeam is the source of
truth, so this command detects a single mis-assigned pull per X hook and swaps
it to the X EventTeam that is otherwise missing a pull on that hook.

Usage (dry-run prints planned changes, makes NO database writes):
    python manage.py import_2026_xteam --xteam /path/to/xteam.xlsx
    python manage.py import_2026_xteam --xteam /path/to/xteam.xlsx --commit
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from events.models import (
    Event, EventTeam, Pull, Hook,
    ScoreCategory, ScoreCategoryInstance, ScoreCategoryScore,
    ScoreSubCategory, ScoreSubCategoryInstance, ScoreSubCategoryScore,
)
from events.management.commands.import_scores import _safe_float, NAME_ALIASES

SHEET = "Overall Scores"

# (ScoreCategory name, max_points, display_order, total_col_idx,
#  [(subcategory name, col_idx, max_points), ...]). 0-based columns.
XTEAM_CATEGORIES = [
    ("Written Design Report", 1000, 9, 6, [
        ("Presentation", 1, 100), ("Data", 2, 200),
        ("Arguments", 3, 300), ("New Design", 4, 400),
    ]),
    ("Team Presentation", 1000, 10, 17, [
        ("Technical Content", 8, 200), ("Identification of Flaws", 9, 200),
        ("Description of Achievements", 10, 100), ("Presentation Delivery", 11, 50),
        ("Team Communication", 12, 50), ("Use of Visuals", 13, 100),
        ("Questions & Answers", 14, 100), ("Improvements/Ownership", 15, 200),
    ]),
    ("Tractor Pull (X-Team)", 800, 11, 25, [
        ("Pull 1", 20, 400), ("Pull 2", 23, 400),
    ]),
]

# X hook name -> distance column on the Overall Scores sheet.
XTEAM_PULL_DIST = [
    ("X Team 1600 Hook 1", 19),
    ("X Team 1600 Hook 2", 22),
]


class Command(BaseCommand):
    help = "Import 2026 X-Team results (scores + pull distances) from the X-Team master xlsx."

    def add_arguments(self, parser):
        parser.add_argument("--xteam", required=True, help="Path to the 2026 X-Team master .xlsx")
        parser.add_argument("--event", type=int, default=26)
        parser.add_argument("--commit", action="store_true", help="Write to the database (default: dry-run)")

    def handle(self, *args, **opts):
        try:
            import openpyxl
        except ImportError:
            raise CommandError("openpyxl is required (pip install openpyxl).")

        path, event_id, commit = opts["xteam"], opts["event"], opts["commit"]
        if not os.path.isfile(path):
            raise CommandError(f"File not found: {path}")
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            raise CommandError(f"Event {event_id} does not exist.")

        wb = openpyxl.load_workbook(path, data_only=True)
        rows = [list(r) for r in wb[SHEET].iter_rows(values_only=True)]

        def cell(row, idx):
            return row[idx] if idx is not None and idx < len(row) else None

        # X teams keyed by their base name (DB name minus trailing " X").
        x_by_base = {}
        x_team_ids = set()
        for et in EventTeam.objects.filter(event_id=event_id, team_id__gte=200).select_related("team"):
            base = et.team.team_name.strip()
            if base.lower().endswith(" x"):
                base = base[:-2].strip()
            x_by_base[base.lower()] = et.team
            x_team_ids.add(et.team_id)

        def match_x(raw):
            if raw is None:
                return None
            s = str(raw).strip().rstrip("*").strip()
            if not s:
                return None
            key = NAME_ALIASES.get(s.lower(), s.lower())
            return x_by_base.get(key) or x_by_base.get(s.lower())

        mode = "COMMIT" if commit else "DRY-RUN (no DB writes)"
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"import_2026_xteam — event {event_id} ({event}) — {mode}"))
        self.stdout.write(f"X EventTeams: {len(x_team_ids)} ({sorted(x_team_ids)})")

        unmatched = set()

        # ---- Category + subcategory scores ----------------------------------
        # plan: {cat_name: {"cfg": (max,order), "totals": {team: v}, "subs": [(name,max,{team:v})]}}
        plan = {}
        for cat_name, max_pts, order, total_col, subdefs in XTEAM_CATEGORIES:
            totals, subs = {}, []
            for row in rows:
                team = match_x(cell(row, 0))
                if team is None:
                    raw = cell(row, 0)
                    if raw and any(k in str(raw).lower() for k in ("university", "state")):
                        unmatched.add(str(raw).strip())
                    continue
                v = _safe_float(cell(row, total_col))
                if v is not None:
                    totals[team] = v
            for sub_name, col_idx, sub_max in subdefs:
                vals = {}
                for row in rows:
                    team = match_x(cell(row, 0))
                    if team is None:
                        continue
                    vals[team] = _safe_float(cell(row, col_idx))
                subs.append((sub_name, sub_max, vals))
            plan[cat_name] = {"cfg": (max_pts, order), "totals": totals, "subs": subs}

        # ---- X pull record fix (mis-assigned team per hook) -----------------
        hooks = {h.hook_name: h for h in Hook.objects.filter(event_id=event_id)}
        pull_swaps = []   # (pull_obj, old_team_id, new_team_id, hook_name)
        for hook_name, _ in XTEAM_PULL_DIST:
            hook = hooks.get(hook_name)
            if not hook:
                continue
            hpulls = list(Pull.objects.filter(event_id=event_id, hook_id=hook.hook_id))
            present = {p.team_id for p in hpulls}
            wrong = [p for p in hpulls if p.team_id not in x_team_ids]
            missing = list(x_team_ids - present)
            if len(wrong) == 1 and len(missing) == 1:
                pull_swaps.append((wrong[0], wrong[0].team_id, missing[0], hook_name))
            elif wrong:
                self.stdout.write(self.style.WARNING(
                    f"  {hook_name}: ambiguous wrong/missing teams; wrong={[p.team_id for p in wrong]} missing={missing} (skipping swap)"))

        # ---- X pull distances -----------------------------------------------
        # Apply planned swaps in-memory so distance lookup finds the right pull.
        swapped_team = {p.pull_id: new for p, _, new, _ in pull_swaps}
        plan_pulls = []   # (pull_obj, team, hook_name, distance)
        missing_pull = []
        for row in rows:
            team = match_x(cell(row, 0))
            if team is None:
                continue
            for hook_name, dist_col in XTEAM_PULL_DIST:
                dist = _safe_float(cell(row, dist_col))
                if dist is None or dist == 0:
                    continue
                hook = hooks.get(hook_name)
                pull = None
                if hook:
                    for p in Pull.objects.filter(event_id=event_id, hook_id=hook.hook_id):
                        eff_team = swapped_team.get(p.pull_id, p.team_id)
                        if eff_team == team.team_id:
                            pull = p
                            break
                if pull is None:
                    missing_pull.append((team.team_name, hook_name))
                    continue
                plan_pulls.append((pull, team, hook_name, dist))

        # ---- Report ----------------------------------------------------------
        self.stdout.write("\n--- X category & subcategory scores ---")
        for cat_name, *_ in XTEAM_CATEGORIES:
            p = plan[cat_name]
            subs = ", ".join(f"{n}({len(v)})" for n, _, v in p["subs"])
            self.stdout.write(f"  {cat_name:<24} totals: {len(p['totals'])} teams   subcats: {subs}")

        self.stdout.write("\n--- X pull record fix (event_teams is source of truth) ---")
        if pull_swaps:
            for pull, old, new, hook_name in pull_swaps:
                self.stdout.write(f"  {hook_name}: pull_id={pull.pull_id} team {old} -> {new}")
        else:
            self.stdout.write("  none needed")

        self.stdout.write("\n--- X pull distances ---")
        for pull, team, hook_name, dist in plan_pulls:
            self.stdout.write(f"  {team.team_name:<28} {hook_name:<20} {dist:.2f} ft (pull_id={pull.pull_id})")
        if missing_pull:
            self.stdout.write(self.style.WARNING(f"  No matching Pull row for: {missing_pull}"))

        if unmatched:
            self.stdout.write(self.style.WARNING("\nUnmatched names (skipped): " + "; ".join(sorted(unmatched))))

        if not commit:
            self.stdout.write(self.style.NOTICE("\nDRY-RUN complete. No DB changes. Re-run with --commit to write."))
            return

        # ---- Execute ---------------------------------------------------------
        now = timezone.now()
        with transaction.atomic():
            for cat_name, *_ in XTEAM_CATEGORIES:
                p = plan[cat_name]
                max_pts, order = p["cfg"]
                cat, _ = ScoreCategory.objects.get_or_create(category_name=cat_name)
                inst, _ = ScoreCategoryInstance.objects.update_or_create(
                    event=event, score_category=cat,
                    defaults={"max_points": max_pts, "released": True, "display_order": order})
                for team, v in p["totals"].items():
                    ScoreCategoryScore.objects.update_or_create(
                        team=team, category_instance=inst, defaults={"score": v})
                for sub_name, sub_max, vals in p["subs"]:
                    sub, _ = ScoreSubCategory.objects.get_or_create(subcategory_name=sub_name)
                    sub_inst, _ = ScoreSubCategoryInstance.objects.update_or_create(
                        event=event, score_subcategory=sub, category_instance=inst,
                        defaults={"max_points": sub_max, "released": True})
                    for team, v in vals.items():
                        ScoreSubCategoryScore.objects.update_or_create(
                            team=team, subcategory=sub_inst, defaults={"score": v})

            for pull, old, new, hook_name in pull_swaps:
                pull.team_id = new
                pull.updated_by_source = "import_2026"
                pull.save(update_fields=["team_id", "updated_by_source"])

            for pull, team, hook_name, dist in plan_pulls:
                pull.final_distance = dist
                pull.state = "COMPLETED"
                pull.updated_by_source = "import_2026"
                pull.save(update_fields=["final_distance", "state", "updated_by_source"])

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
            f"\nCOMMIT complete: X scores written, {len(pull_swaps)} pull(s) reassigned, "
            f"{len(plan_pulls)} X pull distances set, {updated} EventTeam totals recomputed."))
