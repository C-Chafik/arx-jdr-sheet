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


def test_legendary_items_get_permanent_glow_and_red_hover_text():
    # Synthetic catalog: no item in the real items.json is legendary yet,
    # so this exercises the actual .j2 templates with controlled input
    # rather than depending on production data.
    fake_items = {
        "legendary-sword": {"label": "Épée légendaire", "icon": "item-fake.png",
                             "cat": "arme_principale", "size": "1x2", "legendary": True},
        "plain-apple": {"label": "Pomme", "icon": "item-apple.png",
                        "cat": "objet", "size": "1x1"},
    }
    css = build.jinja_env().get_template("css/inventory-slots.css.j2").render(
        items=fake_items, cols=build.GRID_COLS, rows=build.GRID_ROWS, bags=build.GRID_BAGS
    )
    assert "drop-shadow" in css
    assert ".sheet-statbar--item-legendary-sword { color: #ff2b2b; }" in css
    # the non-legendary item must NOT get either effect
    apple_icon_rule = css.split('input[value="plain-apple"] + .sheet-item-icon {')[1].split("}")[0]
    assert "drop-shadow" not in apple_icon_rule
    assert ".sheet-statbar--item-plain-apple { color:" not in css

    html = build.jinja_env().get_template("sheet.html.j2").render(
        items=fake_items, spells=build.load_spells(),
        cols=build.GRID_COLS, rows=build.GRID_ROWS, bags=build.GRID_BAGS
    )
    assert '★ Épée légendaire' in html
    assert '>Pomme<' in html  # non-legendary label carries no star


def test_currency_items_have_effect_and_value():
    for item_id, item in build.load_items().items():
        if item.get("effect") == "currency":
            assert isinstance(item.get("value"), int) and item["value"] > 0, item_id


def test_purse_gold_system_is_wired():
    html = build.render_html()
    css = build.build_css("x")
    assert 'name="act_slot_purse"' in html
    assert 'class="sheet-gold-readout"' in html
    assert 'name="attr_gold"' in html
    assert 'name="attr_hand_effect"' in html
    assert "clicked:slot_purse" in html
    assert '"currency"' in html or "currency" in html
    assert 'input[name="attr_hand_effect"][value="currency"] ~ .sheet-inventory .sheet-purse' in css
    assert ".sheet-purse:hover ~ .sheet-gold-readout" in css
    assert '"gold-one"' in html  # withdraw path spawns a gold-one coin


def test_trash_deletes_held_item():
    html = build.render_html()
    css = build.build_css("x")
    assert 'name="act_trash"' in html
    assert "clicked:trash" in html
    assert 'input[name="attr_hand"]:not([value=""]) ~ .sheet-inventory .sheet-trash' in css


def test_custom_cursors_are_wired():
    css = build.build_css("x")
    assert "mouse-hover.png" in css
    assert "points-hover.png" in css
    assert "selected-hover.png" in css
    assert "base-hover-2.png" in css
    assert 'input[name="attr_hand"]:not([value=""]) ~ .sheet-inventory .sheet-purse' in css


def test_armor_slots_use_the_enlarged_frame():
    css = build.build_css("x")
    assert "Armory-slot.png" in css
    for slot in ("equip_head", "equip_torso", "equip_belt"):
        assert f".sheet-slot--{slot}" in css, slot


def test_magic_page_navigation_is_wired():
    html = build.render_html()
    css = build.build_css("x")
    assert 'id="sheet-tab-magic"' in html
    assert 'for="sheet-tab-magic"' in html
    assert 'for="sheet-tab-base"' in html
    assert 'class="sheet-page sheet-page--magic"' in html
    assert ".sheet-tab-radio--magic:checked ~ .sheet-page--magic" in css
    assert "ARX-MAGICBOOK.png" in css
    assert ".sheet-tab-radio--magic:checked ~ .sheet-nav--base" in css
    assert ".sheet-tab-radio--magic:checked ~ .sheet-nav--magic" in css


def test_rune_items_have_rune_effect():
    for item_id, item in build.load_items().items():
        if item_id.startswith("rune-"):
            assert item.get("effect") == "rune", item_id


