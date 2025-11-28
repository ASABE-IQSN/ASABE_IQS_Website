from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import local_secrets
from sqlalchemy.orm import selectinload
from datetime import datetime
app = Flask(__name__)

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
        lazy="selectin",     # loads in batches; good default
        cascade="all, delete-orphan"  # optional, for cleanup
    )
    hook = db.relationship("Hook", back_populates="pulls")

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
    pull = db.relationship("Pull", back_populates="pull_data")

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

class EventTeam(db.Model):
    __tablename__="event_teams"
    event_team_id=db.Column(db.Integer,primary_key=True)
    event_id=db.Column(db.Integer,db.ForeignKey("events.event_id"),nullable=False)
    team_id=db.Column(db.Integer,db.ForeignKey("teams.team_id"),nullable=False)
    total_score=db.Column(db.Integer,nullable=True)
    event = db.relationship("Event", back_populates="event_teams")
    team = db.relationship("Team", back_populates="event_teams")

    

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

@app.route("/event/<int:event_id>/team/<int:team_id>")
def team_event_detail(event_id, team_id):
    event = Event.query.get_or_404(event_id)
    team = Team.query.get_or_404(team_id)

    # EventTeam row (score, etc.)
    event_team = EventTeam.query.filter_by(
        event_id=event_id,
        team_id=team_id,
    ).first()

    # Pulls for this team in this event
    pulls = (
        Pull.query
        .options(selectinload(Pull.pull_data))
        .filter_by(event_id=event_id, team_id=team_id)
        .order_by(Pull.pull_id)
        .all()
    )

    return render_template(
        "team_event_detail.html",
        event=event,
        team=team,
        event_team=event_team,
        pulls=pulls,
    )

@app.route("/team/<int:team_id>")
def team_profile(team_id):
    team = (
        Team.query
        .options(
            selectinload(Team.event_teams).selectinload(EventTeam.event),
            selectinload(Team.pulls),
        )
        .get_or_404(team_id)
    )

    return render_template("team_profile.html", team=team)

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

