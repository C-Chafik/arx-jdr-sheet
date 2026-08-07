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
    assert "https://example.com/assets/book/base.png" in css
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
NO_ROLL = ["health", "mana", "strength", "mental", "dexterity", "constitution",
           "armor_class", "magic_resistance", "poison_resistance"]  # hover-only icons, not clickable


def test_inventory_toggle_and_band_are_wired():
    html = build.render_html()
    css = build.build_css("x")
    assert 'name="attr_inventory_open"' in html
    assert 'class="sheet-inventory"' in html
    assert 'name="act_inventory_toggle"' in html
    assert "clicked:inventory_toggle" in html
    assert '.sheet-arx:has(input[name="attr_inventory_open"][value="1"]) .sheet-inventory {' in css
    assert "ui/inventory-button.png" in css
    assert "ui/inventory-band.png" in css


def test_every_icon_has_hover_zone_statbar_and_css():
    html = build.render_html()
    css = build.build_css("x")
    for name in HOVER_STATS:
        # Substring, not an exact class= match: skills carry an extra
        # sheet-roll--no-focus/sheet-roll--focus class (see below).
        assert f'sheet-hover-zone sheet-hover--{name}' in html, name
        if name in NO_ROLL:
            assert f'name="roll_{name}"' not in html, name
        elif name == "damages":
            # Needs an item lookup (equipped weapon's label) a static roll
            # value can't do — type="action" + startRoll instead, see
            # clicked:roll_damages in inventory.js.
            assert 'name="act_roll_damages"' in html, name
        else:
            # Skills: two roll buttons (plain + Focus variant), swapped via
            # CSS on attr_posture=focus — see base.css.j2's sheet-roll--focus
            # rules and base.html.j2's roll_value_focus.
            assert f'name="roll_{name}"' in html, name
            assert f'name="roll_{name}_focus"' in html, name
        assert f'class="sheet-statbar sheet-statbar--{name}"' in html, name
        assert f".sheet-hover--{name} " in css or f".sheet-hover--{name}," in css, name
        assert f".sheet-hover--{name}:hover" in css, name


def test_items_catalog_loads():
    items = build.load_items()
    assert "krahoz" in items
    for item in items.values():
        assert item["cat"] in {"casque", "main_principale", "ambidextrie",
                               "main_secondaire", "deux_mains", "armure_haute", "armure_basse",
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
                             "cat": "main_principale", "size": "1x2", "legendary": True},
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
        items=fake_items, spells=build.load_spells(), presets=build.load_presets(),
        cols=build.GRID_COLS, rows=build.GRID_ROWS, bags=build.GRID_BAGS
    )
    assert '★ Épée légendaire' in html
    assert '>Pomme<' in html  # non-legendary label carries no star


MIN_ATTRS = ["strength", "mental", "dexterity", "constitution"]


def test_min_attributes_are_positive_ints_when_present():
    for item_id, item in build.load_items().items():
        for attr in MIN_ATTRS:
            key = "min_" + attr
            if key in item:
                assert isinstance(item[key], int) and item[key] >= 1, f"{item_id}.{key}"
        # a min_ key on anything but the four attributes is silently ignored
        for key in item:
            if key.startswith("min_"):
                assert key[4:] in MIN_ATTRS, f"{item_id}: {key} is not enforced"


def test_min_attributes_block_equipping():
    html = build.render_html()
    # the guard itself, on the equip branch only (bag/purse/loot stay free)
    assert "function tooHeavy(" in html
    assert 'const MIN_STATS = ["strength", "mental", "dexterity", "constitution"]' in html
    assert 'Number(item["min_" + stat])' in html
    assert "if (tooHeavy(v, hand)) { return; }" in html
    # the check needs all four attributes in the click handler's getAttrs
    assert '["hand", "hand_from", "bag_count"]).concat(MIN_STATS)' in html
    # ...and mirrors the verdict for CSS at pickup time
    assert 'name="attr_hand_too_heavy"' in html
    assert "hand_too_heavy: tooHeavy(v, item)" in html


