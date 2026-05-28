import pickle
import re
import time

import gspread
from celery import shared_task
from django.conf import settings
from django.db import transaction

from techin.models import (
    EventTractorRuleStatus,
    TechinCategoryInstance,
    TechinRuleInstance,
)
from events.models import TractorEvent, Team


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def compute_status(line: list[str]) -> int:
    # Cells are read starting at column C, so:
    #   C=line[0] content, D=line[1] pass, E=line[2] fail, F=line[3] corrected
    pass_check = len(line) > 1 and line[1].strip() != ""
    fail_check = len(line) > 2 and line[2].strip() != ""
    corrected_check = len(line) > 3 and line[3].strip() != ""
    return 3 if pass_check else 2 if corrected_check else 1 if fail_check else 0


def _load_x_team_map():
    """Map each A-team id to its X-team counterpart, plus the set of X-team ids.

    X scored workbooks name their worksheet tabs after the school (i.e. the
    A-team name), so scraping an X category resolves to the A team and then
    swaps in the X team here. Teams are paired by team_number: an X team like
    '15X' (or '26 X') pairs with the A team '15'.
    """
    a_by_number = {}
    x_teams = []
    for t in Team.objects.all().values("team_id", "team_number", "team_class_id"):
        number = (t["team_number"] or "").strip()
        if t["team_class_id"] == 2:
            x_teams.append((t["team_id"], number))
        else:
            a_by_number[number] = t["team_id"]

    a_to_x = {}
    x_ids = set()
    for x_id, x_number in x_teams:
        x_ids.add(x_id)
        base = re.sub(r"\s*[xX]\s*$", "", x_number).strip()
        a_id = a_by_number.get(base)
        if a_id is not None:
            a_to_x[a_id] = x_id
    return a_to_x, x_ids


def _load_team_resolver():
    """Resolve a worksheet tab title to a team_id.

    Primary source is the maintained alias pickle (handles abbreviations and
    alternate spellings). Falls back to exact DB team names.
    """
    alias = {}
    path = getattr(settings, "TECHIN_TEAM_DICT_PATH", None)
    if path:
        try:
            with open(path, "rb") as fh:
                alias = pickle.load(fh)
        except (OSError, pickle.PickleError):
            alias = {}
    db_names = {t.team_name: t.team_id for t in Team.objects.all()}

    def resolve(title: str):
        return alias.get(title) or db_names.get(title)

    return resolve


@shared_task
def ping():
    return "pong"


@shared_task(bind=True, name="techin.scrape_tech_in_task", autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def scrape_tech_in_task(self, event_id: int = 26, sheet_names: list[str] | None = None) -> dict:
    """Sync rule statuses from the per-event category workbooks into MySQL.

    Sheet keys are read from each event's TechinCategoryInstance, and rule rows
    are matched by normalized rule content (column C). Content is used rather
    than the column-G checklist number because the rule-source workbook and the
    team scoring workbooks number rules independently. Pass sheet_names (e.g.
    ["Overall_Sheet"]) to limit the run to specific category sheets while others
    are still being filled in.
    """
    gc = gspread.service_account(filename=settings.GSPREAD_SERVICE_ACCOUNT_JSON)
    resolve_team = _load_team_resolver()
    a_to_x, x_team_ids = _load_x_team_map()

    cats = (
        TechinCategoryInstance.objects
        .filter(event_id=event_id)
        .exclude(sheet_key="")
        .select_related("rule_category")
    )
    if sheet_names:
        cats = cats.filter(sheet_name__in=sheet_names)

    tractor_event_by_team = {
        t["team_id"]: t["tractor_event_id"]
        for t in TractorEvent.objects.filter(event_id=event_id).values("team_id", "tractor_event_id")
    }

    totals = {
        "event_id": event_id,
        "sheets": [],
        "rows_upserted": 0,
        "skipped_teams": 0,
        "missing_rules": 0,
        "bad_tractor_events": 0,
    }

    for ci in cats:
        is_x_category = ci.team_class_id == 2
        # normalized rule content -> (rule_id, rule_instance_id) for this category
        rule_lookup = {}
        rinsts = (
            TechinRuleInstance.objects
            .filter(event_id=event_id, subcategory_instance__category_instance=ci)
            .select_related("rule")
        )
        for ri in rinsts:
            rule_lookup[_norm(ri.rule_content)] = (ri.rule_id, ri.rule_instance_id)

        workbook = gc.open_by_key(ci.sheet_key)
        pending = []

        for sheet in workbook.worksheets():
            team_id = resolve_team(sheet.title)
            if team_id is None:
                totals["skipped_teams"] += 1
                continue
            if is_x_category and team_id not in x_team_ids:
                # Tab is named after the A team; swap in its X counterpart.
                team_id = a_to_x.get(team_id)
                if team_id is None:
                    totals["skipped_teams"] += 1
                    continue
            tractor_event_id = tractor_event_by_team.get(team_id)
            if tractor_event_id is None:
                totals["bad_tractor_events"] += 1
                continue

            cell_range = "C10:L300"
            data = None
            for _ in range(5):
                try:
                    data = sheet.get(cell_range)
                    break
                except Exception:
                    time.sleep(0.5)
            if data is None:
                continue

            for line in data:
                content = line[0].strip() if len(line) > 0 else ""
                if not content or content.upper().startswith("NOTE"):
                    continue
                hit = rule_lookup.get(_norm(content))
                if not hit:
                    totals["missing_rules"] += 1
                    continue
                rule_id, rule_instance_id = hit
                pending.append(
                    EventTractorRuleStatus(
                        event_tractor_id=tractor_event_id,
                        rule_id=rule_id,
                        rule_instance_id=rule_instance_id,
                        status=compute_status(line),
                    )
                )

        upserted = 0
        if pending:
            with transaction.atomic():
                for i in range(0, len(pending), 1000):
                    chunk = pending[i:i + 1000]
                    # MySQL uses ON DUPLICATE KEY UPDATE against the existing
                    # (event_tractor_id, rule_id) unique key; it does not accept
                    # an explicit unique_fields list.
                    EventTractorRuleStatus.objects.bulk_create(
                        chunk,
                        update_conflicts=True,
                        update_fields=["status", "rule_instance"],
                    )
                    upserted += len(chunk)

        totals["rows_upserted"] += upserted
        totals["sheets"].append({"sheet_name": ci.sheet_name, "rows_upserted": upserted})

    return totals
