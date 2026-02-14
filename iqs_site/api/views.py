from collections import OrderedDict

from django.contrib.auth.models import User
from django.db.models import Prefetch, Subquery, OuterRef, Case, When, Value, IntegerField
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from events.models import (
    Event, Team, TeamClass, Tractor, TractorEvent, Hook, Pull, PullData,
    EventTeam, EventTeamPhoto, ScheduleItem, TractorMedia, TractorInfo,
    DurabilityRun, DurabilityData, ManeuverabilityRun,
    PerformanceEventMedia, TeamInfo,
    ScoreCategoryInstance, ScoreSubCategoryInstance, ScoreSubCategoryScore,
)
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
