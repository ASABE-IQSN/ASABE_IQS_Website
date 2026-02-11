from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0013_tractor_primary_photo"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""\
                ALTER TABLE performance_event_media
                  ADD COLUMN caption VARCHAR(255) NULL DEFAULT NULL,
                  ADD COLUMN approved TINYINT(1) NOT NULL DEFAULT 0,
                  ADD COLUMN uploaded_by_user_id INT NULL DEFAULT NULL,
                  ADD COLUMN submitted_from_ip VARCHAR(255) NULL DEFAULT NULL,
                  ADD COLUMN created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6);
            """,
            reverse_sql="""\
                ALTER TABLE performance_event_media
                  DROP COLUMN caption,
                  DROP COLUMN approved,
                  DROP COLUMN uploaded_by_user_id,
                  DROP COLUMN submitted_from_ip,
                  DROP COLUMN created_at;
            """,
        ),
    ]
