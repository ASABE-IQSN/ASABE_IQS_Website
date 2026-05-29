import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0026_scoresheetsubmission'),
    ]

    operations = [
        migrations.CreateModel(
            name='EngineData',
            fields=[
                ('engine_data_id', models.AutoField(primary_key=True, serialize=False)),
                ('time', models.FloatField(blank=True, null=True)),
                ('eng_speed', models.FloatField(blank=True, null=True)),
                ('eng_percent_torque', models.FloatField(blank=True, null=True)),
                ('coolant_temp', models.FloatField(blank=True, null=True)),
                ('oil_press', models.FloatField(blank=True, null=True)),
                ('oil_temp', models.FloatField(blank=True, null=True)),
                ('fuel_rate', models.FloatField(blank=True, null=True)),
                ('turbo_boost_press', models.FloatField(blank=True, null=True)),
                ('throttle_pos', models.FloatField(blank=True, null=True)),
                ('percent_load', models.FloatField(blank=True, null=True)),
                ('fuel_level', models.FloatField(blank=True, null=True)),
                ('pull', models.ForeignKey(blank=True, db_column='pull_id', db_constraint=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='engine_data', to='events.pull')),
                ('durability_run', models.ForeignKey(blank=True, db_column='durability_run_id', db_constraint=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='engine_data', to='events.durabilityrun')),
            ],
            options={
                'db_table': 'engine_data',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='enginedata',
            index=models.Index(fields=['pull'], name='engine_data_pull_id_idx'),
        ),
        migrations.AddIndex(
            model_name='enginedata',
            index=models.Index(fields=['durability_run'], name='engine_data_dur_run_idx'),
        ),
    ]
