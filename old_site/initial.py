from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
import local_secrets
from sqlalchemy.orm import selectinload
from datetime import datetime
from werkzeug.utils import secure_filename
from flask_caching import Cache
import flask_monitoringdashboard as dashboard
from collections import defaultdict
from sqlalchemy import and_
import os
import json
import redis

import logging

class IgnoreLiveIngestFilter(logging.Filter):
    def filter(self, record):
        return "/ingest/live" not in record.getMessage()

app = Flask(__name__)

# Put this after app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join("/var","www","quarterscale", "static", "photos")
print(app.config["UPLOAD_FOLDER"])
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max, adjust as needed
#app.config["SQLALCHEMY_ECHO"] = True
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

#app.config["DEBUG"]=True
# app.config["CACHE_TYPE"]="SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"]=300

app.config["CACHE_TYPE"] = "RedisCache"
app.config["CACHE_REDIS_URL"] = "redis://localhost:6379/0"
logging.getLogger("werkzeug").addFilter(IgnoreLiveIngestFilter())
cache=Cache(app)
dashboard.config.init_from(file='dashboard_config.cfg')
dashboard.bind(app)
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


live_data_cache=redis.Redis(
    host="localhost",
    port=6379,
    db=1,
    decode_responses=True
)


app.config["SQLALCHEMY_DATABASE_URI"] = local_secrets.DB_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)

class Pull(db.Model):
    __tablename__ = "pulls"
    pull_id = db.Column(db.Integer, primary_key=True)
    #team_id = db.Column(db.Integer, nullable=False)
    final_distance = db.Column(db.Float, nullable=True)
    hook_id = db.Column(db.Integer, db.ForeignKey("hooks.hook_id"),nullable=True)
    team_id = db.Column(
        db.Integer,
        db.ForeignKey("teams.team_id"),
        nullable=False
    )
    event_id = db.Column(db.Integer, db.ForeignKey("events.event_id"), nullable=True)

    # ORM relationship – lets you say result.team.team_name
    team = db.relationship("Team", lazy="joined")  # joined = eager load via JOIN
    event = db.relationship("Event", back_populates="pulls")
    pull_data = db.relationship(
        "PullData",
        back_populates="pull",
        lazy="noload",     # loads in batches; good default
        cascade="all, delete-orphan"  # optional, for cleanup
    )
    hook = db.relationship("Hook", back_populates="pulls")
    tractor_id = db.Column(
        db.Integer,
        db.ForeignKey("tractors.tractor_id"),
        nullable=True,   # or False if you want to enforce
    )
    tractor = db.relationship("Tractor", back_populates="pulls")

class PullData(db.Model):
    __tablename__="pull_data"
    data_id=db.Column(db.Integer, primary_key=True)
    pull_id = db.Column(
        db.Integer,
        db.ForeignKey("pulls.pull_id"),
        nullable=False,
    )
    chain_force=db.Column(db.Float)
    speed=db.Column(db.Float)
    distance=db.Column(db.Float)
    pull = db.relationship("Pull", back_populates="pull_data",lazy="selectin")

class Hook(db.Model):
    __tablename__="hooks"
    hook_id=db.Column(db.Integer,primary_key=True)
    event_id=db.Column(db.Integer,db.ForeignKey("events.event_id"))
    event=db.relationship("Event",back_populates="hooks")
    hook_name=db.Column(db.String,nullable=True)
    pulls = db.relationship("Pull", back_populates="hook", lazy="selectin",order_by="Pull.final_distance.desc()")
    

