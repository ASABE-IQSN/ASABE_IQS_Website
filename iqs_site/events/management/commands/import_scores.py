"""
Management command to import scores from Google Sheet CSV exports.

Usage:
    python manage.py import_scores <event_id> <csv_dir>

The csv_dir should contain the tab exports from the master score spreadsheet.
"""
import csv
import os
from django.core.management.base import BaseCommand, CommandError
from events.models import (
    Event, Team, EventTeam,
    ScoreCategory, ScoreCategoryInstance, ScoreCategoryScore,
    ScoreSubCategory, ScoreSubCategoryInstance, ScoreSubCategoryScore,
)

# Maps a substring of the CSV filename to category config.
# Each entry: (category_name, max_points, header_rows_to_skip, category_total_col, subcategories)
# subcategories is a list of (subcategory_name, data_col_index, max_points)
CSV_CONFIGS = [
    {
        "keyword": "Weight-In Bonus",
        "category": "Weight-In Bonus",
        "max_points": 100,
        "skip_rows": 4,
        "total_col": 2,
        "subcategories": [],
        "display_order": 1,
    },
    {
        "keyword": "Design Judging",
        "category": "Design Judging",
        "max_points": 420,
        "skip_rows": 4,
        "total_col": 2,
        "subcategories": [
            ("Serviceability", 11, 70),
            ("Manufacturability", 19, 70),
            ("Safety", 27, 70),
            ("Ergonomics", 35, 70),
            ("Test and Development", 43, 70),
        ],
        "display_order": 2,
    },
    {
        "keyword": "Written Design",
        "category": "Written Design",
        "max_points": 500,
        "skip_rows": 4,
        "total_col": 2,
        "subcategories": [
            ("Criteria & Objectives", 10, 5),
            ("Format", 17, 15),
            ("Design Details", 24, 250),
            ("FMEA", 31, 20),
            ("Testing & Development", 38, 70),
            ("Design Log", 45, 20),
            ("Judges Discretion", 52, 20),
            ("Cost Strategy", 59, 50),
            ("Cost Analysis", 66, 50),
        ],
        "display_order": 3,
    },
    {
        "keyword": "Defense of Design",
        "category": "Defense of Design",
        "max_points": 85,
        "skip_rows": 4,
        "total_col": 2,
        "subcategories": [
            ("Design Goal", 10, 20),
            ("Design Considerations", 17, 20),
            ("Company/Project Lim.", 24, 15),
            ("Judges Discretion", 31, 15),
            ("Video Submission", 33, 15),
        ],
        "display_order": 4,
    },
    {
        "keyword": "Presentation Points",
        "category": "Oral Presentation",
        "max_points": 500,
        "skip_rows": 4,
        "total_col": 2,
        "subcategories": [],
        "display_order": 5,
    },
    {
        "keyword": "Tractor Pull",
        "category": "Tractor Pull",
        "max_points": 600,
        "skip_rows": 4,
        "total_col": 2,
        "subcategories": [
            ("1100 lb #1", 3, 200),
            ("1600 lb #1", 5, 200),
            ("1600 lb #2", 7, 200),
        ],
        "display_order": 6,
    },
    {
        "keyword": "Maneuverability",
        "category": "Maneuverability",
        "max_points": 100,
        "skip_rows": 4,
        "total_col": 2,
        "subcategories": [],
        "display_order": 7,
    },
    {
        "keyword": "Durability",
        "category": "Durability",
        "max_points": 200,
        "skip_rows": 4,
        "total_col": 2,
        "subcategories": [],
        "display_order": 8,
    },
]


# Maps CSV team names (lowercased) to DB team names (lowercased) when they differ.
NAME_ALIASES = {
    "purdue university": "purdue",
    "université laval": "université laval",
    "universite laval": "université laval",
    "university of laval": "université laval",
    "university of tennessee - martin": "university of tennessee martin",
    "university of wisconsin madison": "university of wisconsin-madison",
    "university of wisconsin platteville": "university of wisconsin-platteville",
}


def _safe_float(val):
    """Convert a CSV value to float, returning None if blank/non-numeric."""
    if val is None:
        return None
    s = str(val).strip().rstrip("*").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


