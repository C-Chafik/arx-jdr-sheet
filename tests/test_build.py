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


def test_inventory_toggle_and_band_are_wired():
    html = build.render_html()
    css = build.build_css("x")
    assert 'name="attr_inventory_open"' in html
    assert 'class="sheet-inventory"' in html
    assert ".sheet-inventory-toggle:checked ~ .sheet-inventory" in css
    assert "Inventory-Button.png" in css
    assert "Inventory.png" in css


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


def test_items_catalog_loads():
    items = build.load_items()
    assert "krahoz" in items
    for item in items.values():
        assert item["cat"] in {"casque", "arme_principale", "arme_secondaire",
                               "bouclier", "armure_haute", "armure_basse",
                               "bijoux", "objet"}, item


def test_css_has_one_icon_rule_per_item():
    css = build.build_css("https://example.com/assets")
    for item_id, item in build.load_items().items():
        assert f'input[value="{item_id}"]' in css, item_id
        assert f"https://example.com/assets/{item['icon']}" in css, item_id


def test_worker_is_injected_with_catalog():
    html = build.render_html()
    assert html.count('<script type="text/worker">') == 1
    assert html.rstrip().endswith("</script>")
    assert "const ITEMS =" in html
    for item_id in build.load_items():
        assert f'"{item_id}"' in html, item_id


EQUIP_SLOTS = ["equip_head", "equip_torso", "equip_belt", "equip_main_hand",
               "equip_off_hand", "equip_jewel_1", "equip_jewel_2"]
PER_LEVEL = build.GRID_COLS * build.GRID_ROWS
TOTAL_BAG_SLOTS = PER_LEVEL * build.GRID_BAGS
ALL_SLOTS = [f"bag_{i}" for i in range(1, TOTAL_BAG_SLOTS + 1)] + EQUIP_SLOTS


def test_all_slots_have_input_icon_button_and_css():
    html = build.render_html()
    css = build.build_css("x")
    for slot in ALL_SLOTS:
        assert f'name="attr_{slot}"' in html, slot
        assert f'name="act_slot_{slot}"' in html, slot
        # bag slot positions are shared per-cell across levels (sheet-bag-cell-N),
        # not one CSS rule per absolute slot index
        if slot.startswith("bag_"):
            cell = (int(slot.split("_")[1]) - 1) % PER_LEVEL
            assert f"sheet-bag-cell-{cell}" in html, slot
        else:
            assert f".sheet-slot--{slot}" in css, slot
    for mirror in ("attr_hand", "attr_hand_from", "attr_hand_cat", "attr_fit",
                   "attr_bag_count", "attr_bag_level"):
        assert f'name="{mirror}"' in html, mirror


def test_items_have_valid_sizes():
    import re
    for item_id, item in build.load_items().items():
        assert re.fullmatch(r"[1-9]\d*x[1-9]\d*", item["size"]), item_id
        w, h = (int(n) for n in item["size"].split("x"))
        # must fit the bag grid, else the item is silently unplaceable
        assert w <= build.GRID_COLS and h <= build.GRID_ROWS, \
            f"{item_id}: {item['size']} exceeds the {build.GRID_COLS}x{build.GRID_ROWS} grid"


def test_hand_state_css_rules_exist():
    css = build.build_css("x")
    assert 'input[name="attr_hand_from"][value="bag_1"]' in css
    assert 'input[name="attr_hand_cat"][value="casque"]' in css
    # valid bag anchors glow from the worker-published fit mask, one rule per cell
    for i in (1, TOTAL_BAG_SLOTS // 2, TOTAL_BAG_SLOTS):
        assert f'input[name="attr_fit"][value*="|bag_{i}|"]' in css, i
    # no slot beyond the pre-wired levels (the band's rightmost column is the pouch)
    assert f"sheet-slot--bag_{TOTAL_BAG_SLOTS + 1}" not in css
    # equipment glow requires the slot to be empty (no swap)
    assert 'input[value=""] ~ button' in css


def test_bag_levels_pouch_and_nav_are_wired():
    html = build.render_html()
    css = build.build_css("x")
    assert 'name="act_slot_pouch"' in html
    assert 'name="act_bag_up"' in html
    assert 'name="act_bag_down"' in html
    # each level's cells are shown only when attr_bag_level matches
    for lvl in range(1, build.GRID_BAGS + 1):
        assert f'input[name="attr_bag_level"][value="{lvl}"] ~ .sheet-inventory .sheet-bag-level-{lvl}' in css, lvl
    # the pouch glows for the item(s) whose effect is extra_bag
    extra_bag_items = [i for i, it in build.load_items().items() if it.get("effect") == "extra_bag"]
    assert extra_bag_items, "expected at least one extra_bag item in the catalog"
    for item_id in extra_bag_items:
        assert f'input[name="attr_hand"][value="{item_id}"]' in css, item_id


def test_multicell_items_get_span_rules():
    css = build.build_css("x")
    spans = [item_id for item_id, item in build.load_items().items()
             if item["size"] != "1x1"]
    assert spans, "expected at least one multi-cell item in the catalog"
    for item_id in spans:
        assert f'.sheet-inventory .sheet-slot input[value="{item_id}"] + .sheet-item-icon' in css, item_id


def test_worker_has_pick_place_logic():
    html = build.render_html()
    assert "clicked:slot_" in html
    assert "EQUIP_ACCEPTS" in html
    assert "hand_from" in html
    assert "cellsFor" in html      # footprint math
    assert "fitMask" in html       # published valid anchors
    assert 'update[from] = here' not in html  # swap removed
    assert "clicked:slot_pouch" in html
    assert "extra_bag" in html
    assert "clicked:bag_up" in html
    assert "clicked:bag_down" in html


def test_item_name_billboards_and_hover_rules():
    html = build.render_html()
    css = build.build_css("x")
    for item_id, item in build.load_items().items():
        assert f'class="sheet-statbar sheet-statbar--item-{item_id}"' in html, item_id
        assert item["label"] in html, item_id
        assert f'.sheet-arx:has(.sheet-slot:hover input[value="{item_id}"])' in css, item_id


def test_dev_shim_stays_out_of_the_roll20_deliverable():
    build.build()
    preview = (build.BUILD / "preview.html").read_text(encoding="utf-8")
    sheet = (build.BUILD / "sheet.html").read_text(encoding="utf-8")
    assert "ARX dev shim" in preview
    assert "arx-devbar" in preview
    assert "ARX dev shim" not in sheet
    assert "arx-devbar" not in sheet


def test_mod_script_is_generated():
    build.build()
    mod = (build.BUILD / "arx-mod.js").read_text(encoding="utf-8")
    assert "!arxgive" in mod
    for item_id in build.load_items():
        assert f'"{item_id}"' in mod, item_id
