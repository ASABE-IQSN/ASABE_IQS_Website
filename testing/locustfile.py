import os
import random
from locust import HttpUser, task, between
#from ....resources.secrets.python import local_secrets
import mysql.connector
# ---------------------------
# Helpers / configuration
# ---------------------------

DB_IP="38.22.155.20"
ADMINUNAME="####"
ADMINPWORD="####"
DB_NAME="IQS_Production_Environment"

cnx = mysql.connector.connect(
    host=DB_IP,
    port=3306,
    user=ADMINUNAME,
    password=ADMINPWORD,
    database=DB_NAME)
cursor=cnx.cursor(dictionary=True)
def _csv_ints(env_name: str, default: str) -> list[int]:
    raw = os.getenv(env_name, default).strip()
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]

def pick(lst):
    return random.choice(lst)

BASE_PATH = ""  # "", "/testing"
LOGIN_PATH = os.getenv("LOCUST_LOGIN_PATH", f"{BASE_PATH}/accounts/login/")

# Root-level IDs
EVENT_IDS = _csv_ints("LOCUST_EVENT_IDS", "25")
TEAM_IDS = _csv_ints("LOCUST_TEAM_IDS", "1")
TRACTOR_IDS = _csv_ints("LOCUST_TRACTOR_IDS", "1")
PULL_IDS = _csv_ints("LOCUST_PULL_IDS", "1")

sql="SELECT * FROM events"
cursor.execute(sql)
x=cursor.fetchall()
for res in x:
    EVENT_IDS.append(res["event_id"])

sql="SELECT * FROM teams"
cursor.execute(sql)
x=cursor.fetchall()
for res in x:
    TEAM_IDS.append(res["team_id"])

sql="SELECT * FROM tractors"
cursor.execute(sql)
x=cursor.fetchall()
for res in x:
    TRACTOR_IDS.append(res["tractor_id"])

sql="SELECT * FROM pulls"
cursor.execute(sql)
x=cursor.fetchall()
for res in x:
    PULL_IDS.append(res["pull_id"])

TECHIN_TEAM_PAIRS=[]

sql="SELECT * FROM event_teams et JOIN events e ON et.event_id=e.event_id WHERE e.techin_released"
cursor.execute(sql)
x=cursor.fetchall()
for res in x:
    TECHIN_TEAM_PAIRS.append((res["event_id"],res["team_id"]))

# Tech-in IDs
CATEGORY_IDS = []#_csv_ints("LOCUST_CATEGORY_IDS", "1")
SUBCATEGORY_IDS = []#_csv_ints("LOCUST_SUBCATEGORY_IDS", "1")
RULE_IDS = []#_csv_ints("LOCUST_RULE_IDS", "1")

sql="SELECT * FROM rule_categories"
cursor.execute(sql)
x=cursor.fetchall()
for res in x:
    CATEGORY_IDS.append(res["rule_category_id"])

sql="SELECT * FROM rule_subcategories WHERE rule_category_id !=6"
cursor.execute(sql)
x=cursor.fetchall()
for res in x:
    SUBCATEGORY_IDS.append(res["rule_subcategory_id"])

sql="SELECT * FROM rules r JOIN rule_subcategories rs ON r.rule_subcategory_id=rs.rule_subcategory_id WHERE rs.rule_category_id !=6"
cursor.execute(sql)
x=cursor.fetchall()
for res in x:
    RULE_IDS.append(res["rule_id"])

USERNAME = os.getenv("LOCUST_USERNAME", "")
PASSWORD = os.getenv("LOCUST_PASSWORD", "")

TECHIN_PREFIX = f"{BASE_PATH}/techin"

# ---------------------------
# User class
# ---------------------------

