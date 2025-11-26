from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import local_secrets
app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = local_secrets.DB_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)

class Pull(db.Model):
    __tablename__ = "pulls"
    pull_id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, nullable=False)
    final_distance = db.Column(db.Float, nullable=True)
    hook_id = db.Column(db.Integer, nullable=True)
    team_id = db.Column(
        db.Integer,
        db.ForeignKey("teams.team_id"),
        nullable=False
    )

    # ORM relationship – lets you say result.team.team_name
    team = db.relationship("Team", lazy="joined")  # joined = eager load via JOIN

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