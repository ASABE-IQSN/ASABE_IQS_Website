# Generated migration for primary_photo field on Tractor
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0012_tractormedia'),
    ]

    operations = [
        migrations.AddField(
            model_name='tractor',
            name='primary_photo',
            field=models.ForeignKey(
                blank=True,
                db_column='primary_photo_media_id',
                null=True,
                on_delete=models.SET_NULL,
                related_name='primary_for_tractors',
                to='events.tractormedia'
            ),
        ),
    ]
