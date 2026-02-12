from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0016_alter_editlog_team_alter_editlog_tractor'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE event_team_photos ADD COLUMN official TINYINT(1) NOT NULL DEFAULT 0;",
            reverse_sql="ALTER TABLE event_team_photos DROP COLUMN official;",
        ),
    ]
