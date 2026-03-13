import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('compforms', '0004_questionresponse_flag_reason_and_more'),
    ]

    operations = [
        # IMAGE question type (choices-only change)
        migrations.AlterField(
            model_name='question',
            name='question_type',
            field=models.CharField(
                choices=[
                    ('SHORT_TEXT', 'Short Text'),
                    ('LONG_TEXT', 'Long Text'),
                    ('IMAGE', 'Image Upload'),
                ],
                default='LONG_TEXT',
                max_length=20,
            ),
        ),

        # image field on QuestionResponse
        migrations.AddField(
            model_name='questionresponse',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='form_responses/'),
        ),

        # overlay_role on GroupQuestion
        migrations.AddField(
            model_name='groupquestion',
            name='overlay_role',
            field=models.CharField(
                blank=True,
                help_text='Role this question plays in the overlay layout (e.g. photo, name, bio, stat_1, stat_2).',
                max_length=50,
            ),
        ),

        # OverlayLayout table
        migrations.CreateModel(
            name='OverlayLayout',
            fields=[
                ('layout_id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('layout_type', models.CharField(
                    choices=[
                        ('stat', 'Stat Card'),
                        ('profile', 'Profile Card'),
                        ('image', 'Image Card'),
                    ],
                    max_length=50,
                )),
                ('description', models.TextField(blank=True)),
            ],
        ),

        # GroupOverlayConfig table
        migrations.CreateModel(
            name='GroupOverlayConfig',
            fields=[
                ('config_id', models.AutoField(primary_key=True, serialize=False)),
                ('group', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='overlay_config',
                    to='compforms.questiongroup',
                )),
                ('layout', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='group_configs',
                    to='compforms.overlaylayout',
                )),
            ],
        ),
    ]
