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
            name='Question',
            fields=[
                ('question_id', models.AutoField(primary_key=True, serialize=False)),
                ('question_text', models.TextField()),
                ('question_type', models.CharField(
                    choices=[('SHORT_TEXT', 'Short Text'), ('LONG_TEXT', 'Long Text')],
                    default='LONG_TEXT',
                    max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='CompForm',
            fields=[
                ('form_id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='FormQuestion',
            fields=[
                ('form_question_id', models.AutoField(primary_key=True, serialize=False)),
                ('form', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='form_questions',
                    to='compforms.compform',
                )),
                ('question', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='form_questions',
                    to='compforms.question',
                )),
                ('order', models.PositiveIntegerField()),
                ('required', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['order'],
                'unique_together': {('form', 'question')},
            },
        ),
        migrations.AddField(
            model_name='compform',
            name='questions',
            field=models.ManyToManyField(
                through='compforms.FormQuestion',
                related_name='forms',
                to='compforms.question',
            ),
        ),
        migrations.CreateModel(
            name='EventForm',
            fields=[
                ('event_form_id', models.AutoField(primary_key=True, serialize=False)),
                ('event', models.ForeignKey(
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='event_forms',
                    to='events.event',
                )),
                ('form', models.ForeignKey(
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='event_forms',
                    to='compforms.compform',
                )),
                ('is_open', models.BooleanField(default=True)),
            ],
            options={
                'unique_together': {('event', 'form')},
            },
        ),
        migrations.CreateModel(
            name='FormResponse',
            fields=[
                ('response_id', models.AutoField(primary_key=True, serialize=False)),
                ('event_form', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='responses',
                    to='compforms.eventform',
                )),
                ('event_team', models.ForeignKey(
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='form_responses',
                    to='events.eventteam',
                )),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('submitted_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='form_responses_submitted',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'unique_together': {('event_form', 'event_team')},
            },
        ),
        migrations.CreateModel(
            name='QuestionResponse',
            fields=[
                ('question_response_id', models.AutoField(primary_key=True, serialize=False)),
                ('form_response', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='answers',
                    to='compforms.formresponse',
                )),
                ('question', models.ForeignKey(
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='answers',
                    to='compforms.question',
                )),
                ('answer', models.TextField(blank=True)),
            ],
            options={
                'unique_together': {('form_response', 'question')},
            },
        ),
    ]
