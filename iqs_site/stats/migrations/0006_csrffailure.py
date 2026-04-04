import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0005_failed_signup"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CsrfFailure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("ip", models.CharField(blank=True, default="", max_length=45)),
                ("path", models.CharField(blank=True, default="", max_length=500)),
                ("reason", models.CharField(blank=True, default="", max_length=255)),
                ("referer", models.CharField(blank=True, default="", max_length=2048)),
                ("user_agent", models.TextField(blank=True, default="")),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="csrf_failures",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "csrf_failure",
                "ordering": ["-occurred_at"],
                "indexes": [
                    models.Index(fields=["occurred_at", "ip"], name="csrf_failur_occurre_idx"),
                ],
            },
        ),
    ]
