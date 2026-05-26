import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('compforms', '0010_alter_eventform_unique_together_eventform_team_class_and_more'),
    ]

    operations = [
        # Add the two new nullable FK columns
        migrations.AddField(
            model_name='questionresponse',
            name='form_question',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='answers',
                to='compforms.formquestion',
            ),
        ),
        migrations.AddField(
            model_name='questionresponse',
            name='team_assignment',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='answers',
                to='compforms.teamquestionassignment',
            ),
        ),
        # Drop the old (form_response, question) unique_together
        migrations.AlterUniqueTogether(
            name='questionresponse',
            unique_together=set(),
        ),
        # Add typed unique_together pairs. MySQL allows multiple NULLs in a unique
        # index, so these act as conditional constraints: flat answers are deduplicated
        # on form_question, group answers on team_assignment, and neither interferes
        # with the other.
        migrations.AlterUniqueTogether(
            name='questionresponse',
            unique_together={
                ('form_response', 'form_question'),
                ('form_response', 'team_assignment'),
            },
        ),
    ]