class Team(db.Model):
    __tablename__ = "teams"  # adjust if your table is named differently

    team_id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(255), nullable=False)
    team_number = db.Column(db.String(255), nullable=False)
    pulls = db.relationship("Pull", back_populates="team")
    event_teams = db.relationship("EventTeam", back_populates="team")
    team_class_id = db.Column(db.Integer,db.ForeignKey("team_class.team_class_id"))
    team_class = db.relationship("TeamClass",back_populates="teams",lazy="joined")
    tractor_events = db.relationship(
        "TractorEvent",
        back_populates="team",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    tractors = db.relationship(
        "Tractor",
        secondary="tractor_events",
        primaryjoin="Team.team_id == TractorEvent.team_id",
        secondaryjoin="Tractor.tractor_id == TractorEvent.tractor_id",
        viewonly=True,
        lazy="selectin",
    )

    original_tractors = db.relationship(
        "Tractor",
        back_populates="original_team",
        foreign_keys="Tractor.original_team_id",
    )


class Event(db.Model):
    __tablename__ = "events"
    event_id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String)
    event_teams = db.relationship(
        "EventTeam",
        back_populates="event",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="EventTeam.total_score.desc()",
    )
    pulls = db.relationship("Pull", back_populates="event")
    hooks = db.relationship("Hook",back_populates="event",lazy="selectin",cascade="all, delete-orphan")
    event_datetime = db.Column(db.DateTime, nullable=True)

    tractor_events = db.relationship(
        "TractorEvent",
        back_populates="event",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    tractors = db.relationship(
        "Tractor",
        secondary="tractor_events",
        primaryjoin="Event.event_id == TractorEvent.event_id",
        secondaryjoin="Tractor.tractor_id == TractorEvent.tractor_id",
        viewonly=True,
        lazy="selectin",
    )

class EventTeam(db.Model):
    __tablename__="event_teams"
    event_team_id=db.Column(db.Integer,primary_key=True)
    event_id=db.Column(db.Integer,db.ForeignKey("events.event_id"),nullable=False)
    team_id=db.Column(db.Integer,db.ForeignKey("teams.team_id"),nullable=False)
    total_score=db.Column(db.Integer,nullable=True)
    event = db.relationship("Event", back_populates="event_teams")
    team = db.relationship("Team", back_populates="event_teams")
    photos = db.relationship(
        "EventTeamPhoto",
        primaryjoin="and_(EventTeamPhoto.event_team_id == EventTeam.event_team_id, "
                    "EventTeamPhoto.approved == True)",
        lazy="selectin",
    )

class EventTeamPhoto(db.Model):
    __tablename__ = "event_team_photos"

    event_team_photo_id = db.Column(db.Integer, primary_key=True)
    event_team_id = db.Column(
        db.Integer,
        db.ForeignKey("event_teams.event_team_id"),
        nullable=False,
    )
    submitted_from_ip=db.Column(db.String,nullable=True)
    # path relative to /static directory, e.g. "team_photos/iowa_state_2026_1.jpg"
    photo_path = db.Column(db.String(255), nullable=False)

    caption = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    approved=db.Column(db.Boolean, nullable=False)
    event_team = db.relationship("EventTeam", back_populates="photos")

class Tractor(db.Model):
    __tablename__="tractors"

    tractor_id=db.Column(db.Integer, primary_key=True)
    tractor_name = db.Column(db.String(255), nullable=True)
    original_team_id=db.Column(db.Integer,db.ForeignKey("teams.team_id"))

    # Association rows
    tractor_events = db.relationship(
        "TractorEvent",
        back_populates="tractor",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # Convenience many-to-many: all teams this tractor has run under
    teams = db.relationship(
        "Team",
        secondary="tractor_events",
        primaryjoin="Tractor.tractor_id == TractorEvent.tractor_id",
        secondaryjoin="Team.team_id == TractorEvent.team_id",
        viewonly=True,
        lazy="selectin",
    )

    # Convenience many-to-many: all events this tractor has appeared in
    events = db.relationship(
        "Event",
        secondary="tractor_events",
        primaryjoin="Tractor.tractor_id == TractorEvent.tractor_id",
        secondaryjoin="Event.event_id == TractorEvent.event_id",
        viewonly=True,
        lazy="selectin",
    )
    pulls = db.relationship(
        "Pull",
        back_populates="tractor",
        lazy="selectin",
    )

    original_team = db.relationship(
        "Team",
        foreign_keys=[original_team_id],
        back_populates="original_tractors",
    )


class TractorEvent(db.Model):
    __tablename__="tractor_events"

    tractor_event_id = db.Column(db.Integer, primary_key=True)

    tractor_id = db.Column(
        db.Integer,
        db.ForeignKey("tractors.tractor_id"),
        nullable=False,
    )
    team_id = db.Column(
        db.Integer,
        db.ForeignKey("teams.team_id"),
        nullable=False,
    )
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("events.event_id"),
        nullable=False,
    )

    # Optional: enforce uniqueness so you don't get duplicate rows:
    __table_args__ = (
        db.UniqueConstraint(
            "tractor_id", "team_id", "event_id",
            name="uix_tractor_team_event",
        ),
    )

    tractor = db.relationship("Tractor", back_populates="tractor_events")
    team = db.relationship("Team", back_populates="tractor_events")
    event = db.relationship("Event", back_populates="tractor_events")

class TeamClass(db.Model):
    __tablename__="team_class"

    team_class_id=db.Column(db.Integer,primary_key=True)

    name=db.Column(db.String)

    teams = db.relationship(
        "Team",
        back_populates="team_class",
        lazy="noload",
    )

@app.route("/results")
def results():
    query=Pull.query
    
    rows = query.order_by(Pull.pull_id).all()
    return render_template("results.html", results=rows)

@app.route("/")
@cache.cached(timeout=300)
def landing():
    now = datetime.now()  # or datetime.now() if you're thinking in local time
    print("Main Page")
    next_event = (
        Event.query
        .options(selectinload(Event.event_teams))
        .filter(Event.event_datetime != None)
        .filter(Event.event_datetime >= now)
        .order_by(Event.event_datetime.asc())
        .first()
    )

    return render_template("landing.html", next_event=next_event)

@app.route("/pull/<int:pull_id>")
@cache.memoize()
def pull_detail(pull_id):
    print(f"Serving Pull:{pull_id}")
    pull = (
        Pull.query
        .options(
            selectinload(Pull.team),
            selectinload(Pull.pull_data)
        )
        .filter_by(pull_id=pull_id)
        .first_or_404()
    )

    # Extract arrays for the chart
    speeds = [d.speed for d in pull.pull_data if d.speed is not None and d.chain_force is not None]
    forces = [d.chain_force for d in pull.pull_data if d.speed is not None and d.chain_force is not None]
    distances = [d.distance for d in pull.pull_data if d.speed is not None and d.distance is not None]
    return render_template(
        "pull_detail.html",
        pull=pull,
        speeds=speeds,
        forces=forces,
        distances=distances,
    )

@app.route("/cache/reset/pull/<int:pull_id>")
def cache_buster_pull(pull_id):
    cache.delete_memoized(pull_detail,pull_id)
    return "Success"

@app.route("/events")
@cache.memoize()
def events():
    events = (
        Event.query
        .options(
            selectinload(Event.event_teams)
                .selectinload(EventTeam.team)
                .selectinload(Team.team_class)
        )
        .order_by(Event.event_datetime.desc())
        .all()
    )

    # Only the first 2 classes
    top_classes = (
        TeamClass.query
        .order_by(TeamClass.team_class_id)
        .limit(2)
        .all()
    )

    return render_template(
        "events.html",
        events=events,
        top_classes=top_classes,
    )

@app.route("/cache/reset/events")
def cache_buster_events():
    cache.delete_memoized(events)
    return "Success"

@app.route("/event/<int:event_id>/team/<int:team_id>")
@cache.memoize()
def team_event_detail(event_id, team_id):
    event = (
        Event.query
        .options(
            selectinload(Event.event_teams).selectinload(EventTeam.team),
        )
        .get_or_404(event_id)
    )

    team = Team.query.get_or_404(team_id)

    # Load EventTeam with its photos
    event_team = (
        EventTeam.query
        .options(selectinload(EventTeam.photos))
        .filter_by(event_id=event_id, team_id=team_id)
        .first()
    )

    pulls = (
        Pull.query
        .options(selectinload(Pull.hook))
        .filter_by(event_id=event_id, team_id=team_id)
        .order_by(Pull.hook_id, Pull.final_distance.desc())
        .all()
    )

    best_pull_overall = (
        Pull.query
        .options(selectinload(Pull.team), selectinload(Pull.hook))
        .filter_by(event_id=event_id)
        .order_by(Pull.final_distance.desc())
        .first()
    )

    top3 = event.event_teams[:3] if event.event_teams else []
    team_in_top3 = any(et.team_id == team_id for et in top3)

    # chart data
    labels = []
    distances = []
    for p in pulls:
        label = (
            p.hook.hook_name
            if p.hook and p.hook.hook_name
            else f"Hook {p.hook_id}"
        )
        labels.append(label)
        distances.append(p.final_distance or 0)
    return render_template(
        "team_event_detail.html",
        event=event,
        team=team,
        event_team=event_team,
        pulls=pulls,
        best_pull_overall=best_pull_overall,
        top3=top3,
        team_in_top3=team_in_top3,
        chart_labels=labels,
        chart_distances=distances,
    )

@app.route("/cache/reset/event/<int:event_id>/team/<int:team_id>")
def cache_buster_event_team(event_id,team_id):
    cache.delete_memoized(team_event_detail,event_id,team_id)
    return "Success"

@app.route("/team/<int:team_id>")
@cache.memoize()
def team_detail(team_id):
    team = (
        Team.query
        .options(
            selectinload(Team.event_teams).selectinload(EventTeam.event)
        )
        .get_or_404(team_id)
    )

    # Sort team.event_teams for the events list + chart
    event_teams = sorted(
        team.event_teams,
        key=lambda et: (et.event.event_datetime or et.event_id)
    )

    labels = [
        (et.event.event_datetime.strftime("%b %Y")
         if et.event.event_datetime
         else et.event.event_name)
        for et in event_teams
    ]
    scores = [
        et.total_score or 0
        for et in event_teams
    ]

    # NEW: all approved EventTeamPhoto rows for this team across events
    team_photos = (
        EventTeamPhoto.query
        .join(EventTeam, EventTeamPhoto.event_team)   # use relationship
        .join(Event, EventTeam.event)
        .options(
            selectinload(EventTeamPhoto.event_team)
                .selectinload(EventTeam.event)
        )
        .filter(
            EventTeam.team_id == team_id,
            EventTeamPhoto.approved == True
        )
        .order_by(
            Event.event_datetime.desc(),
            EventTeamPhoto.event_team_photo_id.desc()
        )
        .all()
    )

    return render_template(
        "team_detail.html",
        team=team,
        event_teams=event_teams,
        chart_labels=labels,
        chart_scores=scores,
        team_photos=team_photos,
    )

@app.route("/cache/reset/team/<int:team_id>")
def cache_buster_team(team_id):
    cache.delete_memoized(team_detail,team_id)
    return "Success"

@app.route("/event/<int:event_id>")
@cache.memoize()
def event_detail(event_id):
    event = Event.query.get_or_404(event_id)

    # Assuming event.event_teams is a relationship of EventTeam objects
    # and each EventTeam has .team with .team_class and .total_score
    rankings_by_class = defaultdict(list)
    
    for et in event.event_teams:
        tc = getattr(et.team, "team_class", None)
        class_name = tc.name if tc and getattr(tc, "name", None) else "Unclassified"
        rankings_by_class[class_name].append(et)

    # sort each class by total_score (descending), None at bottom
    for class_name, items in rankings_by_class.items():
        items.sort(
            key=lambda et: (et.total_score is None, -(et.total_score or 0))
        )

    # If you truly only ever want the first 2 classes:
    # rankings_by_class = dict(list(rankings_by_class.items())[:2])

    return render_template(
        "event_detail.html",
        event=event,
        rankings_by_class=rankings_by_class,
        active_page="events",
    )

@app.route("/cache/reset/event/<int:event_id>")
def cache_buster_event(event_id):
    cache.delete_memoized(event_detail,event_id)
    return "Success"

@app.route("/teams")
@cache.memoize()
def teams():
    # Load all classes and their teams + event_teams
    team_classes = (
        TeamClass.query
        .options(
            selectinload(TeamClass.teams)
                .selectinload(Team.event_teams)
                .selectinload(EventTeam.event)
        )
        .order_by(TeamClass.team_class_id)
        .all()
    )

    # Teams without a class
    unclassified_teams = (
        Team.query
        .options(
            selectinload(Team.event_teams)
                .selectinload(EventTeam.event)
        )
        .filter(Team.team_class_id.is_(None))
        .order_by(Team.team_name)
        .all()
    )

    # Build stats per class
    class_stats = {}
    for tc in team_classes:
        teams = tc.teams or []
        num_teams = len(teams)

        event_entries = []
        scores = []

        for team in teams:
            for et in team.event_teams:
                event_entries.append(et)
                if et.total_score is not None:
                    scores.append(et.total_score)

        num_events = len(event_entries)
        avg_score = sum(scores) / len(scores) if scores else None

        class_stats[tc.team_class_id] = {
            "num_teams": num_teams,
            "num_events": num_events,
            "avg_score": avg_score,
        }

    # Stats for unclassified
    unclassified_stats = None
    if unclassified_teams:
        event_entries = []
        scores = []
        for team in unclassified_teams:
            for et in team.event_teams:
                event_entries.append(et)
                if et.total_score is not None:
                    scores.append(et.total_score)

        num_teams = len(unclassified_teams)
        num_events = len(event_entries)
        avg_score = sum(scores) / len(scores) if scores else None

        unclassified_stats = {
            "num_teams": num_teams,
            "num_events": num_events,
            "avg_score": avg_score,
        }

    return render_template(
        "teams.html",
        team_classes=team_classes,
        unclassified_teams=unclassified_teams,
        class_stats=class_stats,
        unclassified_stats=unclassified_stats,
    )


@app.route("/cache/reset/teams")
def cache_buster_teams():
    cache.delete_memoized(teams)
    return "Success"

@app.route("/event/<int:event_id>/team/<int:team_id>/upload_photo", methods=["POST"])
def upload_team_photo(event_id, team_id):
    # Find EventTeam record
    event_team = (
        EventTeam.query
        .options(selectinload(EventTeam.photos))
        .filter_by(event_id=event_id, team_id=team_id)
        .first()
    )
    if event_team is None:
        abort(404)

    if "photo" not in request.files:
        # you can use flash if you have messaging set up; otherwise just redirect
        return redirect(url_for("team_event_detail", event_id=event_id, team_id=team_id))

    file = request.files["photo"]
    if request.headers.getlist("X-Forwarded-For"):
        ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        ip = request.remote_addr
    if file.filename == "":
        return redirect(url_for("team_event_detail", event_id=event_id, team_id=team_id))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        # ensure upload folder exists
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

        # Optionally prefix with event/team to reduce collisions
        name_root, ext = os.path.splitext(filename)
        filename = f"event{event_id}_team{team_id}_{name_root}{ext}"

        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)

        # Store path relative to /static
        rel_path = f"photos/{filename}"

        photo = EventTeamPhoto(
            event_team_id=event_team.event_team_id,
            photo_path=rel_path,
            submitted_from_ip=ip,
        )
        db.session.add(photo)
        db.session.commit()

    return redirect(url_for("team_event_detail", event_id=event_id, team_id=team_id))