def test_equipment_specs_render_in_the_tooltip():
    fake_items = {
        "heavy-blade": {"label": "Lame lourde", "icon": "i.png", "cat": "deux_mains",
                        "size": "1x3", "weap_dmg": "2d20", "strength": 10, "stealth": -20,
                        "special": "Paralyse temporairement l'ennemi",
                        "min_strength": 20, "min_dexterity": 15},
        "plain-blade": {"label": "Lame simple", "icon": "i.png", "cat": "main_principale",
                        "size": "1x3", "weap_dmg": "2d20", "strength": 10, "stealth": -20,
                        "min_strength": 20, "min_dexterity": 15},
        "helm": {"label": "Casque de Poxelis", "icon": "i.png", "cat": "casque", "size": "1x1",
                 "armor_class": 5, "magic_resistance": 10, "mental": 5, "dexterity": -2,
                 "special": "Conjure les illusions", "min_constitution": 10, "min_mental": 8},
        "buckler": {"label": "Rondache", "icon": "i.png", "cat": "main_secondaire",
                    "size": "2x2", "armor_class": 3},
        "ring": {"label": "Anneau", "icon": "i.png", "cat": "bijoux", "size": "1x1",
                 "mental": 3, "casting": 8, "magic_resistance": 5,
                 "special": "Murmure les secrets des morts"},
        "plain-apple": {"label": "Pomme", "icon": "i.png", "cat": "objet", "size": "1x1",
                        "effect": "food"},
    }
    html = build.jinja_env().get_template("sheet.html.j2").render(
        items=fake_items, spells=build.load_spells(), presets=build.load_presets(),
        cols=build.GRID_COLS, rows=build.GRID_ROWS, bags=build.GRID_BAGS
    )
    def spec(label):
        return html.split(label, 1)[1].split("</div>")[0].replace(
            '<span class="sheet-item-specs">', "").replace("</span>", "")
    assert spec("Lame lourde") == (
        " - [2d20 | +10 FOR; -20 DIS | Paralyse temporairement l\'ennemi"
        " | (20 FOR; 15 DEX) | 2H]")
    # no effect on this one: the section is dropped, never left empty
    assert spec("Lame simple") == " - [2d20 | +10 FOR; -20 DIS | (20 FOR; 15 DEX) | 1H]"
    # armour leads with its defensive block, and CA/CAM/CAP stay out of the bonuses
    assert spec("Casque de Poxelis") == (
        " - [5 CA - 10 CAM | +5 MEN; -2 DEX | Conjure les illusions | (8 MEN; 10 CON)]")
    # a shield is armour that occupies a hand: defensive block AND hand code
    assert spec("Rondache") == " - [3 CA | ADD]"
    # a jewel has neither block nor hand: CAM stays inline with the other stats
    assert spec("Anneau") == " - [+3 MEN; +8 INC; +5 CAM | Murmure les secrets des morts]"
    # a plain object keeps a bare label: no bracket, and its reserved effect
    # ("food", a behaviour) is never mistaken for prose and printed
    assert 'sheet-statbar--item-plain-apple">Pomme</div>' in html


def test_effect_stays_a_typed_behaviour():
    """Prose belongs in "special"; "effect" only ever carries one of the eight
    behaviours the code actually reacts to. Any other value does nothing, and
    does it silently."""
    RESERVED = {"scroll", "rune", "currency", "extra_bag", "map_card",
                "food", "drinks", "potions"}
    for item_id, item in build.load_items().items():
        if "effect" in item:
            assert item["effect"] in RESERVED, f"{item_id}: {item['effect']} is wired to nothing"


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
    assert 'input[name="attr_hand_effect"][value="currency"] ~ .sheet-purse' in css
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
    assert "cursor-default.png" in css
    # cursor-points.png is retired — stat hover zones now use cursor-hover.png,
    # same as every other interactive element.
    assert "cursor-points.png" not in css
    assert "cursor-hover.png" in css
    assert 'input[name="attr_hand"]:not([value=""]) ~ .sheet-purse' in css


def test_armor_slots_use_the_enlarged_frame():
    css = build.build_css("x")
    assert "ui/armory-slot.png" in css
    for slot in ("equip_head", "equip_torso", "equip_belt"):
        assert f".sheet-slot--{slot}" in css, slot