class WebsiteUser(HttpUser):
    wait_time = between(0.3, 1.5)

    def on_start(self):
        """Optional login (for group-protected pages)"""
        if not (USERNAME and PASSWORD):
            return

        self.client.get(LOGIN_PATH, name="GET login")
        resp = self.client.post(
            LOGIN_PATH,
            data={"username": USERNAME, "password": PASSWORD},
            allow_redirects=True,
            name="POST login",
        )
        if resp.status_code >= 400:
            resp.failure("Login failed")

    # ---------------------------
    # Root / public browsing
    # ---------------------------

    @task(12)
    def landing(self):
        self.client.get(f"{BASE_PATH}/", name="landing")

    @task(8)
    def event_list(self):
        self.client.get(f"{BASE_PATH}/events/", name="event_list")

    @task(6)
    def event_detail(self):
        self.client.get(
            f"{BASE_PATH}/events/{pick(EVENT_IDS)}/",
            name="event_detail"
        )

    @task(6)
    def team_list(self):
        self.client.get(f"{BASE_PATH}/teams/", name="team_list")

    @task(4)
    def team_detail(self):
        self.client.get(
            f"{BASE_PATH}/teams/{pick(TEAM_IDS)}/",
            name="team_detail"
        )

    @task(3)
    def team_event_detail(self):
        self.client.get(
            f"{BASE_PATH}/team-event/{pick(EVENT_IDS)}/{pick(TEAM_IDS)}/",
            name="team_event_detail"
        )

    @task(3)
    def pull_detail(self):
        self.client.get(
            f"{BASE_PATH}/pulls/{pick(PULL_IDS)}/",
            name="pull_detail"
        )

    @task(3)
    def tractor_list(self):
        self.client.get(f"{BASE_PATH}/tractors/", name="tractor_list")

    @task(2)
    def tractor_detail(self):
        self.client.get(
            f"{BASE_PATH}/tractors/{pick(TRACTOR_IDS)}",
            name="tractor_detail"
        )

    # @task(1)
    # def privacy(self):
    #     self.client.get(f"{BASE_PATH}/privacy/", name="privacy")

    # ---------------------------
    # Tech-In traffic
    # ---------------------------

    @task(6)
    def techin_event_overview(self):
        self.client.get(
            f"{TECHIN_PREFIX}/event/{pick(EVENT_IDS)}/",
            name="techin_event_overview"
        )

    @task(4)
    def techin_team_overview(self):
        pair=pick(TECHIN_TEAM_PAIRS)
        self.client.get(
            f"{TECHIN_PREFIX}/event/{pair[0]}/team/{pair[1]}/",
            name="techin_team_overview"
        )

    @task(2)
    def techin_team_subcategory(self):
        pair=pick(TECHIN_TEAM_PAIRS)
        self.client.get(
            f"{TECHIN_PREFIX}/event/{pair[0]}/team/{pair[1]}/subcategory/{pick(SUBCATEGORY_IDS)}/",
            name="techin_team_subcategory"
        )

    @task(2)
    def techin_team_rule(self):
        pair=pick(TECHIN_TEAM_PAIRS)
        self.client.get(
            f"{TECHIN_PREFIX}/event/{pair[0]}/team/{pair[1]}/rule/{pick(RULE_IDS)}/",
            name="techin_team_rule"
        )

    # @task(2)
    # def techin_category_view(self):
    #     pair=pick(TECHIN_TEAM_PAIRS)
    #     self.client.get(
    #         f"{TECHIN_PREFIX}/event/{pick(EVENT_IDS)}/category/{pick(CATEGORY_IDS)}",
    #         name="techin_category_view"
    #     )

    # ---------------------------
    # Rare actions (uploads)
    # ---------------------------

    # @task(0.2)
    # def upload_team_photo(self):
    #     """
    #     Very low weight – simulate occasional admin uploads.
    #     Use a tiny payload so we're testing auth & routing,
    #     not disk throughput.
    #     """
    #     self.client.post(
    #         f"{BASE_PATH}/team-event/{pick(EVENT_IDS)}/{pick(TEAM_IDS)}/upload-photo/",
    #         files={"photo": ("test.jpg", b"fakeimage", "image/jpeg")},
    #         name="upload_team_photo"
    #     )
