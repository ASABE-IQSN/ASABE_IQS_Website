import os
import random
from locust import HttpUser, task, between

# ---------------------------
# Helpers / configuration
# ---------------------------

def _csv_ints(env_name: str, default: str) -> list[int]:
    raw = os.getenv(env_name, default).strip()
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]

def pick(lst):
    return random.choice(lst)

BASE_PATH = os.getenv("LOCUST_BASE_PATH", "").rstrip("/")  # "", "/testing"
LOGIN_PATH = os.getenv("LOCUST_LOGIN_PATH", f"{BASE_PATH}/accounts/login/")

# Root-level IDs
EVENT_IDS = _csv_ints("LOCUST_EVENT_IDS", "25")
TEAM_IDS = _csv_ints("LOCUST_TEAM_IDS", "1")
TRACTOR_IDS = _csv_ints("LOCUST_TRACTOR_IDS", "1")
PULL_IDS = _csv_ints("LOCUST_PULL_IDS", "1")

# Tech-in IDs
TRACTOR_EVENT_IDS = _csv_ints("LOCUST_TRACTOR_EVENT_IDS", "1")
CATEGORY_IDS = _csv_ints("LOCUST_CATEGORY_IDS", "1")
SUBCATEGORY_IDS = _csv_ints("LOCUST_SUBCATEGORY_IDS", "1")
RULE_IDS = _csv_ints("LOCUST_RULE_IDS", "1")

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

    # @task(4)
    # def techin_team_overview(self):
    #     self.client.get(
    #         f"{TECHIN_PREFIX}/event/{pick(EVENT_IDS)}/team/{pick(TRACTOR_EVENT_IDS)}/",
    #         name="techin_team_overview"
    #     )

    # @task(2)
    # def techin_team_subcategory(self):
    #     self.client.get(
    #         f"{TECHIN_PREFIX}/event/{pick(EVENT_IDS)}/team/{pick(TRACTOR_EVENT_IDS)}/subcategory/{pick(SUBCATEGORY_IDS)}/",
    #         name="techin_team_subcategory"
    #     )

    # @task(2)
    # def techin_team_rule(self):
    #     self.client.get(
    #         f"{TECHIN_PREFIX}/event/{pick(EVENT_IDS)}/team/{pick(TRACTOR_EVENT_IDS)}/rule/{pick(RULE_IDS)}/",
    #         name="techin_team_rule"
    #     )

    # @task(2)
    # def techin_category_view(self):
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