def test_spellbook_and_grimoire_are_wired():
    html = build.render_html()
    css = build.build_css("x")
    for i in range(1, 21):
        assert f'name="attr_spellbook_{i}"' in html, i
        assert f".sheet-spellbook-slot--{i}" in css, i
    assert 'name="act_slot_grimoire"' in html
    assert "clicked:slot_grimoire" in html
    assert "item-magicbook-" in css  # derived from item-rune-* via the replace filter
    assert 'input[name="attr_hand_effect"][value="rune"] ~ .sheet-book .sheet-grimoire' in css
    rune_ids = [k for k, v in build.load_items().items() if v.get("effect") == "rune"]
    assert rune_ids
    for rid in rune_ids:
        assert f'class="sheet-statbar sheet-spell-statbar sheet-statbar--spell-{rid}"' in html, rid
        assert f".sheet-spellbook-slot:hover input[value=\"{rid}\"]" in css, rid


def test_spells_catalog_loads():
    spells = build.load_spells()
    assert spells
    for spell in spells.values():
        assert 1 <= spell["page"] <= 10, spell
        assert 1 <= spell["slot"] <= 4, spell
        assert spell["runes"]
        for rune_id in spell["runes"]:
            assert rune_id in build.load_items(), rune_id


def test_spell_page_navigation_is_wired():
    html = build.render_html()
    css = build.build_css("x")
    pages_with_spells = {s["page"] for s in build.load_spells().values()}
    for p in range(1, 11):
        assert f'id="sheet-spell-page-{p}"' in html, p
        assert f'for="sheet-spell-page-{p}"' in html, p
        assert f".sheet-spell-page-tab--{p} {{ background-image: url('x/magic-nav-{p}.png'); }}" in css, p
    # page 1 is always visible; other pages only if they have a spell
    assert ".sheet-spell-page-tab--1 { display: block; }" in css
    for p in range(2, 11):
        rule = f".sheet-spell-page-tab--{p} {{ display: block; }}"
        if p in pages_with_spells:
            assert rule in css, p
        else:
            assert rule not in css, p


def test_spell_with_icon_renders_image_not_text():
    # Synthetic: the real catalog's spell has no icon yet (art not delivered).
    fake_spells = {
        "test-spell": {"label": "Test Spell", "runes": ["rune-aam"],
                       "page": 1, "slot": 2, "icon": "item-fake-spell.png"},
    }
    html = build.jinja_env().get_template("partials/pages/magic.html.j2").render(
        items=build.load_items(), spells=fake_spells)
    css = build.jinja_env().get_template("css/magic-slots.css.j2").render(
        items=build.load_items(), spells=fake_spells,
        cols=build.GRID_COLS, rows=build.GRID_ROWS, bags=build.GRID_BAGS)
    assert '<span class="sheet-spell-icon"></span>' in html
    assert "Test Spell" not in html  # icon present -> no text fallback
    assert ".sheet-spell-slot--test-spell .sheet-spell-icon" in css
    assert "item-fake-spell.png" in css

    # The real spell (no icon) still falls back to its text label.
    real_html = build.render_html()
    for spell_id, spell in build.load_spells().items():
        if not spell.get("icon"):
            assert f">{spell['label']}<" in real_html, spell_id


def test_spell_visibility_requires_page_and_all_runes():
    html = build.render_html()
    css = build.build_css("x")
    for spell_id, spell in build.load_spells().items():
        assert f'class="sheet-spell-slot sheet-spell-slot--slot-{spell["slot"]} sheet-spell-slot--{spell_id}"' in html, spell_id
        expected = f'.sheet-arx:has(input[name="attr_spell_page"][value="{spell["page"]}"]:checked)'
        for rune_id in spell["runes"]:
            expected += f':has(input[name="attr_known_{rune_id[5:]}"][value="1"])'
        expected += f" .sheet-spell-slot--{spell_id}"
        assert expected in css, spell_id
    for item_id, item in build.load_items().items():
        if item.get("effect") == "rune":
            assert f'name="attr_known_{item_id[5:]}"' in html, item_id


def test_dev_shim_stays_out_of_the_roll20_deliverable():
    build.build()
    preview = (build.BUILD / "preview.html").read_text(encoding="utf-8")
    sheet = (build.BUILD / "sheet.html").read_text(encoding="utf-8")
    assert "ARX dev shim" in preview
    assert "arx-devbar" in preview
    assert "ARX dev shim" not in sheet
    assert "arx-devbar" not in sheet
    assert 'id="arx-give-runes"' in preview
    assert 'id="arx-give-runes"' not in sheet


def test_mod_script_is_generated():
    build.build()
    mod = (build.BUILD / "arx-mod.js").read_text(encoding="utf-8")
    assert "!arxgive" in mod
    for item_id in build.load_items():
        assert f'"{item_id}"' in mod, item_id