@app.route("/tractors")
@cache.memoize()
def tractors():
    tractors = (
        Tractor.query
        .options(
            selectinload(Tractor.tractor_events)
                .selectinload(TractorEvent.team),
            selectinload(Tractor.tractor_events)
                .selectinload(TractorEvent.event),
        )
        .order_by(Tractor.tractor_name.is_(None), Tractor.tractor_name, Tractor.tractor_id)
        .all()
    )
    return render_template("tractors.html", tractors=tractors)

@app.route("/cache/reset/tractors")
def cache_buster_tractors():
    cache.delete_memoized(tractors)
    return "Success"

@app.route("/tractor/<int:tractor_id>")
@cache.memoize()
def tractor_detail(tractor_id):
    tractor = Tractor.query.get_or_404(tractor_id)

    # Convenience shortcuts from your relationships
    pulls = tractor.pulls          # all Pulls that used this tractor
    events = tractor.events        # all Events this tractor appeared in
    usages = tractor.tractor_events  # TractorEvent rows (team+event+year-ish)
    teams = tractor.teams          # all Teams that have used this tractor

    # Photos from events where this tractor was used
    # EventTeamPhoto -> EventTeam (event_id, team_id)
    # EventTeam + TractorEvent matched on (event_id, team_id) for this tractor
    tractor_photos = (
        db.session.query(EventTeamPhoto)
        .join(EventTeamPhoto.event_team)  # joins to EventTeam
        .join(
            TractorEvent,
            and_(
                TractorEvent.event_id == EventTeam.event_id,
                TractorEvent.team_id == EventTeam.team_id,
            ),
        )
        .filter(
            TractorEvent.tractor_id == tractor.tractor_id,
            EventTeamPhoto.approved.is_(True),
        )
        .order_by(EventTeamPhoto.created_at.desc())
        .all()
    )

    return render_template(
        "tractor_detail.html",
        tractor=tractor,
        pulls=pulls,
        events=events,
        usages=usages,
        teams=teams,
        tractor_photos=tractor_photos,   # <-- used by the template
        active_page="tractors",
    )

@app.route("/cache/reset/tractor/<int:tractor_id>")
def cache_buster_tractor(tractor_id):
    cache.delete_memoized(tractor_detail,tractor_id)
    return "Success"

@app.route("/privacy")
@cache.memoize()
def privacy():
    return render_template(
        "privacy.html",
        active_page=None,  # or "privacy" if you later add a nav link
        last_updated="January 1, 2026",
        contact_email="youremail@example.com",
    )

@app.route("/current_pull")
def current_pull():
    return render_template("current_pull.html")

@app.route("/ingest/live",methods=["POST"])
def update_live():
    for key in request.json:
        live_data_cache.set(key,request.json[key])
        
    return "Success"