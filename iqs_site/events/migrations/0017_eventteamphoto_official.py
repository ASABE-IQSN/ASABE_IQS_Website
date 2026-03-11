from django.db import migrations


def add_official_column(apps, schema_editor):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = 'event_team_photos'"
        )
        if cursor.fetchone()[0] == 0:
            return

        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'event_team_photos' "
            "AND column_name = 'official'"
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "ALTER TABLE event_team_photos ADD COLUMN official TINYINT(1) NOT NULL DEFAULT 0"
            )


def drop_official_column(apps, schema_editor):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'event_team_photos' "
            "AND column_name = 'official'"
        )
        if cursor.fetchone()[0] > 0:
            cursor.execute("ALTER TABLE event_team_photos DROP COLUMN official")


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0016_alter_editlog_team_alter_editlog_tractor'),
    ]

    operations = [
        migrations.RunPython(add_official_column, drop_official_column),
    ]
