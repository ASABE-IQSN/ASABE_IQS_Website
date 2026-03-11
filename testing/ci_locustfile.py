"""
CI-safe Locust file — no database connection.
IDs are seeded from environment variables with sensible defaults.
"""
import os
import random
from locust import HttpUser, task, between


def _csv_ints(env_name: str, default: str) -> list:
    raw = os.getenv(env_name, default).strip()
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]


def pick(lst):
    return random.choice(lst)


BASE_PATH = ""

EVENT_IDS = _csv_ints("LOCUST_EVENT_IDS", "1,2,3")
TEAM_IDS = _csv_ints("LOCUST_TEAM_IDS", "1,2,3")
TRACTOR_IDS = _csv_ints("LOCUST_TRACTOR_IDS", "1,2,3")
PULL_IDS = _csv_ints("LOCUST_PULL_IDS", "1,2,3")

TECHIN_PREFIX = f"{BASE_PATH}/techin"


class WebsiteUser(HttpUser):
    wait_time = between(0.3, 1.5)

    @task(12)
    def landing(self):
        self.client.get(f"{BASE_PATH}/", name="landing")

    @task(8)
    def event_list(self):
        self.client.get(f"{BASE_PATH}/events/", name="event_list")

    @task(6)
    def team_list(self):
        self.client.get(f"{BASE_PATH}/teams/", name="team_list")

    @task(6)
    def event_detail(self):
        self.client.get(
            f"{BASE_PATH}/events/{pick(EVENT_IDS)}/",
            name="event_detail"
        )

    @task(4)
    def team_detail(self):
        self.client.get(
            f"{BASE_PATH}/teams/{pick(TEAM_IDS)}/",
            name="team_detail"
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

    @task(6)
    def techin_event_overview(self):
        self.client.get(
            f"{TECHIN_PREFIX}/event/{pick(EVENT_IDS)}/",
            name="techin_event_overview"
        )
