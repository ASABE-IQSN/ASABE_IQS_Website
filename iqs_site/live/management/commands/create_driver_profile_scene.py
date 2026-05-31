"""
Management command to create a portrait driver profile overlay scene.

Usage:
    python manage.py create_driver_profile_scene
    python manage.py create_driver_profile_scene --name "My Driver Card"

Canvas: 460 x 700 (portrait)
Layout:
  - Driver photo            (top, full width)
  - Name                    (below photo, centered)
  - Major | Year | Hometown (three stat columns, label + value)
  - Motto                   (full-width italic quote)
  - Bio                     (bottom, wrapped text)

Bindings used (set as `overlay_role` on each group question):
  photo, name, major, year, hometown, motto, bio
"""

from django.core.management.base import BaseCommand
from compforms.models import OverlayScene


# Note: font_size is expressed as a percentage of canvas HEIGHT (see the scene
# renderer in live_overlay.js). At 700px tall, 3.4 ≈ 24px, 2.0 ≈ 14px.
MUTED = "#94a3b8"
LABEL_STYLE = {
    "font_size": 1.4,
    "font_weight": 700,
    "color": MUTED,
    "background": "transparent",
    "border_radius": 0,
    "border": "",
    "text_align": "center",
    "text_transform": "uppercase",
    "letter_spacing": 0.5,
    "opacity": 1,
}
VALUE_STYLE = {
    "font_size": 2.1,
    "font_weight": 600,
    "color": "#ffffff",
    "background": "transparent",
    "border_radius": 0,
    "border": "",
    "text_align": "center",
    "opacity": 1,
}


def _stat(col_id, label, role, x, w):
    """A labelled stat column: small uppercase label above a value line."""
    return [
        {
            "id": f"el_{col_id}_label", "type": "text", "label": f"{label} Label",
            "x": x, "y": 48.5, "width": w, "height": 3,
            "binding": "", "content": label,
            "style": dict(LABEL_STYLE),
        },
        {
            "id": f"el_{col_id}", "type": "text", "label": label,
            "x": x, "y": 51.5, "width": w, "height": 5.5,
            "binding": role, "content": "",
            "style": dict(VALUE_STYLE),
        },
    ]


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

    # ── Driver photo (top ~34% of card) ──────────────────────────────────────
    {
        "id": "el_photo",
        "type": "image",
        "label": "Driver Photo",
        "x": 8, "y": 3, "width": 84, "height": 34,
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
        "x": 4, "y": 38, "width": 92, "height": 7.5,
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

    # ── Divider above the stat row ───────────────────────────────────────────
    {
        "id": "el_divider",
        "type": "rect",
        "label": "Divider",
        "x": 8, "y": 47, "width": 84, "height": 0.4,
        "binding": "", "content": "",
        "style": {
            "background": "rgba(148,163,184,.3)",
            "border_radius": 2,
            "border": "",
            "opacity": 1,
        },
    },

    # ── Stat columns: Major | Year | Hometown ────────────────────────────────
    *_stat("major",    "Major",    "major",    x=3,  w=31),
    *_stat("year",     "Year",     "year",     x=34.5, w=31),
    *_stat("hometown", "Hometown", "hometown", x=66, w=31),

    # ── Motto (full-width italic quote) ──────────────────────────────────────
    {
        "id": "el_motto_label", "type": "text", "label": "Motto Label",
        "x": 4, "y": 59, "width": 92, "height": 3,
        "binding": "", "content": "Motto",
        "style": dict(LABEL_STYLE),
    },
    {
        "id": "el_motto", "type": "text", "label": "Motto",
        "x": 6, "y": 62, "width": 88, "height": 5.5,
        "binding": "motto", "content": "",
        "style": {
            "font_size": 2.0,
            "font_weight": 500,
            "color": "#e2e8f0",
            "background": "transparent",
            "border_radius": 0,
            "border": "",
            "text_align": "center",
            "font_style": "italic",
            "white_space": "normal",
            "min_font_size": 1.2,
            "opacity": 1,
        },
    },

    # ── Divider above the bio ────────────────────────────────────────────────
    {
        "id": "el_divider2",
        "type": "rect",
        "label": "Divider 2",
        "x": 8, "y": 68, "width": 84, "height": 0.4,
        "binding": "", "content": "",
        "style": {
            "background": "rgba(148,163,184,.3)",
            "border_radius": 2,
            "border": "",
            "opacity": 1,
        },
    },

    # ── Bio (bottom, wrapped multi-line text) ────────────────────────────────
    {
        "id": "el_bio_label", "type": "text", "label": "Bio Label",
        "x": 4, "y": 69, "width": 92, "height": 3,
        "binding": "", "content": "Bio",
        "style": dict(LABEL_STYLE),
    },
    {
        "id": "el_bio",
        "type": "text",
        "label": "Bio",
        "x": 6, "y": 72.5, "width": 88, "height": 25,
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
            "white_space": "normal",
            "min_font_size": 1.0,
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
