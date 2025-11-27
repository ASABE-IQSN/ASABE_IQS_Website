from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import local_secrets
from sqlalchemy.orm import selectinload
app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = local_secrets.DB_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)

class Pull(db.Model):
    __tablename__ = "pulls"
    pull_id = db.Column(db.Integer, primary_key=True)
    #team_id = db.Column(db.Integer, nullable=False)
    final_distance = db.Column(db.Float, nullable=True)
    hook_id = db.Column(db.Integer, nullable=True)
    team_id = db.Column(
        db.Integer,
        db.ForeignKey("teams.team_id"),
        nullable=False
    )

    # ORM relationship – lets you say result.team.team_name
    team = db.relationship("Team", lazy="joined")  # joined = eager load via JOIN
    pull_data = db.relationship(
        "PullData",
        back_populates="Pull",
        lazy="selectin",     # loads in batches; good default
        cascade="all, delete-orphan"  # optional, for cleanup
    )

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
    Pull = db.relationship("Pull", back_populates="pull_data")
    

class Team(db.Model):
    __tablename__ = "teams"  # adjust if your table is named differently

    team_id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(255), nullable=False)
    team_number = db.Column(db.String(255), nullable=False)
    # add other columns if you have them: university, number, etc.

@app.route("/results")
def results():
    query=Pull.query
    query.filter(Pull.hook_id==1)
    rows = query.order_by(Pull.final_distance).all()
    return render_template("results.html", results=rows)

@app.route("/")
def hello_world():
    return "<p> Hello World! </p>"

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
