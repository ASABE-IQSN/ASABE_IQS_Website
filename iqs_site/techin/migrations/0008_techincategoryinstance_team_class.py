from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("techin", "0007_category_instance_sheet"),
    ]

    operations = [
        migrations.AddField(
            model_name="techincategoryinstance",
            name="team_class_id",
            field=models.IntegerField(default=1),
        ),
    ]
