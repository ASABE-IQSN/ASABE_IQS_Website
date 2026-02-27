from django.db import models


class AwardType(models.Model):
    CATEGORY_CHOICES = [
        ('REPORT', 'Report'),
        ('PRESENTATION', 'Presentation'),
        ('PULL', 'Pull'),
        ('OVERALL', 'Overall'),
        ('OTHER', 'Other'),
    ]

    award_type_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='awards/', blank=True, null=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='OTHER')
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

    @property
    def image_url(self):
        # MEDIA_ROOT = /var/www/quarterscale/static, served by nginx at /static/
        if self.image:
            return f"/static/{self.image.name}"
        return None


class Award(models.Model):
    award_id = models.AutoField(primary_key=True)
    award_type = models.ForeignKey(
        AwardType,
        on_delete=models.CASCADE,
        related_name='awards',
    )
    event_team = models.ForeignKey(
        'events.EventTeam',
        on_delete=models.CASCADE,
        related_name='awards',
    )
    notes = models.CharField(max_length=500, blank=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['event_team__event__event_datetime', 'display_order']
        unique_together = [('award_type', 'event_team')]

    def __str__(self):
        return f"{self.award_type.name} — {self.event_team}"
