from collections import OrderedDict

from django.contrib.auth.models import User
from django.db.models import Prefetch, Subquery, OuterRef, Case, When, Value, IntegerField
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from events.models import (
    Event, Team, TeamClass, Tractor, TractorEvent, Hook, Pull, PullData,
    EventTeam, EventTeamPhoto, TractorMedia, TractorInfo,
    DurabilityRun, DurabilityData, ManeuverabilityRun,
    PerformanceEventMedia, TeamInfo,
    ScoreCategoryInstance, ScoreSubCategoryInstance, ScoreSubCategoryScore, Report
)
from schedule.models import ScheduleItem
from techin.models import (
    RuleCategory, RuleSubCategory, Rule, EventTractorRuleStatus,
)
from events.permissions import can_edit_team

from .serializers import (
    EventListSerializer, EventDetailSerializer, EventTeamSerializer,
    ScheduleItemSerializer, HookSerializer,
    TeamListSerializer, TeamDetailSerializer, TeamClassSerializer,
    TractorListSerializer, TractorDetailSerializer,
    PullListSerializer, PullDetailSerializer,
    DurabilityRunListSerializer, DurabilityRunDetailSerializer,
    ManeuverabilityRunListSerializer, ManeuverabilityRunDetailSerializer,
    EventTeamPhotoSerializer,
    UserSerializer, RegisterSerializer,
)
from .pagination import StandardPagination


