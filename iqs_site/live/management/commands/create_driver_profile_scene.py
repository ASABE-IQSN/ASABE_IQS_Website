"""
Management command to create a portrait driver profile overlay scene.

Usage:
    python manage.py create_driver_profile_scene
    python manage.py create_driver_profile_scene --name "My Driver Card"

Canvas: 460 x 700 (portrait)
Layout:
  - Driver photo  (top, full width)
  - Name          (below photo, centered)
  - Stat 1 | Stat 2  (side by side)
  - Bio           (bottom, wrapped text)
"""

from django.core.management.base import BaseCommand
from compforms.models import OverlayScene


ELEMENTS = [
    # ── Background ───────────────────────────────────────────────────────────
    {
        "id": "el_bg",
        "type": "rect",
        "label": "Background",
        "x": 0, "y": 0, "width": 100, "height": 100,
        "binding": "", "content": "",
        "style": {
            "background": "rgba(15,23,42,0.92)",
            "border_radius": 16,
            "border": "1px solid rgba(148,163,184,.2)",
            "opacity": 1,
            "backdrop_filter": "blur(12px)",
        },
    },

    # ── Driver photo (top ~43% of card) ──────────────────────────────────────
    {
        "id": "el_photo",
        "type": "image",
        "label": "Driver Photo",
        "x": 8, "y": 3, "width": 84, "height": 42,
        "binding": "photo",
        "content": "",
        "style": {
            "object_fit": "cover",
            "border_radius": 12,
            "border": "2px solid rgba(148,163,184,.25)",
            "background": "rgba(148,163,184,.1)",
            "opacity": 1,
        },
    },

    # ── Name ─────────────────────────────────────────────────────────────────
    {
        "id": "el_name",
        "type": "text",
        "label": "Driver Name",
        "x": 4, "y": 47, "width": 92, "height": 9,
        "binding": "name",
        "content": "",
        "style": {
            "font_size": 3.4,
            "font_weight": 700,
            "color": "#ffffff",
            "background": "transparent",
            "border_radius": 0,
            "border": "",
            "text_align": "center",
            "opacity": 1,
        },
    },

    # ── Thin divider ─────────────────────────────────────────────────────────
    {
        "id": "el_divider",
        "type": "rect",
        "label": "Divider",
        "x": 8, "y": 57.5, "width": 84, "height": 0.4,
        "binding": "", "content": "",
        "style": {
            "background": "rgba(148,163,184,.3)",
            "border_radius": 2,
            "border": "",
            "opacity": 1,
        },
    },

    # ── Stat 1 (left) ────────────────────────────────────────────────────────
    {
        "id": "el_stat1",
        "type": "text",
        "label": "Stat 1",
        "x": 4, "y": 59, "width": 44, "height": 8,
        "binding": "stat_1",
        "content": "",
        "style": {
            "font_size": 2.4,
            "font_weight": 600,
            "color": "#94a3b8",
            "background": "transparent",
            "border_radius": 0,
            "border": "",
            "text_align": "center",
            "opacity": 1,
        },
    },

    # ── Stat 2 (right) ───────────────────────────────────────────────────────
    {
        "id": "el_stat2",
        "type": "text",
        "label": "Stat 2",
        "x": 52, "y": 59, "width": 44, "height": 8,
        "binding": "stat_2",
        "content": "",
        "style": {
            "font_size": 2.4,
            "font_weight": 600,
            "color": "#94a3b8",
            "background": "transparent",
            "border_radius": 0,
            "border": "",
            "text_align": "center",
            "opacity": 1,
        },
    },

    # ── Bio (bottom ~29% of card) ─────────────────────────────────────────────
    {
        "id": "el_bio",
        "type": "text",
        "label": "Bio",
        "x": 6, "y": 69, "width": 88, "height": 28,
        "binding": "bio",
        "content": "",
        "style": {
            "font_size": 1.9,
            "font_weight": 400,
            "color": "#cbd5e1",
            "background": "transparent",
            "border_radius": 0,
            "border": "",
            "text_align": "center",
            "opacity": 1,
        },
    },
]


class Command(BaseCommand):
    help = "Create a portrait driver profile overlay scene"

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            default="Driver Profile",
            help="Name for the new scene (default: 'Driver Profile')",
        )

    def handle(self, *args, **options):
        scene = OverlayScene.objects.create(
            name=options["name"],
            description="Portrait driver card: photo top, name + stats middle, bio bottom.",
            canvas_width=460,
            canvas_height=700,
            elements=ELEMENTS,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created OverlayScene '{scene.name}' (id={scene.scene_id})"
            )
        )
