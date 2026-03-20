import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('events', '0022_alter_team_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CrowdSubmission',
            fields=[
                ('submission_id', models.AutoField(primary_key=True, serialize=False)),
                ('submission_type', models.CharField(
                    choices=[('comment', 'Comment'), ('photo', 'Photo')],
                    max_length=10,
                )),
                ('text', models.TextField(blank=True)),
                ('photo', models.ImageField(blank=True, null=True, upload_to='engagement/submissions/')),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
                    db_index=True,
                    default='pending',
                    max_length=10,
                )),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('event', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='events.event',
                )),
                ('reviewed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='reviewed_crowd_submissions',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('submitted_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='crowd_submissions',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'engagement_crowd_submissions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='crowdsubmission',
            index=models.Index(fields=['status', 'created_at'], name='engagement__status_created_idx'),
        ),
        migrations.CreateModel(
            name='ReactionAggregate',
            fields=[
                ('aggregate_id', models.AutoField(primary_key=True, serialize=False)),
                ('emoji', models.CharField(
                    choices=[('fire', '🔥'), ('clap', '👏'), ('wow', '😮'), ('tractor', '🚜')],
                    max_length=10,
                )),
                ('count', models.PositiveBigIntegerField(default=0)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('event', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reaction_aggregates',
                    to='events.event',
                )),
            ],
            options={
                'db_table': 'engagement_reaction_aggregates',
            },
        ),
        migrations.AlterUniqueTogether(
            name='reactionaggregate',
            unique_together={('event', 'emoji')},
        ),
        migrations.CreateModel(
            name='Poll',
            fields=[
                ('poll_id', models.AutoField(primary_key=True, serialize=False)),
                ('question', models.CharField(max_length=500)),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('active', 'Active'), ('closed', 'Closed')],
                    db_index=True,
                    default='draft',
                    max_length=10,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('activated_at', models.DateTimeField(blank=True, null=True)),
                ('event', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='events.event',
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'engagement_polls',
            },
        ),
        migrations.CreateModel(
            name='PollOption',
            fields=[
                ('option_id', models.AutoField(primary_key=True, serialize=False)),
                ('option_text', models.CharField(max_length=255)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('vote_count', models.PositiveBigIntegerField(default=0)),
                ('poll', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='options',
                    to='engagement.poll',
                )),
            ],
            options={
                'db_table': 'engagement_poll_options',
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='FanVoteCategory',
            fields=[
                ('category_id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='fan_vote_categories',
                    to='events.event',
                )),
            ],
            options={
                'db_table': 'engagement_fan_vote_categories',
            },
        ),
        migrations.CreateModel(
            name='FanVote',
            fields=[
                ('vote_id', models.AutoField(primary_key=True, serialize=False)),
                ('session_key', models.CharField(db_index=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('category', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='votes',
                    to='engagement.fanvotecategory',
                )),
                ('team', models.ForeignKey(
                    db_constraint=False,
                    on_delete=django.db.models.deletion.CASCADE,
                    to='events.team',
                )),
            ],
            options={
                'db_table': 'engagement_fan_votes',
            },
        ),
        migrations.AlterUniqueTogether(
            name='fanvote',
            unique_together={('category', 'session_key')},
        ),
        migrations.AddIndex(
            model_name='fanvote',
            index=models.Index(fields=['category', 'team'], name='engagement__fanvote_cat_team_idx'),
        ),
    ]