# ── Events ───────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def event_list(request):
    events = (
        Event.objects.all()
        .order_by("-event_datetime")
    )
    serializer = EventListSerializer(events, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def event_detail(request, event_id):
    event = get_object_or_404(
        Event.objects.prefetch_related("hooks"),
        pk=event_id,
    )
    serializer = EventDetailSerializer(event)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def event_teams(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    ets = (
        EventTeam.objects
        .filter(event=event)
        .select_related("team__team_class")
        .order_by("-total_score")
    )
    serializer = EventTeamSerializer(ets, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def event_schedule(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    items = (
        ScheduleItem.objects
        .filter(event=event)
        .select_related("type", "team")
        .order_by("datetime")
    )
    serializer = ScheduleItemSerializer(items, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def event_results(request, event_id):
    """Full scoring breakdown: categories -> subcategories -> team scores."""
    event = get_object_or_404(Event, pk=event_id)

    cat_instances = (
        ScoreCategoryInstance.objects
        .filter(event=event, released=True)
        .select_related("score_category")
        .order_by("score_category__category_name")
    )

    result = []
    for ci in cat_instances:
        subcat_instances = (
            ScoreSubCategoryInstance.objects
            .filter(event=event)
            .select_related("score_subcategory")
        )
        subcats = []
        for si in subcat_instances:
            scores = (
                ScoreSubCategoryScore.objects
                .filter(subcategory=si)
                .select_related("team")
                .order_by("team__team_name")
            )
            subcats.append({
                "subcategory_name": si.score_subcategory.subcategory_name,
                "max_points": si.max_points,
                "released": si.released,
                "scores": [
                    {"team_id": s.team_id, "team_name": s.team.team_name,
                     "score_id": s.score_subcategory_score_id}
                    for s in scores
                ],
            })
        result.append({
            "category_name": ci.score_category.category_name,
            "max_points": ci.max_points,
            "subcategories": subcats,
        })

    return Response({"event_id": event_id, "categories": result})


@api_view(["GET"])
@permission_classes([AllowAny])
def event_pulls(request, event_id):
    """All pulls for an event, grouped by hook."""
    event = get_object_or_404(Event, pk=event_id)
    hooks = (
        Hook.objects
        .filter(event=event)
        .prefetch_related(
            Prefetch(
                "pulls",
                queryset=Pull.objects.select_related("team", "tractor")
                    .order_by("-final_distance"),
            )
        )
    )

    result = []
    for hook in hooks:
        pulls = list(hook.pulls.all())
        result.append({
            "hook_id": hook.hook_id,
            "hook_name": hook.hook_name,
            "pulls": PullListSerializer(pulls, many=True).data,
        })

    return Response(result)


@api_view(["GET"])
@permission_classes([AllowAny])
def event_durability(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    runs = (
        DurabilityRun.objects
        .filter(event=event)
        .select_related("team", "tractor")
        .order_by("-total_laps", "run_order")
    )

    # Assign ranks like the Django view
    ranked = []
    rank = 0
    for r in runs:
        data = DurabilityRunListSerializer(r).data
        if r.total_laps is not None and r.total_laps > 0:
            rank += 1
            data["rank"] = rank
        else:
            data["rank"] = None
        ranked.append(data)

    return Response(ranked)


@api_view(["GET"])
@permission_classes([AllowAny])
def event_maneuverability(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    runs = (
        ManeuverabilityRun.objects
        .filter(event=event)
        .select_related("team")
        .order_by("run_order")
    )
    serializer = ManeuverabilityRunListSerializer(runs, many=True)
    return Response(serializer.data)


# ── Teams ────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def team_list(request):
    """All teams grouped by class."""
    team_qs = Team.objects.select_related("team_class").order_by("team_name")
    team_classes = (
        TeamClass.objects
        .prefetch_related(
            Prefetch("teams", queryset=team_qs)
        )
        .order_by("name")
    )

    result = []
    for tc in team_classes:
        teams = TeamListSerializer(tc.teams.all(), many=True).data
        result.append({
            "team_class_id": tc.team_class_id,
            "name": tc.name,
            "teams": teams,
        })

    # Add unclassified teams
    unclassified = Team.objects.filter(team_class__isnull=True).order_by("team_name")
    if unclassified.exists():
        result.append({
            "team_class_id": None,
            "name": "Unclassified",
            "teams": TeamListSerializer(unclassified, many=True).data,
        })

    return Response(result)


@api_view(["GET"])
@permission_classes([AllowAny])
def team_detail(request, team_id):
    team = get_object_or_404(
        Team.objects.select_related("team_class"),
        pk=team_id,
    )
    data = TeamDetailSerializer(team).data

    # Add event history
    event_teams = (
        EventTeam.objects
        .filter(team=team)
        .select_related("event")
        .order_by("-event__event_datetime")
    )
    data["event_history"] = [
        {
            "event_id": et.event_id,
            "event_name": et.event.event_name,
            "event_datetime": et.event.event_datetime,
            "total_score": et.total_score,
        }
        for et in event_teams
    ]

    # Add photos
    photos = (
        EventTeamPhoto.objects
        .filter(event_team__team=team, approved=True)
        .select_related("event_team__event")
        .order_by("-event_team_photo_id")
    )
    data["photos"] = EventTeamPhotoSerializer(photos, many=True).data

    # Hero photo
    hero = photos.filter(official=True).first()
    if not hero and photos.exists():
        hero = photos.first()
    data["hero_photo"] = EventTeamPhotoSerializer(hero).data if hero else None

    # Can edit
    data["can_edit"] = can_edit_team(request.user, team) if request.user.is_authenticated else False

    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def team_events(request, team_id):
    team = get_object_or_404(Team, pk=team_id)
    event_teams = (
        EventTeam.objects
        .filter(team=team)
        .select_related("event")
        .order_by("-event__event_datetime")
    )
    data = [
        {
            "event_id": et.event_id,
            "event_name": et.event.event_name,
            "event_datetime": et.event.event_datetime,
            "total_score": et.total_score,
            "event_team_id": et.event_team_id,
        }
        for et in event_teams
    ]
    return Response(data)


# ── Team-Event composite ────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def team_event_detail(request, event_id, team_id):
    team = get_object_or_404(Team, pk=team_id)
    event = get_object_or_404(Event, pk=event_id)

    event_team = (
        EventTeam.objects
        .filter(event=event, team=team)
        .select_related("event", "team")
        .first()
    )

    # Top 3 standings
    top3 = (
        EventTeam.objects
        .filter(event=event)
        .select_related("team")
        .order_by("-total_score")[:3]
    )

    # Pulls
    pulls = (
        Pull.objects
        .filter(event=event, team=team)
        .select_related("hook", "tractor")
        .order_by("hook__hook_name", "pull_id")
    )

    # Durability runs
    durability_runs = (
        DurabilityRun.objects
        .filter(event=event, team=team)
        .select_related("tractor")
        .order_by("run_order")
    )

    # Maneuverability runs
    maneuverability_runs = (
        ManeuverabilityRun.objects
        .filter(event=event, team=team)
        .order_by("run_order")
    )

    # Schedule items
    schedule_items = (
        ScheduleItem.objects
        .filter(event=event, team=team)
        .select_related("type")
        .order_by("datetime")
    )

    # Photos
    photos = []
    if event_team:
        photos = (
            EventTeamPhoto.objects
            .filter(event_team=event_team, approved=True)
            .order_by("event_team_photo_id")
        )

    data = {
        "event": EventListSerializer(event).data,
        "team": TeamListSerializer(team).data,
        "event_team": EventTeamSerializer(event_team).data if event_team else None,
        "top3": EventTeamSerializer(top3, many=True).data,
        "pulls": PullListSerializer(pulls, many=True).data,
        "durability_runs": DurabilityRunListSerializer(durability_runs, many=True).data,
        "maneuverability_runs": ManeuverabilityRunListSerializer(
            maneuverability_runs, many=True).data,
        "schedule_items": ScheduleItemSerializer(schedule_items, many=True).data,
        "photos": EventTeamPhotoSerializer(photos, many=True).data,
    }

    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def team_event_photos(request, event_id, team_id):
    event_team = get_object_or_404(
        EventTeam.objects.select_related("event", "team"),
        event_id=event_id, team_id=team_id,
    )
    photos = (
        EventTeamPhoto.objects
        .filter(event_team=event_team, approved=True)
        .order_by("-event_team_photo_id")
    )
    return Response(EventTeamPhotoSerializer(photos, many=True).data)


# ── Tractors ─────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def tractor_list(request):
    nickname_sq = TractorInfo.objects.filter(
        tractor_id=OuterRef("tractor_id"),
        info_type=TractorInfo.InfoTypes.NICKNAME,
    ).values("info")[:1]

    tractors = (
        Tractor.objects
        .select_related("original_team", "primary_photo")
        .annotate(
            nickname_info=Subquery(nickname_sq),
            has_photo=Case(
                When(primary_photo__isnull=False, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .order_by("has_photo", "original_team", "-year")
    )
    serializer = TractorListSerializer(tractors, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def tractor_detail(request, tractor_id):
    tractor = get_object_or_404(
        Tractor.objects.select_related("original_team", "primary_photo"),
        pk=tractor_id,
    )
    return Response(TractorDetailSerializer(tractor).data)


# ── Pulls ────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def pull_detail(request, pull_id):
    pull = get_object_or_404(
        Pull.objects.select_related("team", "event", "hook", "tractor"),
        pk=pull_id,
    )
    return Response(PullDetailSerializer(pull).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def recompute_pull_etas_view(request, hook_id):
    """Recompute expected_start_time for all SCHEDULED pulls in `hook_id`.

    Runs the task body synchronously so the caller receives the freshly
    written ETAs in the response. Signal-driven invocations use .delay().
    """
    from events.tasks import recompute_pull_etas

    hook = get_object_or_404(Hook, pk=hook_id)
    # Run inline so the caller gets back the freshly written ETAs.
    updated = recompute_pull_etas.apply(args=[hook.hook_id]).get()
    return Response({"hook_id": hook.hook_id, "updated": updated})


# ── Durability ───────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def durability_run_detail(request, run_id):
    run = get_object_or_404(
        DurabilityRun.objects.select_related("team", "event", "tractor"),
        pk=run_id,
    )
    return Response(DurabilityRunDetailSerializer(run).data)


# ── Maneuverability ──────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def maneuverability_run_detail(request, run_id):
    run = get_object_or_404(
        ManeuverabilityRun.objects.select_related("team", "event"),
        pk=run_id,
    )
    return Response(ManeuverabilityRunDetailSerializer(run).data)


# ── Photos ───────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def photo_gallery(request):
    """All approved photos, paginated."""
    paginator = StandardPagination()

    photos = (
        EventTeamPhoto.objects
        .filter(approved=True)
        .select_related("event_team__event", "event_team__team")
        .order_by("-created_at")
    )

    # Optional filters
    event_id = request.query_params.get("event_id")
    team_id = request.query_params.get("team_id")
    if event_id:
        photos = photos.filter(event_team__event_id=event_id)
    if team_id:
        photos = photos.filter(event_team__team_id=team_id)

    page = paginator.paginate_queryset(photos, request)
    serializer = EventTeamPhotoSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# ── Tech Inspection ──────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def techin_overview(request, event_id):
    """Tech inspection overview: all teams with progress per category."""
    event = get_object_or_404(Event, pk=event_id)

    categories = list(
        RuleCategory.objects
        .prefetch_related("subcategories__rules")
        .order_by("rule_category_name")
    )

    tractor_events = list(
        TractorEvent.objects
        .filter(event=event, team__team_class=1)
        .select_related("team")
        .order_by("team__team_name")
    )

    statuses_qs = (
        EventTractorRuleStatus.objects
        .filter(event_tractor__in=tractor_events)
        .select_related("rule")
    )
    status_by_te_rule = {
        (rs.event_tractor_id, rs.rule.rule_id): rs.status
        for rs in statuses_qs
    }

    rows = []
    for te in tractor_events:
        cat_values = []
        for cat in categories:
            total = 0
            completed = 0
            for subcat in cat.subcategories.all():
                for rule in subcat.rules.all():
                    total += 1
                    s = status_by_te_rule.get((te.pk, rule.rule_id))
                    if s in (2, 3):
                        completed += 1
            pct = round((completed / total) * 100) if total > 0 else 0
            cat_values.append({
                "category_name": cat.rule_category_name,
                "percent_complete": pct,
            })

        rows.append({
            "team_id": te.team_id,
            "team_name": te.team.team_name,
            "categories": cat_values,
        })

    return Response({
        "event_id": event_id,
        "category_names": [c.rule_category_name for c in categories],
        "teams": rows,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def techin_team_detail(request, event_id, team_id):
    """Team's tech inspection status by category -> subcategory -> rules."""
    event = get_object_or_404(Event, pk=event_id)
    team = get_object_or_404(Team, pk=team_id)

    if not event.techin_released:
        return Response({"detail": "Tech inspection not released."},
                        status=status.HTTP_404_NOT_FOUND)

    te = get_object_or_404(
        TractorEvent.objects.select_related("team", "event"),
        team=team, event=event,
    )

    categories = (
        RuleCategory.objects
        .prefetch_related("subcategories__rules")
        .order_by("rule_category_name")
    )

    statuses_qs = (
        EventTractorRuleStatus.objects
        .filter(event_tractor=te)
        .select_related("rule")
    )
    status_by_rule = {rs.rule.rule_id: rs.status for rs in statuses_qs}

    STATUS_MAP = {0: "Not Started", 1: "Failed", 2: "Corrected", 3: "Pass"}

    result = []
    for cat in categories:
        cat_total = 0
        cat_done = 0
        subcats = []
        for subcat in cat.subcategories.all():
            rules = []
            sub_total = 0
            sub_done = 0
            for rule in subcat.rules.all():
                s = status_by_rule.get(rule.rule_id, 0)
                rules.append({
                    "rule_id": rule.rule_id,
                    "rule_number": rule.rule_number,
                    "rule_content": rule.rule_content,
                    "status": s,
                    "status_label": STATUS_MAP.get(s, "Unknown"),
                })
                sub_total += 1
                if s in (2, 3):
                    sub_done += 1

            cat_total += sub_total
            cat_done += sub_done
            pct = round((sub_done / sub_total) * 100) if sub_total > 0 else 0
            subcats.append({
                "subcategory_id": subcat.rule_subcategory_id,
                "subcategory_name": subcat.rule_subcategory_name,
                "percent_complete": pct,
                "rules": rules,
            })

        cat_pct = round((cat_done / cat_total) * 100) if cat_total > 0 else 0
        result.append({
            "category_id": cat.rule_category_id,
            "category_name": cat.rule_category_name,
            "percent_complete": cat_pct,
            "subcategories": subcats,
        })

    return Response({
        "event_id": event_id,
        "team_id": team_id,
        "team_name": team.team_name,
        "categories": result,
    })


# ── Auth ─────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def auth_me(request):
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def auth_register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    username = serializer.validated_data["username"]
    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    if User.objects.filter(username=username).exists():
        return Response({"detail": "Username already taken."},
                        status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(email=email).exists():
        return Response({"detail": "Email already registered."},
                        status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_active=False,  # Requires email verification
    )

    # Trigger email verification (reuse existing flow from users app)
    from users.views import send_verification_email
    try:
        send_verification_email(request, user)
    except Exception:
        pass  # Don't fail registration if email fails

    return Response(
        {"detail": "Account created. Check your email to verify."},
        status=status.HTTP_201_CREATED,
    )


# ── Announcer ─────────────────────────────────────────────────────────

REPORT_TYPE_LABELS = {1: "Design Report", 2: "Cost Report", 3: "Design Log"}


def _build_announcer_team_payload(team, event, event_team, rank, tractor, photo_url):
    from compforms.models import FormResponse

    team_infos = TeamInfo.objects.filter(team=team)
    info_map = {ti.info_type: ti.info for ti in team_infos}

    form_responses_data = []
    reports_data = []

    if event_team:
        form_responses = (
            FormResponse.objects
            .filter(event_form__event=event, event_team=event_team)
            .select_related("event_form__form")
            .prefetch_related("answers__question", "event_form__form__form_questions__question")
        )
        for fr in form_responses:
            questions = []
            for fq in fr.event_form.form.form_questions.order_by("order"):
                answer_obj = fr.answers.filter(question=fq.question).first()
                questions.append({
                    "question": fq.question.question_text,
                    "answer": answer_obj.answer if answer_obj else "",
                })
            form_responses_data.append({
                "form_name": fr.event_form.form.name,
                "questions": questions,
            })

        for r in Report.objects.filter(event_team=event_team):
            reports_data.append({
                "report_id": r.report_id,
                "label": REPORT_TYPE_LABELS.get(r.report_type, f"Report {r.report_id}"),
                "url": f"/reports/{r.report_id}",
            })

    return {
        "team": {
            "team_id": team.team_id,
            "team_name": team.team_name,
            "team_number": team.team_number,
            "team_abbreviation": team.team_abbreviation,
            "team_class": team.team_class.name if team.team_class else None,
            "info": {
                "bio": info_map.get(TeamInfo.InfoTypes.BIO),
                "instagram": info_map.get(TeamInfo.InfoTypes.INSTAGRAM),
                "website": info_map.get(TeamInfo.InfoTypes.WEBSITE),
                "nickname": info_map.get(TeamInfo.InfoTypes.NICKNAME),
                "youtube": info_map.get(TeamInfo.InfoTypes.YOUTUBE),
            },
        },
        "tractor": {
            "tractor_id": tractor.tractor_id,
            "tractor_name": tractor.tractor_name,
            "year": tractor.year,
            "photo_url": photo_url,
        } if tractor else None,
        "event_standing": {
            "total_score": event_team.total_score if event_team else None,
            "rank": rank,
        },
        "form_responses": form_responses_data,
        "reports": reports_data,
    }


def _resolve_event_team(event, team):
    """Return (event_team, rank) for the given team in the given event."""
    ets = list(
        EventTeam.objects.filter(event=event).order_by("-total_score").select_related("team")
    )
    event_team = next((et for et in ets if et.team_id == team.team_id), None)
    rank = next((i + 1 for i, et in enumerate(ets) if et.team_id == team.team_id), None)
    return event_team, rank


@api_view(["GET"])
@permission_classes([IsAdminUser])
def announcer_pull_data(request, pull_id):
    pull = get_object_or_404(
        Pull.objects.select_related("team__team_class", "event", "hook", "tractor__primary_photo"),
        pk=pull_id,
    )
    team = pull.team
    event = pull.event
    event_team, rank = _resolve_event_team(event, team)

    tractor_event = (
        TractorEvent.objects
        .filter(team=team, event=event)
        .select_related("tractor__primary_photo")
        .first()
    )
    tractor = tractor_event.tractor if tractor_event else pull.tractor
    photo_url = tractor.primary_photo.link if (tractor and tractor.primary_photo) else None

    all_event_pulls = (
        Pull.objects.filter(event=event, team=team)
        .select_related("hook")
        .order_by("hook__hook_id")
    )

    payload = _build_announcer_team_payload(team, event, event_team, rank, tractor, photo_url)
    payload["current_pull"] = {
        "pull_id": pull.pull_id,
        "hook_name": pull.hook.hook_name if pull.hook else None,
        "final_distance": pull.final_distance,
    }
    payload["all_event_pulls"] = [
        {
            "pull_id": p.pull_id,
            "hook_name": p.hook.hook_name if p.hook else None,
            "final_distance": p.final_distance,
        }
        for p in all_event_pulls
    ]
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def announcer_man_data(request, run_id):
    run = get_object_or_404(
        ManeuverabilityRun.objects.select_related("team__team_class", "event"),
        pk=run_id,
    )
    team = run.team
    event = run.event
    event_team, rank = _resolve_event_team(event, team)

    tractor_event = (
        TractorEvent.objects
        .filter(team=team, event=event)
        .select_related("tractor__primary_photo")
        .first()
    )
    tractor = tractor_event.tractor if tractor_event else None
    photo_url = tractor.primary_photo.link if (tractor and tractor.primary_photo) else None

    payload = _build_announcer_team_payload(team, event, event_team, rank, tractor, photo_url)
    payload["run_state"] = run.state
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def announcer_dur_data(request, run_id):
    run = get_object_or_404(
        DurabilityRun.objects.select_related("team__team_class", "event", "tractor__primary_photo"),
        pk=run_id,
    )
    team = run.team
    event = run.event
    event_team, rank = _resolve_event_team(event, team)

    tractor = run.tractor
    photo_url = tractor.primary_photo.link if (tractor and tractor.primary_photo) else None

    payload = _build_announcer_team_payload(team, event, event_team, rank, tractor, photo_url)
    payload["run_state"] = run.state
    payload["total_laps"] = run.total_laps
    return Response(payload)


# ── Overlay Producer ─────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAdminUser])
def overlay_active_responses(request):
    """Return form responses for the team linked to the given pull_id.

    Responses are split into:
      - individual_responses: single Q&A or image answers (for stat/image cards)
      - layout_groups: groups configured with an OverlayLayout (multi-field cards)
    """
    from collections import defaultdict
    from compforms.models import FormResponse, GroupOverlayConfig, GroupQuestion, TeamQuestionAssignment

    # The producer page follows whichever activity a team is running, so the
    # team + event can be resolved from a pull, durability run, or
    # maneuverability run id. Whichever id is supplied wins.
    pull_id = request.query_params.get("pull_id")
    dur_run_id = request.query_params.get("dur_run_id")
    man_run_id = request.query_params.get("man_run_id")

    if pull_id:
        run = get_object_or_404(
            Pull.objects.select_related("team", "event"), pk=pull_id,
        )
    elif dur_run_id:
        run = get_object_or_404(
            DurabilityRun.objects.select_related("team", "event"), pk=dur_run_id,
        )
    elif man_run_id:
        run = get_object_or_404(
            ManeuverabilityRun.objects.select_related("team", "event"), pk=man_run_id,
        )
    else:
        return Response({"team": None, "individual_responses": [], "layout_groups": []})

    team = run.team
    event = run.event
    event_team = EventTeam.objects.filter(event=event, team=team).first()
    if not event_team:
        return Response({
            "team": {"team_name": team.team_name, "team_number": team.team_number},
            "individual_responses": [],
            "layout_groups": [],
        })

    form_responses = (
        FormResponse.objects
        .filter(event_form__event=event, event_team=event_team)
        .select_related("event_form__form")
        .prefetch_related("answers__question")
    )

    individual_responses = []
    layout_groups = []

    for fr in form_responses:
        form_name = fr.event_form.form.name

        # Build answer lookup for this form response
        answer_map = {qa.question_id: qa for qa in fr.answers.select_related("question")}

        # Get all team question assignments for this form's groups, with overlay config
        assignments = (
            TeamQuestionAssignment.objects
            .filter(event_team=event_team, group__form=fr.event_form.form)
            .select_related("group__overlay_config__layout", "question")
            .order_by("group__order", "display_order")
        )

        # Build group → assignments map
        group_assignments = defaultdict(list)
        for a in assignments:
            group_assignments[a.group_id].append(a)

        # Build role map: (group_id, question_id) → overlay_role
        group_ids = list(group_assignments.keys())
        role_map = {}
        if group_ids:
            for gq in GroupQuestion.objects.filter(group_id__in=group_ids).values("group_id", "question_id", "overlay_role"):
                role_map[(gq["group_id"], gq["question_id"])] = gq["overlay_role"]

        # Track which question_ids are consumed by a layout group
        layout_question_ids = set()

        for group_id, group_asns in group_assignments.items():
            group = group_asns[0].group
            config = getattr(group, "overlay_config", None)
            if not config or not config.layout:
                continue

            fields = {}
            for asn in group_asns:
                role = role_map.get((group_id, asn.question_id), "")
                if not role:
                    continue
                qa = answer_map.get(asn.question_id)
                if qa:
                    if qa.image:
                        fields[role] = request.build_absolute_uri(qa.image.url)
                    elif qa.answer:
                        fields[role] = qa.answer
                layout_question_ids.add(asn.question_id)

            if fields:
                layout_groups.append({
                    "group_id": group_id,
                    "group_name": group.name,
                    "form_name": form_name,
                    "layout_type": config.layout.layout_type,
                    "layout_name": config.layout.name,
                    "layout_id": config.layout.layout_id,
                    "team_name": team.team_name,
                    "fields": fields,
                })

        # Individual responses: answers not consumed by a layout group
        for qid, qa in answer_map.items():
            if qid in layout_question_ids:
                continue
            if qa.answer or qa.image:
                individual_responses.append({
                    "form_name": form_name,
                    "question": qa.question.question_text,
                    "question_id": qid,
                    "answer": qa.answer,
                    "image_url": request.build_absolute_uri(qa.image.url) if qa.image else None,
                })

    return Response({
        "team": {"team_name": team.team_name, "team_number": team.team_number},
        "individual_responses": individual_responses,
        "layout_groups": layout_groups,
    })


@api_view(["POST"])
@permission_classes([IsAdminUser])
def overlay_card_trigger(request):
    """Publish a card to all overlay clients via Redis → SSE.

    For stat/image cards: { layout, question, answer, image_url, form_name, team_name }
    For layout cards:     { layout, layout_type, group_name, fields, form_name, team_name }
    """
    import redis as redis_lib
    import json as json_lib
    import time as time_lib
    from django.conf import settings as django_settings

    layout = request.data.get("layout", "stat")
    team_name = request.data.get("team_name", "")
    form_name = request.data.get("form_name", "")

    if layout in ("profile", "image"):
        fields = request.data.get("fields")
        if not fields:
            return Response({"error": "fields required for layout cards"}, status=status.HTTP_400_BAD_REQUEST)
        payload = {
            "layout": layout,
            "layout_name": request.data.get("layout_name", ""),
            "group_name": request.data.get("group_name", ""),
            "fields": fields,
            "form_name": form_name,
            "team_name": team_name,
            "ts": time_lib.time(),
        }
    else:
        question = request.data.get("question", "")
        answer = request.data.get("answer", "")
        image_url = request.data.get("image_url", "")
        if not question or (not answer and not image_url):
            return Response({"error": "question and answer (or image_url) required"}, status=status.HTTP_400_BAD_REQUEST)
        payload = {
            "layout": "image" if image_url and not answer else "stat",
            "question": question,
            "answer": answer,
            "image_url": image_url,
            "form_name": form_name,
            "team_name": team_name,
            "ts": time_lib.time(),
        }

    # Attach scene definition if a layout_id is provided
    layout_id = request.data.get("layout_id")
    if layout_id:
        from compforms.models import OverlayLayout
        try:
            layout_obj = OverlayLayout.objects.select_related('scene').get(pk=layout_id)
            if layout_obj.scene:
                payload['scene_definition'] = {
                    'canvas_width':  layout_obj.scene.canvas_width,
                    'canvas_height': layout_obj.scene.canvas_height,
                    'elements':      layout_obj.scene.elements,
                }
        except OverlayLayout.DoesNotExist:
            pass

    r = redis_lib.Redis.from_url(django_settings.REDIS_URL, decode_responses=True)
    payload_str = json_lib.dumps(payload)
    r.set("overlay:card:latest", payload_str)
    r.publish("overlay:card", payload_str)

    return Response({"ok": True})


# Every overlay card is an independently-toggleable module. All default OFF
# (a missing key means the card is hidden); the producer turns each on as needed.
_OVERLAY_TOGGLE_KEYS = {
    # Pull data cards
    "pull_hud", "pull_chart", "load_toad",
    # Durability data cards
    "dur_hud", "dur_chart",
    # Maneuverability data card (HUD only — no telemetry stream yet)
    "man_hud",
    # Common cards (shared across all events)
    "tractor_card", "up_next", "reactions", "poll",
}


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def overlay_toggle(request):
    """Read or update overlay toggle flags (one flag per overlay card).

    GET  → returns current toggle state.
    POST → either:
             - { key: "pull_hud", value: true|false } to set a single flag, or
             - { state: { pull_hud: false, poll: false, ... } } to merge several
               at once (used by the producer's "All Off" button).
           The merged state is persisted in Redis and published so all
           overlay/producer clients sync.
    """
    import redis as redis_lib
    import json as json_lib
    from django.conf import settings as django_settings

    r = redis_lib.Redis.from_url(django_settings.REDIS_URL, decode_responses=True)
    raw = r.get("overlay:toggle:latest")
    state = {}
    if raw:
        try:
            state = json_lib.loads(raw) or {}
        except Exception:
            state = {}

    if request.method == "GET":
        return Response(state)

    # Bulk update form: { state: { key: bool, ... } }
    bulk = request.data.get("state")
    if bulk is not None:
        if not isinstance(bulk, dict):
            return Response({"error": "state must be an object"},
                            status=status.HTTP_400_BAD_REQUEST)
        for k, v in bulk.items():
            if k not in _OVERLAY_TOGGLE_KEYS:
                return Response({"error": f"unknown toggle key: {k}"},
                                status=status.HTTP_400_BAD_REQUEST)
            if not isinstance(v, bool):
                return Response({"error": f"value for {k} must be boolean"},
                                status=status.HTTP_400_BAD_REQUEST)
            state[k] = v
    else:
        key = request.data.get("key")
        value = request.data.get("value")
        if key not in _OVERLAY_TOGGLE_KEYS:
            return Response({"error": f"unknown toggle key: {key}"},
                            status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(value, bool):
            return Response({"error": "value must be boolean"},
                            status=status.HTTP_400_BAD_REQUEST)
        state[key] = value

    payload_str = json_lib.dumps(state)
    r.set("overlay:toggle:latest", payload_str)
    r.publish("overlay:toggle", payload_str)
    return Response(state)
