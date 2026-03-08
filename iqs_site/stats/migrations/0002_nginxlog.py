from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="NginxLog",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ip", models.CharField(db_index=True, max_length=45)),
                ("time", models.DateTimeField(db_index=True)),
                ("method", models.CharField(max_length=16)),
                ("url", models.CharField(db_index=True, max_length=2048)),
                ("query_string", models.CharField(blank=True, default="", max_length=2048)),
                ("protocol", models.CharField(blank=True, default="", max_length=16)),
                ("status_code", models.SmallIntegerField(db_index=True)),
                ("bytes_sent", models.BigIntegerField()),
                ("referer", models.CharField(blank=True, default="", max_length=2048)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("source_hash", models.CharField(max_length=64, unique=True)),
            ],
            options={
                "db_table": "nginx_log",
            },
        ),
        migrations.AddIndex(
            model_name="NginxLog",
            index=models.Index(fields=["time", "status_code"], name="nginx_log_time_status_idx"),
        ),
        migrations.AddIndex(
            model_name="NginxLog",
            index=models.Index(fields=["ip", "time"], name="nginx_log_ip_time_idx"),
        ),
    ]
