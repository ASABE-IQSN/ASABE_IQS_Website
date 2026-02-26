from django.apps import AppConfig


class ScheduleConfig(AppConfig):
    name = "schedule"

    def ready(self):
        import schedule.signals  # noqa: F401
