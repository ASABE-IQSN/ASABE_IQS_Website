import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0006_csrffailure"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ServerError",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("url", models.CharField(blank=True, default="", max_length=500)),
                ("method", models.CharField(blank=True, default="", max_length=16)),
                ("ip", models.CharField(blank=True, default="", max_length=45)),
                ("exception_type", models.CharField(blank=True, default="", max_length=255)),
                ("traceback", models.TextField(blank=True, default="")),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="server_errors",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "server_error_log",
                "ordering": ["-occurred_at"],
            },
        ),
    ]