class Command(BaseCommand):
    help = "Import scores from Google Sheet CSV exports into the database."

    def add_arguments(self, parser):
        parser.add_argument("event_id", type=int, help="Event ID to import scores for")
        parser.add_argument("csv_dir", type=str, help="Directory containing the CSV files")

    def handle(self, *args, **options):
        event_id = options["event_id"]
        csv_dir = options["csv_dir"]

        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            raise CommandError(f"Event with id {event_id} does not exist.")

        if not os.path.isdir(csv_dir):
            raise CommandError(f"Directory not found: {csv_dir}")

        # Pre-load all teams by normalized name
        teams_by_name = {
            t.team_name.strip().lower(): t
            for t in Team.objects.all()
        }

        # Find and process each CSV
        csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
        matched_configs = []
        for config in CSV_CONFIGS:
            for fname in csv_files:
                if config["keyword"].lower() in fname.lower():
                    matched_configs.append((config, os.path.join(csv_dir, fname)))
                    break
            else:
                self.stdout.write(
                    self.style.WARNING(f"No CSV found for category: {config['category']}")
                )

        if not matched_configs:
            raise CommandError("No matching CSV files found.")

        total_cat_scores = 0
        total_sub_scores = 0

        for config, filepath in matched_configs:
            self.stdout.write(f"Processing {config['category']} from {os.path.basename(filepath)}...")

            # Get or create ScoreCategory and ScoreCategoryInstance
            score_cat, _ = ScoreCategory.objects.get_or_create(
                category_name=config["category"]
            )
            cat_instance, _ = ScoreCategoryInstance.objects.update_or_create(
                event=event,
                score_category=score_cat,
                defaults={
                    "max_points": config["max_points"],
                    "released": True,
                    "display_order": config["display_order"],
                },
            )

            # Get or create ScoreSubCategoryInstances
            sub_instances = {}
            for sub_name, col_idx, sub_max in config["subcategories"]:
                sub_cat, _ = ScoreSubCategory.objects.get_or_create(
                    subcategory_name=sub_name
                )
                sub_inst, _ = ScoreSubCategoryInstance.objects.update_or_create(
                    event=event,
                    score_subcategory=sub_cat,
                    category_instance=cat_instance,
                    defaults={
                        "max_points": sub_max,
                        "released": True,
                    },
                )
                sub_instances[col_idx] = sub_inst

            # Parse CSV
            with open(filepath, encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)

            data_rows = rows[config["skip_rows"]:]

            for row in data_rows:
                team_name_raw = row[0].strip() if row else ""
                if not team_name_raw:
                    continue

                normalized = team_name_raw.lower()
                normalized = NAME_ALIASES.get(normalized, normalized)
                team = teams_by_name.get(normalized)
                if team is None:
                    self.stdout.write(
                        self.style.WARNING(f"  Unmatched team name: '{team_name_raw}'")
                    )
                    continue

                # Category total score
                cat_val = _safe_float(row[config["total_col"]] if len(row) > config["total_col"] else None)
                if cat_val is not None:
                    ScoreCategoryScore.objects.update_or_create(
                        team=team,
                        category_instance=cat_instance,
                        defaults={"score": cat_val},
                    )
                    total_cat_scores += 1

                # Subcategory scores
                for col_idx, sub_inst in sub_instances.items():
                    sub_val = _safe_float(row[col_idx] if len(row) > col_idx else None)
                    ScoreSubCategoryScore.objects.update_or_create(
                        team=team,
                        subcategory=sub_inst,
                        defaults={"score": sub_val},
                    )
                    total_sub_scores += 1

            self.stdout.write(self.style.SUCCESS(f"  Done: {config['category']}"))

        # Update EventTeam.total_score for each team as sum of all category scores
        self.stdout.write("Updating EventTeam total scores...")
        updated = 0
        for et in EventTeam.objects.filter(event=event).select_related("team"):
            total = sum(
                cs.score
                for cs in ScoreCategoryScore.objects.filter(
                    team=et.team, category_instance__event=event
                )
                if cs.score is not None
            )
            et.total_score = round(total, 2)
            et.save(update_fields=["total_score"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nImport complete: {total_cat_scores} category scores, "
                f"{total_sub_scores} subcategory scores, "
                f"{updated} EventTeam totals updated."
            )
        )
