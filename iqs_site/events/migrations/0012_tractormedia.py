# Generated migration for TractorMedia model
import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0011_maneuverabilityrun_teaminfo_tractorinfo_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TractorMedia',
            fields=[
                ('media_id', models.AutoField(primary_key=True, serialize=False)),
                ('media_type', models.IntegerField(blank=True, choices=[(1, 'Youtube Video'), (2, 'Image')], null=True)),
                ('link', models.CharField(blank=True, max_length=255, null=True)),
                ('caption', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(default=datetime.datetime.utcnow)),
                ('approved', models.BooleanField(default=False)),
                ('submitted_from_ip', models.CharField(blank=True, max_length=255, null=True)),
            ],
            options={
                'db_table': 'tractor_media',
                'managed': False,
                'permissions': [('can_auto_approve_tractor_media', 'Can auto-approve uploaded tractor media')],
            },
        ),
    ]
