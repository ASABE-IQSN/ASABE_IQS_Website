"""
Import 2006 IQS results from historical score sheets.

2006 has a unique category structure — different max points and a "Tech Time"
penalty category not found in other years:
  Written Design:    500  (same as later years)
  Oral Presentation: 500  (same)
  Design Judging:    300  (later years: 420)
  Tractor Pull:      800  (same; labeled "Performance Competition")
  Maneuverability:   125  (later years: 100)
  Tech Time:           0  (penalty: 0 if passed on time, -100 if not)

30 teams in the source. Tennessee Tech University is not in the DB and is skipped.

Usage:
    python manage.py import_2006_results              # dry-run
    python manage.py import_2006_results --commit     # write to DB
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
    "illinois, university of": "university of illinois",
    "kentucky, university of": "university of kentucky",
    "laval, université": "université laval",
    "manitoba, university of": "university of manitoba",
    "minnesota, university of": "university of minnesota",
    "missouri, university of": "university of missouri",
    "nebraska, university of": "university of nebraska",
    "arizona, university of": "university of arizona",
    "saskatchawen, university of": "university of saskatchewan",
    "saskatchewan, university of": "university of saskatchewan",
    "wisconsin - madison, university of": "university of wisconsin-madison",
    "wisconsin - platteville, university of": "university of wisconsin-platteville",
    "wisconsin - river falls, university of": "university of wisconsin - river falls",
    "wyoming, university of": "university of wyoming",
    "purdue university - calumet": "purdue university-calumet",
}

# 2006-specific categories with their max points.
# Tech Time is a penalty: 0 = passed on time, -100 = failed tech inspection timing.
CATEGORIES = [
    ("Design Judging",    300, 2),
    ("Written Design",    500, 3),
    ("Oral Presentation", 500, 5),
    ("Tractor Pull",      800, 6),
    ("Maneuverability",   125, 7),
    ("Tech Time",           0, 9),  # display_order 9 to avoid collision
]

SKIPPED_TEAMS = ["Tennessee Tech University"]

# Keyed by DB team name (lowercased). Scores from 2006 source PDF.
SCORES = {
    "kansas state university": {
        "Written Design": 500.0, "Oral Presentation": 500.0, "Design Judging": 272.2,
        "Tractor Pull": 785.6, "Maneuverability": 115.9, "Tech Time": 0.0,
    },
    "université laval": {
        "Written Design": 448.7, "Oral Presentation": 469.0, "Design Judging": 286.4,
        "Tractor Pull": 778.7, "Maneuverability": 124.0, "Tech Time": 0.0,
    },
    "university of wisconsin-madison": {
        "Written Design": 475.3, "Oral Presentation": 447.2, "Design Judging": 274.8,
        "Tractor Pull": 781.7, "Maneuverability": 123.0, "Tech Time": 0.0,
    },
    "university of nebraska": {
        "Written Design": 475.0, "Oral Presentation": 486.3, "Design Judging": 267.2,
        "Tractor Pull": 689.8, "Maneuverability": 115.9, "Tech Time": 0.0,
    },
    "cal poly state university": {
        "Written Design": 471.7, "Oral Presentation": 457.3, "Design Judging": 300.0,
        "Tractor Pull": 725.2, "Maneuverability": 75.0, "Tech Time": 0.0,
    },
    "university of kentucky": {
        "Written Design": 436.3, "Oral Presentation": 403.9, "Design Judging": 273.3,
        "Tractor Pull": 690.0, "Maneuverability": 109.9, "Tech Time": 0.0,
    },
    "iowa state university": {
        "Written Design": 480.0, "Oral Presentation": 395.5, "Design Judging": 281.5,
        "Tractor Pull": 622.7, "Maneuverability": 98.8, "Tech Time": 0.0,
    },
    "purdue": {
        "Written Design": 441.0, "Oral Presentation": 408.3, "Design Judging": 252.7,
        "Tractor Pull": 772.5, "Maneuverability": 0.0, "Tech Time": 0.0,
    },
    "modesto junior college": {
        "Written Design": 412.0, "Oral Presentation": 447.5, "Design Judging": 275.5,
        "Tractor Pull": 604.7, "Maneuverability": 82.7, "Tech Time": 0.0,
    },
    "university of wisconsin - river falls": {
        "Written Design": 412.3, "Oral Presentation": 470.2, "Design Judging": 249.5,
        "Tractor Pull": 559.2, "Maneuverability": 106.9, "Tech Time": 0.0,
    },
    "university of saskatchewan": {
        "Written Design": 401.3, "Oral Presentation": 399.1, "Design Judging": 250.5,
        "Tractor Pull": 700.6, "Maneuverability": 119.0, "Tech Time": -100.0,
    },
    "north carolina state university": {
        "Written Design": 334.3, "Oral Presentation": 450.5, "Design Judging": 266.8,
        "Tractor Pull": 565.9, "Maneuverability": 83.7, "Tech Time": 0.0,
    },
    "auburn university": {
        "Written Design": 404.3, "Oral Presentation": 388.8, "Design Judging": 240.8,
        "Tractor Pull": 570.6, "Maneuverability": 90.7, "Tech Time": 0.0,
    },
    "michigan state": {
        "Written Design": 285.7, "Oral Presentation": 308.8, "Design Judging": 234.8,
        "Tractor Pull": 722.9, "Maneuverability": 125.0, "Tech Time": 0.0,
    },
    "texas a&m university": {
        "Written Design": 391.3, "Oral Presentation": 313.4, "Design Judging": 256.4,
        "Tractor Pull": 584.9, "Maneuverability": 125.0, "Tech Time": 0.0,
    },
    "north dakota state university": {
        "Written Design": 412.0, "Oral Presentation": 372.2, "Design Judging": 233.2,
        "Tractor Pull": 677.9, "Maneuverability": 75.0, "Tech Time": -100.0,
    },
    "ohio state": {
        "Written Design": 456.3, "Oral Presentation": 452.1, "Design Judging": 262.6,
        "Tractor Pull": 407.2, "Maneuverability": 83.7, "Tech Time": 0.0,
    },
    "university of arizona": {
        "Written Design": 354.0, "Oral Presentation": 420.0, "Design Judging": 251.0,
        "Tractor Pull": 646.0, "Maneuverability": 87.7, "Tech Time": -100.0,
    },
    "university of illinois": {
        "Written Design": 488.0, "Oral Presentation": 488.2, "Design Judging": 254.6,
        "Tractor Pull": 315.6, "Maneuverability": 115.9, "Tech Time": -100.0,
    },
    "university of minnesota": {
        "Written Design": 325.3, "Oral Presentation": 451.5, "Design Judging": 263.7,
        "Tractor Pull": 368.3, "Maneuverability": 116.9, "Tech Time": 0.0,
    },
    "purdue university-calumet": {
        "Written Design": 277.0, "Oral Presentation": 379.1, "Design Judging": 244.6,
        "Tractor Pull": 466.0, "Maneuverability": 104.8, "Tech Time": 0.0,
    },
    "university of wisconsin-platteville": {
        "Written Design": 273.7, "Oral Presentation": 402.4, "Design Judging": 223.9,
        "Tractor Pull": 525.4, "Maneuverability": 75.0, "Tech Time": -100.0,
    },
    "university of manitoba": {
        "Written Design": 313.7, "Oral Presentation": 382.1, "Design Judging": 248.7,
        "Tractor Pull": 355.7, "Maneuverability": 98.8, "Tech Time": 0.0,
    },
    "penn state university": {
        "Written Design": 343.0, "Oral Presentation": 432.5, "Design Judging": 261.5,
        "Tractor Pull": 277.0, "Maneuverability": 125.0, "Tech Time": -100.0,
    },
    "nicholls state university": {
        "Written Design": 316.3, "Oral Presentation": 327.7, "Design Judging": 253.5,
        "Tractor Pull": 317.0, "Maneuverability": 124.0, "Tech Time": 0.0,
    },
    "southern illinois university": {
        "Written Design": 186.0, "Oral Presentation": 340.4, "Design Judging": 217.5,
        "Tractor Pull": 547.4, "Maneuverability": 0.0, "Tech Time": -100.0,
    },
    "oklahoma state university": {
        "Written Design": 453.3, "Oral Presentation": 410.8, "Design Judging": 265.1,
        "Tractor Pull": 0.0, "Maneuverability": 0.0, "Tech Time": 0.0,
    },
    "university of missouri": {
        "Written Design": 0.0, "Oral Presentation": 0.0, "Design Judging": 0.0,
        "Tractor Pull": 0.0, "Maneuverability": 0.0, "Tech Time": -100.0,
    },
    "university of wyoming": {
        "Written Design": 0.0, "Oral Presentation": 0.0, "Design Judging": 0.0,
        "Tractor Pull": 0.0, "Maneuverability": 0.0, "Tech Time": -100.0,
    },
}


class Command(BaseCommand):
    help = "Import 2006 IQS historical results (hardcoded from score sheets)."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, default=6, help="Event id (default 6)")
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
            f"import_2006_results — event {event_id} ({event}) — {mode}"))
        self.stdout.write(f"\nSkipped teams (not in DB): {', '.join(SKIPPED_TEAMS)}")
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
