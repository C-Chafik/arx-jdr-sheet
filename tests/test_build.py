import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import build


def test_sheet_html_is_a_fragment():
    html = build.render_html()
    for forbidden in ("<html", "<head", "<body", "<script src", "<iframe", "style="):
        assert forbidden not in html, forbidden


def test_css_asset_base_is_substituted():
    css = build.build_css("https://example.com/assets")
    assert "https://example.com/assets/ARX-BASE.png" in css
    assert "{{ASSET_BASE}}" not in css


def test_build_writes_the_four_outputs():
    build.build()
    for name in ("sheet.html", "sheet.css", "preview.html", "preview.css"):
        assert (build.BUILD / name).exists(), name


ATTRS = [
    "character_name",
    "level",
    "strength", "mental", "dexterity", "constitution",
    "stealth", "technical", "intuition",
    "ethereal_link", "object_knowledge", "casting",
    "close_combat", "projectile", "defense",
    "health", "health_max", "mana", "mana_max",
    "damages", "armor_class", "magic_resistance", "poison_resistance",
]


def test_sheet_html_contains_every_attribute():
    html = build.render_html()
    for attr in ATTRS:
        assert f'name="attr_{attr}"' in html, attr


POSITIONED_FIELDS = [a for a in ATTRS if not a.endswith("_max")]


def test_css_positions_every_field():
    css = build.build_css("x")
    for name in POSITIONED_FIELDS:
        assert f".sheet-field--{name}" in css, name


HOVER_STATS = [a for a in POSITIONED_FIELDS if a not in ("level", "character_name")]
NO_ROLL = ["health", "mana"]  # hover-only icons, not clickable


def test_every_icon_has_hover_zone_statbar_and_css():
    html = build.render_html()
    css = build.build_css("x")
    for name in HOVER_STATS:
        assert f'class="sheet-hover-zone sheet-hover--{name}"' in html, name
        if name in NO_ROLL:
            assert f'name="roll_{name}"' not in html, name
        else:
            assert f'name="roll_{name}"' in html, name
        assert f'class="sheet-statbar sheet-statbar--{name}"' in html, name
        assert f".sheet-hover--{name} " in css or f".sheet-hover--{name}," in css, name
        assert f".sheet-hover--{name}:hover" in css, name