def test_magic_page_navigation_is_wired():
    html = build.render_html()
    css = build.build_css("x")
    assert 'name="act_goto_magic"' in html
    assert 'name="act_goto_base"' in html
    assert "clicked:goto_magic" in html
    assert "clicked:goto_base" in html
    assert 'class="sheet-page sheet-page--magic"' in html
    assert '.sheet-arx:has(input[name="attr_sheet_tab"][value="magic"]) .sheet-page--magic' in css
    assert "book/magicbook.png" in css
    assert '.sheet-arx:has(input[name="attr_sheet_tab"][value="magic"]) .sheet-nav--magic { display: none; }' in css


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
    assert "runes/magicbook-" in css  # derived from runes/* via the replace filter
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
    spells = build.load_spells()
    assert '"clicked:goto_spellpage_" + p' in html
    for p in range(1, 11):
        assert f'name="act_goto_spellpage_{p}"' in html, p
        assert f".sheet-spell-page-tab--{p} {{ background-image: url('x/book/magicbook-nav-{p}.png?v={build.ASSET_VERSION}'); }}" in css, p
    # page 1 is always visible, even with no rune known yet
    assert ".sheet-spell-page-tab--1 { display: block; }" in css
    # other pages only open once at least one of their spells is fully known —
    # never a bare unconditional rule (that would leak an unearned page).
    for p in range(2, 11):
        bare_rule = f".sheet-spell-page-tab--{p} {{ display: block; }}"
        assert bare_rule not in css, p
        spells_here = [s for s in spells.values() if s["page"] == p]
        assert spells_here, p
        first = spells_here[0]
        chain = "".join(f':has(input[name="attr_known_{r[5:]}"][value="1"])' for r in first["runes"])
        assert f".sheet-arx{chain} .sheet-spell-page-tab--{p}" in css, p


