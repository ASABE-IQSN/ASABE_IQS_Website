from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0011_remove_userprofile_committee_title_and_more'),
    ]

    operations = [
        # Index on time alone — covers daily_activity's primary filter
        # (Django translates time__date=X to a range query, so a btree index works)
        migrations.RunSQL(
            sql="CREATE INDEX idx_views_time ON views (time);",
            reverse_sql="DROP INDEX idx_views_time ON views;",
        ),
        # Composite (ip, time) — covers location_drill: WHERE ip IN (...) AND time BETWEEN ...
        migrations.RunSQL(
            sql="CREATE INDEX idx_views_ip_time ON views (ip, time);",
            reverse_sql="DROP INDEX idx_views_ip_time ON views;",
        ),
        # Composite (url, time) — covers auth-status geo filter: WHERE url = '...' AND time ...
        migrations.RunSQL(
            sql="CREATE INDEX idx_views_url_time ON views (url, time);",
            reverse_sql="DROP INDEX idx_views_url_time ON views;",
        ),
    ]
