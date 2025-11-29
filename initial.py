from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
import local_secrets
from sqlalchemy.orm import selectinload
from datetime import datetime
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# Put this after app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join("/var","www","quarterscale", "static", "photos")
print(app.config["UPLOAD_FOLDER"])
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max, adjust as needed
#app.config["SQLALCHEMY_ECHO"] = True
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS



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

    

@app.route("/results")
def results():
    query=Pull.query
    
    rows = query.order_by(Pull.pull_id).all()
    return render_template("results.html", results=rows)

@app.route("/")
def landing():
    now = datetime.utcnow()  # or datetime.now() if you're thinking in local time

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
def pull_detail(pull_id):
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

@app.route("/events")
def events():
    events = (
        Event.query
        .options(
            selectinload(Event.event_teams).selectinload(EventTeam.team)
        )
        .order_by(Event.event_datetime.desc())
        .all()
    )
    return render_template("events.html", events=events)

from sqlalchemy.orm import selectinload

@app.route("/event/<int:event_id>/team/<int:team_id>")
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

@app.route("/team/<int:team_id>")
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
        team_photos=team_photos,   # 👈 pass to template
    )

@app.route("/event/<int:event_id>")
def event_detail(event_id):
    event = (
        Event.query
        .options(
            # rankings
            selectinload(Event.event_teams).selectinload(EventTeam.team),
            # hooks → pulls → team
            selectinload(Event.hooks)
                .selectinload(Hook.pulls)
                .selectinload(Pull.team),
        )
        .get_or_404(event_id)
    )

    return render_template("event_detail.html", event=event)

@app.route("/teams")
def teams():
    teams = (
        Team.query
        .order_by(Team.team_name)  # or Team.team_name
        .all()
    )
    return render_template("teams.html", teams=teams)

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
        )
        db.session.add(photo)
        db.session.commit()

    return redirect(url_for("team_event_detail", event_id=event_id, team_id=team_id))

@app.route("/tractors")
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

@app.route("/tractor/<int:tractor_id>")
def tractor_detail(tractor_id):
    tractor = (
        Tractor.query
        .options(
            selectinload(Tractor.pulls)
                .selectinload(Pull.event),
            selectinload(Tractor.pulls)
                .selectinload(Pull.team),
            selectinload(Tractor.tractor_events)
                .selectinload(TractorEvent.team),
            selectinload(Tractor.tractor_events)
                .selectinload(TractorEvent.event),
        )
        .get_or_404(tractor_id)
    )

    # Sort pulls by event date then hook/pull_id
    pulls = sorted(
        tractor.pulls,
        key=lambda p: (
            p.event.event_datetime if p.event and p.event.event_datetime else None,
            p.event_id,
            p.pull_id,
        )
    )

    # Build a list of (team, event, year) usages
    usages = []
    for te in tractor.tractor_events:
        year = None
        if te.event and te.event.event_datetime:
            year = te.event.event_datetime.year
        usages.append({
            "team": te.team,
            "event": te.event,
            "year": year,
        })

    # Sort usages by year desc then event name
    usages.sort(key=lambda u: (u["year"] or 0, u["event"].event_name if u["event"] else ""), reverse=True)

    # Distinct events/teams if you want them separately
    events = sorted(
        {te.event for te in tractor.tractor_events if te.event},
        key=lambda e: (e.event_datetime or None, e.event_name)
    )
    teams = sorted(
        {te.team for te in tractor.tractor_events if te.team},
        key=lambda t: t.team_name
    )

    return render_template(
        "tractor_detail.html",
        tractor=tractor,
        pulls=pulls,
        usages=usages,
        events=events,
        teams=teams,
    )

@app.route("/example")
def example():
    if request.headers.getlist("X-Forwarded-For"):
        ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        ip = request.remote_addr
    return f"Your IP is {ip}"