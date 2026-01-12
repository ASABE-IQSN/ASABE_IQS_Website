import time
import gspread
from celery import shared_task
from django.conf import settings
from django.db import transaction

from techin.models import RuleCategory, EventTractorRuleStatus
from events.models import TractorEvent
import resources.dict_loader as dict_loader


def compute_status(line: list[str]) -> int:
    # line indexes based on your script:
    # pass_check=line[1], fail_check=line[2], corrected_check=line[3]
    pass_check = len(line) > 1 and line[1] != ""
    fail_check = len(line) > 2 and line[2] != ""
    corrected_check = len(line) > 3 and line[3] != ""
    return 3 if pass_check else 2 if corrected_check else 1 if fail_check else 0


@shared_task
def ping():
    return "pong"

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def scrape_tech_in_task(self, event_id: int = 25) -> dict:
    """
    Periodic task: sync rule statuses from Google Sheets into MySQL via Django ORM.
    """

    # Better than hardcoding a relative path: store this in settings / env
    gc = gspread.service_account(filename=settings.GSPREAD_SERVICE_ACCOUNT_JSON)

    rule_categories = RuleCategory.objects.exclude(sheet_name__isnull=True).exclude(sheet_name="")

    created_or_updated = 0
    skipped_teams = 0
    missing_rules = 0
    bad_tractor_events = 0

    for cat in rule_categories:
        workbook = gc.open_by_key(cat.sheet_key)

        # Prefetch tractor events for this event once, for quick lookup
        tractor_events = TractorEvent.objects.filter(event_id=event_id).values("team_id", "tractor_event_id")
        tractor_event_by_team = {t["team_id"]: t["tractor_event_id"] for t in tractor_events}

        pending = []

        for sheet in workbook.worksheets():
            team_id = dict_loader.team_dict.get(sheet.title)
            if team_id is None:
                skipped_teams += 1
                continue

            tractor_event_id = tractor_event_by_team.get(team_id)
            if tractor_event_id is None:
                bad_tractor_events += 1
                continue

            row_start = 10
            cell_range = f"C{row_start}:L300"

            data = None
            while not data:
                try:
                    data = sheet.get(cell_range)
                except Exception:
                    # gspread / Google can hiccup; tiny sleep avoids tight-looping
                    time.sleep(0.5)

            for row_iter, line in enumerate(data):
                row_number = row_start + row_iter

                if len(line) > 0 and line[0] != "":
                    rule_id = dict_loader.sheet_rule_dict.get((cat.sheet_name, row_number))
                    if not rule_id:
                        missing_rules += 1
                        continue

                    status = compute_status(line)

                    pending.append(
                        EventTractorRuleStatus(
                            event_tractor_id=tractor_event_id,  # works if FK db_column is event_tractor_id
                            rule_id=rule_id,
                            status=status,
                        )
                    )

        # Bulk upsert per category
        if pending:
            with transaction.atomic():
                for i in range(0, len(pending), 1000):
                    chunk = pending[i:i+1000]
                    EventTractorRuleStatus.objects.bulk_create(
                        chunk,
                        update_conflicts=True,
                        update_fields=["status"],
                        unique_fields=["event_tractor", "rule_id"],
                    )
                    created_or_updated += len(chunk)

    return {
        "event_id": event_id,
        "rows_upserted": created_or_updated,
        "skipped_teams": skipped_teams,
        "missing_rules": missing_rules,
        "bad_tractor_events": bad_tractor_events,
    }