from django.db import migrations


def create_views_indexes(apps, schema_editor):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = 'views'"
        )
        if cursor.fetchone()[0] == 0:
            return

        indexes = [
            # Index on time alone — covers daily_activity's primary filter
            ("idx_views_time", "CREATE INDEX idx_views_time ON views (time)"),
            # Composite (ip, time) — covers location_drill: WHERE ip IN (...) AND time BETWEEN ...
            ("idx_views_ip_time", "CREATE INDEX idx_views_ip_time ON views (ip, time)"),
            # Composite (url, time) — covers auth-status geo filter: WHERE url = '...' AND time ...
            ("idx_views_url_time", "CREATE INDEX idx_views_url_time ON views (url, time)"),
        ]

        for index_name, create_sql in indexes:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND table_name = 'views' "
                "AND index_name = %s",
                [index_name],
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(create_sql)


def drop_views_indexes(apps, schema_editor):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = 'views'"
        )
        if cursor.fetchone()[0] == 0:
            return

        for index_name in ("idx_views_time", "idx_views_ip_time", "idx_views_url_time"):
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND table_name = 'views' "
                "AND index_name = %s",
                [index_name],
            )
            if cursor.fetchone()[0] > 0:
                cursor.execute(f"DROP INDEX {index_name} ON views")


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0011_remove_userprofile_committee_title_and_more'),
    ]

    operations = [
        migrations.RunPython(create_views_indexes, drop_views_indexes),
    ]