def test_spell_with_icon_renders_image_not_text():
    # Synthetic: the real catalog's spell has no icon yet (art not delivered).
    fake_spells = {
        "test-spell": {"label": "Test Spell", "runes": ["rune-aam"],
                       "page": 1, "slot": 2, "icon": "item-fake-spell.png"},
    }
    html = build.jinja_env().get_template("partials/pages/magic.html.j2").render(
        items=build.load_items(), spells=fake_spells)
    css = build.jinja_env().get_template("css/magic-slots.css.j2").render(
        items=build.load_items(), spells=fake_spells, presets=build.load_presets(),
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
        expected = f'.sheet-arx:has(input[name="attr_spell_page"][value="{spell["page"]}"])'
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
    assert "!arxlearnall" in mod
    assert "!arxpreset" in mod
    assert "!arxpage" in mod
    assert "!arxtab" in mod
    for item_id in build.load_items():
        assert f'"{item_id}"' in mod, item_id


def _loot_skins():
    """(id, label) pairs from the shared Jinja data file."""
    module = build.jinja_env().get_template("data/loot.j2").module
    return list(module.loot_skins)


def test_loot_strip_skins_match_the_mod():
    import re
    # The mod is plain JS with no data file of its own, so the sheet's skin
    # list can only be kept honest by reading ARX_LOOT_SKINS back out of it.
    mod = build.render_mod()
    line = [ln for ln in mod.splitlines() if "const ARX_LOOT_SKINS" in ln]
    assert len(line) == 1, line
    mod_skins = re.findall(r'"([^"]+)"', line[0])
    assert [skin for skin, _ in _loot_skins()] == mod_skins


def test_loot_strip_opens_every_skin_and_closes():
    html = build.render_html()
    css = build.build_css("x")
    for skin, label in _loot_skins():
        name = skin.replace("-", "_")
        assert f'name="act_gm_loot_open_{name}" value="!arxlootopen {skin}"' in html, skin
        assert f'<span class="sheet-gm-loot-face">{label}</span>' in html, skin
        assert f".sheet-gm-loot-btn--{skin} .sheet-gm-loot-face" in css, skin
        assert f"url('x/ui/loot-{skin}.png?v={build.ASSET_VERSION}')" in css, skin
    assert 'name="act_gm_loot_close" value="!arxlootclose"' in html


def test_loot_strip_swaps_on_the_open_pool_and_hides_with_the_panel():
    css = build.build_css("x")
    panel_open = '.sheet-arx:has(input[name="attr_gm_panel_open"][value="1"])'
    pool_open = ':has(input[name="attr_gm_panel_loot_open"][value="1"])'
    # nothing at all until the panel is open
    assert ".sheet-gm-loot-btn {\n  display: none;" in css
    assert f"{panel_open} .sheet-gm-loot-btn--skin {{\n  display: block;" in css
    # ...and the skins give way to the close button once a pool is open
    assert f"{panel_open}{pool_open} .sheet-gm-loot-btn--skin {{\n  display: none;" in css
    assert f"{panel_open}{pool_open} .sheet-gm-loot-btn--close {{\n  display: block;" in css


def test_loot_strip_stays_inside_the_sheet_and_clear_of_the_search_bar():
    import re
    css = build.build_css("x")
    rows = {}
    for skin, _ in _loot_skins():
        block = css.split(f".sheet-gm-loot-btn--{skin} {{")[1].split("}")[0]
        left, top, width = (int(re.search(rf"{p}: (\d+)px", block).group(1))
                            for p in ("left", "top", "width"))
        # the search input sits at top 685 height 28, .sheet-arx is 1500 × 801
        assert top >= 713, (skin, top)
        assert top + 38 <= 801, (skin, top)
        assert left >= 1255 and left + width <= 1445, (skin, left, width)
        rows.setdefault(top, []).append((left, left + width))
    for top, spans in rows.items():
        spans.sort()
        for (_, end), (start, _) in zip(spans, spans[1:]):
            assert start >= end, (top, spans)  # no overlap inside a row


def test_gm_panel_does_not_touch_stats():
    """Removed on request: unlocking the panel only opens the admin catalog."""
    html = build.render_html()
    assert "GM_LEVEL" not in html
    assert "GM_ATTR" not in html
    assert "GM_GAUGE_MAX" not in html
    assert "forceGmStats" not in html
    # no stat listener reads the flag any more — the CSS gate is its only use
    for block in ("function recomputeGaugeMax(v) {", 'on("change:" + attr, function () {'):
        assert "gm_panel_unlocked" not in html.split(block)[1].split("\n}")[0]
    # the caps stand for everyone, GM sheet included
    skill_cap = html.split('on("change:" + skill, function () {')[1].split("});")[0]
    assert "gm_panel_unlocked" not in skill_cap
    assert "125" in skill_cap


def test_gauges_have_no_auto_shrink():
    """Removed on request: the gauge maxes follow their plain formula."""
    html = build.render_html()
    css = build.build_css("x")
    assert "max_size" not in html
    assert "max_size" not in css


CONSUMABLE_EFFECTS = ["food", "drinks", "potions"]


def test_consumables_are_wired_end_to_end():
    html = build.render_html()
    css = build.build_css("x")
    items = build.load_items()
    # the catalog actually carries the three effects
    for effect in CONSUMABLE_EFFECTS:
        assert any(i.get("effect") == effect for i in items.values()), effect
    # both halves are the mod's job: a worker's startRoll renders a roll
    # template and never an emote, and Roll20 does not fire clicked: for a
    # type="roll" button (tested in game) — so nothing is left sheet-side
    assert 'value="!arxconsume"' in html
    assert "consume_phrase" not in html
    assert 'on("clicked:consume"' not in html
    mod = build.render_mod()
    handler = mod.split('indexOf("!arxconsume") !== 0) { return; }')[1].split("\n});")[0]
    assert "arxResolveCharacterForPlayer(msg)" in handler   # player-triggered
    assert "playerIsGM" not in handler                      # ...so no GM gate, like !arxloottake
    assert 'sendChat("character|" + charId, "/me "' in handler
    assert "arxCellsFor(" in handler                        # frees the whole footprint
    # one reveal rule per effect, and the button shares the scroll button's spot
    for effect in CONSUMABLE_EFFECTS:
        assert (f'input[name="attr_hand_effect"][value="{effect}"] ~ '
                f'.sheet-inventory .sheet-consume {{ display: block; }}') in css, effect
    assert ">Consommer</span>" in html


def test_consume_verbs_cover_exactly_the_effects_used():
    """The verbs live in the mod, the reveal rules in CSS and the values in
    items.json — three places that must not drift apart."""
    import json
    import re
    mod = build.render_mod()
    verbs = mod.split("const ARX_CONSUME_VERBS = {")[1].split("}")[0]
    in_worker = sorted(re.findall(r"(\w+):", verbs))
    assert in_worker == sorted(CONSUMABLE_EFFECTS), in_worker
    # the command must be listed in !arxhelp like every other one
    assert "!arxconsume — pas pour le MJ" in mod
    css = build.build_css("x")
    in_css = sorted(set(re.findall(r'attr_hand_effect"\]\[value="(\w+)"\] ~ '
                                   r'.sheet-inventory .sheet-consume', css)))
    assert in_css == sorted(CONSUMABLE_EFFECTS), in_css
    # an item is a scroll OR food, never both: that is what lets the two
    # buttons share one spot in the band
    in_items = {i["effect"] for i in build.load_items().values() if "effect" in i}
    assert in_items.issuperset(CONSUMABLE_EFFECTS)
    assert "scroll" in in_items


WEAPON_DICE = {"one-handed-sword-light": "1d4", "wooden-club": "1d6",
               "one-handed-sword": "1d8", "bow": "1d8", "sam-sword": "2d20"}


def test_weapon_dice_are_well_formed_and_only_on_weapons():
    import re
    items = build.load_items()
    for item_id, item in items.items():
        if "weap_dmg" not in item:
            continue
        assert re.fullmatch(r"[1-9]\d*d[1-9]\d*", item["weap_dmg"]), item_id
        # dice on a shield or a loaf of bread would silently never be rolled
        assert item["cat"] in ("main_principale", "ambidextrie", "deux_mains"), \
            f"{item_id}: {item['cat']} never reaches the damage roll"
    for item_id, dice in WEAPON_DICE.items():
        assert items[item_id]["weap_dmg"] == dice, item_id


def test_damage_roll_is_computed_in_the_worker():
    html = build.render_html()
    handler = html.split('on("clicked:roll_damages"')[1].split("\n});")[0]
    # RNG is the eleven-step ladder 0, 0.1 … 1.0, not a continuous draw
    assert "Math.floor(Math.random() * 11) / 10" in handler
    assert "const base = offensive ? damages : Math.round(damages * (0.8 + 0.2 * rng));" in handler
    # Offensive takes each die at its maximum instead of rolling it
    assert "values.push(offensive ? weapon.dice.faces : rollDie(weapon.dice.faces));" in handler
    # one row per weapon, keyed by its own label, every die spelled out
    assert 'rows += " {{" + weapon.label + "=" + values.join(" + ") + "}}"' in handler
    # the total is accumulated here, never rebuilt by finishRoll
    assert "values.forEach(function (value) { total += value; });" in handler
    assert "finishRoll(results.rollId, {})" in handler
    # nothing left of the version whose Total displayed 0
    for gone in ("Hasard", "{{Stat=", "{{Arme=", "[[1d100]]", "{{Total=[[0]]}}", "diceMax"):
        assert gone not in handler, gone
    # a two-handed weapon mirrors itself into the off hand: count it once
    assert 'mainItem.cat === "deux_mains"' in handler
    assert '[v.equip_main_hand, mirroredTwoHanded ? "" : v.equip_off_hand]' in handler


def test_damage_rows_use_the_weapon_label_and_the_base_row():
    html = build.render_html()
    handler = html.split('on("clicked:roll_damages"')[1].split("\n});")[0]
    assert '{{Base=[[" + base + "]]}}' in handler
    assert '{{Total=[[" + total + "]]}}' in handler
    assert '(offensive ? " (Offensive)" : "")' in handler
    # the weapon row is keyed by the label, so a nameless item cannot appear
    assert "label: ITEMS[id].label" in handler


def test_ambidextrous_weapons_need_dexterity_for_the_off_hand():
    import re
    html = build.render_html()
    css = build.build_css("x")
    # the click is refused, and only for that one slot
    assert 'if (slot === "equip_off_hand" && offHandDenied(v, hand)) { return; }' in html
    assert 'item.cat === "ambidextrie"' in html
    assert 'hand_no_offhand: offHandDenied(v, item) ? "1" : ""' in html
    assert 'name="attr_hand_no_offhand"' in html
    # red on the off hand ONLY — the same sword must stay gold in the main hand
    red = ('.sheet-arx:has(input[name="attr_hand_no_offhand"][value="1"]) '
           'input[name="attr_hand_cat"][value="ambidextrie"] ~ .sheet-book '
           '.sheet-slot--equip_off_hand input[value=""] ~ button {')
    assert red in css
    # the rule is universal (every character, every ambidextrous weapon), so
    # it is deliberately absent from the tooltips — it would repeat on each
    assert "main gauche" not in html
    # exactly one selector keys off that flag, and it targets the off hand
    keyed = [l for l in css.splitlines()
             if "attr_hand_no_offhand" in l and l.startswith(".sheet-arx")]
    assert len(keyed) == 1, keyed
    assert ".sheet-slot--equip_off_hand" in keyed[0]
    assert ".sheet-slot--equip_main_hand" not in keyed[0]
    # both red states must look identical: same declarations, one source
    heavy = css.split('.sheet-arx:has(input[name="attr_hand_too_heavy"][value="1"])')[1].split("}")[0]
    assert heavy.split("{")[1].strip() == css.split(red)[1].split("}")[0].strip()
