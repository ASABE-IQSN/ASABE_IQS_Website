from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('awards', '0003_awardtype_team_class'),
    ]

    operations = [
        migrations.AlterField(
            model_name='award',
            name='placement',
            field=models.IntegerField(
                blank=True,
                choices=[
                    (1, '1st Place'),
                    (2, '2nd Place'),
                    (3, '3rd Place'),
                    (4, '4th Place'),
                    (5, '5th Place'),
                ],
                null=True,
            ),
        ),
    ]
