import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('compforms', '0005_image_and_overlay_layout'),
    ]

    operations = [
        migrations.CreateModel(
            name='OverlayScene',
            fields=[
                ('scene_id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('canvas_width', models.PositiveIntegerField(default=1920, help_text='Reference canvas width in px')),
                ('canvas_height', models.PositiveIntegerField(default=1080, help_text='Reference canvas height in px')),
                ('elements', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name='overlaylayout',
            name='scene',
            field=models.ForeignKey(
                blank=True,
                help_text='If set, the overlay renders this scene definition instead of the hardcoded template.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='layouts',
                to='compforms.overlayscene',
            ),
        ),
    ]
