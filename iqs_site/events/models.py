from django.db import models

# Create your models here.


class Team(models.Model):
    name = models.CharField(max_length=200)
    school = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name


class Event(models.Model):
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    # e.g. ["A-Team", "X-Team"] if you want to store classes on the event
    classes = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name


class Hook(models.Model):
    event = models.ForeignKey(Event, related_name="hooks", on_delete=models.CASCADE)
    # e.g. 1..6
    number = models.PositiveIntegerField()
    # e.g. "A-Team", "X-Team"
    class_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.event.name} – Hook {self.number} ({self.class_name})"


class Pull(models.Model):
    team = models.ForeignKey(Team, related_name="pulls", on_delete=models.CASCADE)
    event = models.ForeignKey(Event, related_name="pulls", on_delete=models.CASCADE)
    hook = models.ForeignKey(
        Hook, related_name="pulls", on_delete=models.SET_NULL, null=True, blank=True
    )

    final_distance = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # optional: if you have multiple tries, notes, etc.
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-final_distance"]

    def __str__(self):
        return f"{self.team} – {self.event} ({self.final_distance or 0:.2f} ft)"
