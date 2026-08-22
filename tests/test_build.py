import re
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
        if name in NO_ROLL or name == "damages":
            # damages is inert too: the attack roll lives on the two per-hand
            # buttons instead (see test_attack_buttons_are_one_per_hand).
            assert f'name="roll_{name}"' not in html, name
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


# items.json is ordered, not chronological: one contiguous run per group, in
# this order. It is the GM catalog's own layout (gm-panel.html.j2 derives page
# and cell from an item's index), so a new item belongs with its kind, never
# appended at the end. Weapons lead because that is what the batches grow.
ITEM_GROUP_ORDER = [
    ("main_principale", {"cat": "main_principale"}),
    ("ambidextrie", {"cat": "ambidextrie"}),
    ("deux_mains", {"cat": "deux_mains"}),
    ("main_secondaire", {"cat": "main_secondaire"}),
    ("casque", {"cat": "casque"}),
    ("armure_haute", {"cat": "armure_haute"}),
    ("armure_basse", {"cat": "armure_basse"}),
    ("bijoux", {"cat": "bijoux"}),
    ("rune", {"effect": "rune"}),
    ("scroll", {"effect": "scroll"}),
    ("potions", {"effect": "potions"}),
    ("food", {"effect": "food"}),
    ("drinks", {"effect": "drinks"}),
    ("currency", {"effect": "currency"}),
    ("map_card", {"effect": "map_card"}),
    ("extra_bag", {"effect": "extra_bag"}),
    ("objet", {}),  # catch-all, necessarily last
]


def _group_of(item):
    for name, spec in ITEM_GROUP_ORDER:
        if all(item.get(k) == v for k, v in spec.items()):
            return name
    raise AssertionError(item)


def test_items_are_grouped_by_category_in_file_order():
    groups = [_group_of(i) for i in build.load_items().values()]
    runs = [g for n, g in enumerate(groups) if n == 0 or g != groups[n - 1]]
    # every group appears exactly once: a second run means an item was dropped
    # in the wrong place, and the GM catalog page it lands on is not its kind's
    assert len(runs) == len(set(runs)), \
        f"groupe scindé : {[g for g in runs if runs.count(g) > 1]}"
    expected = [name for name, _ in ITEM_GROUP_ORDER if name in set(runs)]
    assert runs == expected, f"ordre des groupes : {runs}"


def test_rune_order_is_the_spellbook_slot_order():
    """RUNE_ORDER (inventory.js, arx-mod.js) maps each rune to a FIXED
    spellbook_<n> by its rank among the runes of items.json. Reordering the
    runes silently reshuffles every existing character's grimoire, so the
    sequence is pinned here rather than left to whoever edits the file."""
    runes = [k for k, v in build.load_items().items() if v.get("effect") == "rune"]
    assert runes == [
        "rune-aam", "rune-nhi", "rune-mega", "rune-yok", "rune-taar",
        "rune-kaom", "rune-vitae", "rune-vista", "rune-stregum", "rune-morte",
        "rune-cosum", "rune-comunicatum", "rune-movis", "rune-tempus",
        "rune-folgora", "rune-spacium", "rune-tera", "rune-cetrius",
        "rune-rhaa", "rune-fridd",
    ], runes
    # the two copies of the order must agree, or the API hands out slots the
    # sheet does not read back
    html = build.render_html()
    assert 'const RUNE_ORDER = Object.keys(ITEMS).filter' in html
    mod = build.render_mod()
    assert "const ARX_RUNE_ORDER = Object.keys(ARX_ITEMS).filter" in mod


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
        "spiked-shield": {"label": "Rondache à pointes", "icon": "i.png",
                          "cat": "main_secondaire", "size": "2x2",
                          "weap_dmg": "1d4", "armor_class": 3, "magic_resistance": 1},
        "torch": {"label": "Torche", "icon": "i.png", "cat": "ambidextrie",
                  "size": "1x2", "weap_dmg": "1d2"},
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
    # ...and one that also hits stacks its dice IN FRONT of that block rather
    # than replacing it — the dice really are rolled, so they must be readable
    assert spec("Rondache à pointes") == " - [1d4 | 3 CA - 1 CAM | ADD]"
    # dice on a non-weapon category are printed all the same: weap_dmg alone
    # decides, exactly as rollHandDamage does
    assert spec("Torche") == " - [1d2 | AMB]"
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
    assert "SKILL_CAP" in skill_cap
    assert "const SKILL_CAP = 125;" in html


def _cap_write_off(base, gear_steps, cap=24):
    """Replay the attribute cap against recomputeModifiers, the way the sheet
    runs them: gear change first, clamp second. Mirrors inventory.js — if that
    logic moves, this drifts and the assertions below stop meaning anything,
    which is why test_attribute_cap_writes_off_what_it_refuses also pins the
    source lines it is modelled on."""
    value, applied = base, 0
    for gear in gear_steps:
        value += gear - applied            # recomputeModifiers: delta only
        applied = gear
        if value > cap:                    # the cap, writing off what it refused
            applied = max(0, applied - (value - cap))
            value = cap
    value += 0 - applied                   # everything unequipped
    return value


def test_attribute_cap_writes_off_what_it_refuses():
    """A capped bonus must not be handed back at unequip.

    22 Force + a 5 Force weapon used to clamp to 24 and drop to 19 once the
    weapon came off, because attr_<name>_applied_mod still claimed the whole
    +5. The clamp now writes off the refused points."""
    assert _cap_write_off(22, [5]) == 22
    assert _cap_write_off(22, [10]) == 22
    assert _cap_write_off(20, [5, 8]) == 20          # swapping items
    assert _cap_write_off(24, [6]) == 24             # already at the ceiling
    assert _cap_write_off(6, [5]) == 6               # never reaches the cap
    # a malus eats into the refused overflow instead of biting the character:
    # 23 + 5 sits at 24 with 4 written off, so a -2 leaves the total untouched
    assert _cap_write_off(23, [5, 3]) == 23
    assert _cap_write_off(23, [5, -3]) == 23         # malus beyond the overflow
    assert _cap_write_off(23, [-2, 3]) == 23         # malus equipped first

    html = build.render_html()
    body = html.split('on("change:" + attr, function () {')[1].split("\n  });")[0]
    assert 'getAttrs([attr, attr + "_applied_mod"]' in body
    assert 'update[attr + "_applied_mod"] = Math.max(0, applied - (total - ATTR_CAP));' in body
    assert "const ATTR_CAP = 24;" in html
    # the skill cap does the same across its two trackers, gear first
    skill = html.split('on("change:" + skill, function () {')[1].split("\n  });")[0]
    assert "const offGear = Math.min(gear, refused);" in skill
    assert 'update[skill + "_applied_mod"] = gear - offGear;' in skill
    assert 'update[skill + "_applied_stat_mod"] = Math.max(0, derived - (refused - offGear));' in skill


BREAKDOWN_STATS = (["strength", "mental", "dexterity", "constitution"]
                   + ["stealth", "technical", "intuition", "ethereal_link",
                      "object_knowledge", "casting", "close_combat", "projectile", "defense"]
                   + ["damages", "armor_class", "magic_resistance", "poison_resistance"])


def test_stat_billboards_show_where_the_number_comes_from():
    """Each stat's hover billboard carries the same spec line an item does.

    The field shows only the sum; the share assigned by hand is invisible,
    which is what makes a level-up at the cap look like it did nothing."""
    html = build.render_html()
    css = build.build_css("x")
    # identical treatment to an item's spec line, one rule for both
    assert ".sheet-item-specs,\n.sheet-stat-breakdown {" in css
    for name in BREAKDOWN_STATS:
        bar = html.split(f'sheet-statbar--{name}">')[1].split("</div>")[0]
        assert 'class="sheet-stat-breakdown"' in bar, name
        # live values, not build-time constants
        assert f'<span name="attr_{name}_own">' in bar, name
        assert f'<span name="attr_{name}_applied_mod">' in bar, name
        # attributes have no attribute-derived share; everything else does
        derived = f'<span name="attr_{name}_applied_stat_mod">' in bar
        assert derived is (name not in ("strength", "mental", "dexterity", "constitution")), name
    # the hand-assigned share is derived from the two trackers, never stored twice
    assert 'update[name + "_own"] = total - gear - derived;' in html
    # ...and recomputed when a TRACKER moves, not just the stat: the cap
    # rewrites a tracker while leaving the total alone. The event string is
    # built from BREAKDOWN_GETATTRS, which is the stats plus both trackers.
    assert ('on(BREAKDOWN_GETATTRS.map(function (a) { return "change:" + a; }).join(" "),'
            in html)
    getattrs = html.split("const BREAKDOWN_GETATTRS =")[1].split("\n\n")[0]
    assert '"_applied_mod"' in getattrs and '"_applied_stat_mod"' in getattrs


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
    # player-fired: documented in the file header, deliberately NOT in the
    # in-game !arxhelp whisper (filtered to GM-useful commands on request)
    assert "!arxconsume                 (not for GM use" in mod
    help_block = (mod.split('indexOf("!arxhelp")')[1]
                     .split('sendChat("ARX", "/w gm " + [')[1].split('].join')[0])
    assert "!arxconsume" not in help_block
    css = build.build_css("x")
    in_css = sorted(set(re.findall(r'attr_hand_effect"\]\[value="(\w+)"\] ~ '
                                   r'.sheet-inventory .sheet-consume', css)))
    assert in_css == sorted(CONSUMABLE_EFFECTS), in_css
    # an item is a scroll OR food, never both: that is what lets the two
    # buttons share one spot in the band
    in_items = {i["effect"] for i in build.load_items().values() if "effect" in i}
    assert in_items.issuperset(CONSUMABLE_EFFECTS)
    assert "scroll" in in_items


WEAPON_DICE = {"dagger": "2d4", "club": "1d8", "long-sword": "2d16",
               "bow": "1d20", "sword-mx": "2d80",
               # a shield's dice are rolled like any other hand's (see
               # rollHandDamage), which is why they may carry weap_dmg at all
               "shield": "1d8", "shield-elder": "1d19"}


def test_weapon_dice_are_well_formed_and_reachable():
    import re
    items = build.load_items()
    for item_id, item in items.items():
        if "weap_dmg" not in item:
            continue
        assert re.fullmatch(r"[1-9]\d*d[1-9]\d*", item["weap_dmg"]), item_id
        # a hand category is all it takes now — a shield's dice DO get rolled
        # (see rollHandDamage) — but dice on a helmet or a loaf of bread still
        # could never reach a hand slot, so they would be silently dead
        assert item["cat"] in ("main_principale", "main_secondaire",
                               "ambidextrie", "deux_mains"), \
            f"{item_id}: {item['cat']} never reaches a hand slot"
    for item_id, dice in WEAPON_DICE.items():
        assert items[item_id]["weap_dmg"] == dice, item_id


def _damage_handler(html):
    return html.split("function rollHandDamage(slot) {")[1].split("\n}")[0]


def test_attack_buttons_are_one_per_hand():
    html = build.render_html()
    css = build.build_css("x")
    # the sword's own button is gone: the damages stat is a hover zone now
    assert "act_roll_damages" not in html
    assert "roll_damages" not in html
    for slot, asset in (("equip_main_hand", "attack_left"),
                        ("equip_off_hand", "attack_right")):
        assert f'name="act_attack_{slot}"' in html, slot
        assert f'on("clicked:attack_" + slot' in html
        assert f".sheet-attack-btn--{slot} {{" in css, slot
        assert f"ui/{asset}.png" in css, slot
        # each button gets its own hover billboard
        assert f'class="sheet-statbar sheet-statbar--attack-{slot}"' in html, slot
        assert f".sheet-attack-btn--{slot}:hover) .sheet-statbar--attack-{slot}" in css, slot
    # the hand a click reads is the button's own slot and nothing else
    handler = _damage_handler(html)
    assert "getAttrs([slot, \"posture\", \"damages\", \"damages_gm_mod\"]" in handler
    assert "const itemId = v[slot];" in handler
    # ...so no de-duplication of a mirrored two-handed weapon survives
    for gone in ("mirroredTwoHanded", "mainItem", "equip_off_hand", "equip_main_hand"):
        assert gone not in handler, gone


def test_damage_roll_is_computed_in_the_worker():
    html = build.render_html()
    handler = _damage_handler(html)
    # RNG is the eleven-step ladder 0, 0.1 … 1.0, not a continuous draw
    assert "Math.floor(Math.random() * 11) / 10" in handler
    assert "const base = offensive ? damages : Math.round(damages * (0.8 + 0.2 * rng));" in handler
    # Offensive takes each die at its maximum instead of rolling it
    assert "values.push(offensive ? dice.faces : rollDie(dice.faces));" in handler
    # the total is accumulated here, never rebuilt by finishRoll
    assert "values.forEach(function (value) { total += value; });" in handler
    assert "finishRoll(results.rollId, {})" in handler
    # nothing left of the version whose Total displayed 0
    for gone in ("Hasard", "{{Stat=", "{{Arme=", "[[1d100]]", "{{Total=[[0]]}}", "diceMax"):
        assert gone not in handler, gone


def test_damage_rows_use_the_weapon_label_and_the_base_row():
    html = build.render_html()
    handler = _damage_handler(html)
    assert '{{Base=[[" + base + "]]}}' in handler
    assert '{{Total=[[" + total + "]]}}' in handler
    assert '(offensive ? " (Offensive)" : "")' in handler
    # the chat window names the hand, so two rolls never look alike
    assert '{{name=Dégâts — " + HAND_LABELS[slot]' in handler
    # the single row is keyed by the item's label, so a nameless one can't show
    assert 'rows = " {{" + ITEMS[itemId].label + "=" + values.join(" + ") + "}}"' in handler
    # ...and there is no row at all without dice: bare fists roll the base alone
    assert "if (dice) {" in handler


def test_the_off_hand_dexterity_rule_is_gone():
    """Removed on request: an ambidextrous weapon goes in either hand freely."""
    html = build.render_html()
    css = build.build_css("x")
    for gone in ("OFFHAND_MIN_DEXTERITY", "offHandDenied", "hand_no_offhand"):
        assert gone not in html, gone
        assert gone not in css, gone
    # min_strength is a different rule and must survive untouched
    assert "function tooHeavy(v, itemId)" in html
    assert 'if (tooHeavy(v, hand)) { return; }' in html
    assert 'input[name="attr_hand_too_heavy"][value="1"]' in css


def test_fate_status_is_displayed_and_gm_only():
    """Faveur du Noden / Coups du sort: a GM-set status (attr_fate), shown as
    an icon on the posture row — the player can see it but never change it."""
    html = build.render_html()
    css = build.build_css("x")
    # One hidden attribute, no player-facing control writes to it
    assert 'name="attr_fate"' in html
    assert 'name="act_fate' not in html
    # Two icons (plain divs, not buttons), one per status
    assert 'class="sheet-fate-icon sheet-fate-icon--favor"' in html
    assert 'class="sheet-fate-icon sheet-fate-icon--twist"' in html
    # Hover labels: rainbow spans for the favor, plain red text for the twist
    assert 'sheet-statbar--fate-favor' in html
    assert 'sheet-statbar--fate-twist' in html
    assert '<span class="sheet-rainbow-0">F</span>' in html
    # Only the active status shows
    assert '.sheet-fate-icon {\n  display: none;' in css
    assert '.sheet-arx:has(input[name="attr_fate"][value="favor"]) .sheet-fate-icon--favor' in css
    assert '.sheet-arx:has(input[name="attr_fate"][value="twist"]) .sheet-fate-icon--twist' in css
    assert "ui/noden-favor.png" in css
    assert "ui/twist-of-fate.png" in css
    assert '.sheet-arx:has(.sheet-fate-icon--favor:hover) .sheet-statbar--fate-favor' in css
    assert '.sheet-arx:has(.sheet-fate-icon--twist:hover) .sheet-statbar--fate-twist' in css
    assert '.sheet-statbar--fate-twist { color: #ff2b2b; }' in css


def test_fate_gm_buttons_and_mod_commands():
    """The GM sets/clears the status via !arxfavor/!arxtwist/!arxfateclear —
    selected token, same flow as the loot commands — with shortcut buttons on
    the GM utility sheet, shown only while the GM panel is open."""
    build.build()
    html = build.render_html()
    css = build.build_css("x")
    mod = (build.BUILD / "arx-mod.js").read_text(encoding="utf-8")
    for name, command in (("favor", "!arxfavor"), ("twist", "!arxtwist"),
                          ("clear", "!arxfateclear")):
        assert f'name="act_gm_fate_{name}" value="{command}"' in html, name
        assert command in mod, command
        assert f".sheet-gm-fate-btn--{name}" in css, name
    assert '.sheet-arx:has(input[name="attr_gm_panel_open"][value="1"]) .sheet-gm-cmd-btn' in css
    # The full character reset clears the status too
    assert 'arxSetAttr(charId, "fate", "");' in mod


MOD_BADGE_FIELDS = [
    "strength", "mental", "dexterity", "constitution",
    "stealth", "technical", "intuition",
    "ethereal_link", "object_knowledge", "casting",
    "close_combat", "projectile", "defense",
    "armor_class", "magic_resistance", "poison_resistance", "damages",
]


def test_every_stat_has_its_own_mod_badge():
    """GM item bonus/malus badges: one standalone absolute element per stat,
    NEVER nested inside the stat's own .sheet-field (the base number must
    never move because of it)."""
    html = build.render_html()
    css = build.build_css("x")
    for name in MOD_BADGE_FIELDS:
        assert f'class="sheet-mod-badge sheet-mod-badge--{name}"' in html, name
        assert f".sheet-mod-badge--{name}" in css, name
        # Standalone: the badge is not inside the field's div (one line each)
        assert f'sheet-field--{name}"><span class="sheet-mod-badge' not in html, name
    assert "pointer-events: none;" in css.split(".sheet-mod-badge {")[1].split("}")[0]


def test_gm_mod_values_are_dynamic_and_gm_only():
    """!arxmod/!arxclearmods (multi-token, GM only) write attr_<stat>_gm_mod;
    the badge shows it blue when positive, red when negative, nothing at 0.
    The sheet itself never writes these attributes."""
    build.build()
    html = build.render_html()
    css = build.build_css("x")
    mod = (build.BUILD / "arx-mod.js").read_text(encoding="utf-8")
    for name in MOD_BADGE_FIELDS:
        assert f'name="attr_{name}_gm_mod"' in html, name
        assert (f'.sheet-arx:has(input[name="attr_{name}_gm_mod"]'
                f':not([value=""]):not([value="0"]):not([value^="-"])) '
                f'.sheet-mod-badge--{name}') in css, name
        assert (f'.sheet-arx:has(input[name="attr_{name}_gm_mod"][value^="-"]) '
                f'.sheet-mod-badge--{name}') in css, name
    assert 'name="act_gm_mod' not in html.replace('name="act_gm_mod"', "")  # only the GM button
    assert "!arxmod" in mod and "!arxclearmods" in mod
    # The GM button pops the native stat/value query, French labels included
    assert 'name="act_gm_mod" value="!arxmod ?{Stat' in html
    assert ",strength|" in html and ",damages}" in html
    # The mod's whitelist is the exact badge list — kept honest like the loot skins
    import re
    js_list = re.search(r"const ARX_GM_MOD_STATS = \[(.*?)\];", mod, re.S).group(1)
    assert re.findall(r'"([^"]+)"', js_list) == MOD_BADGE_FIELDS
    # !arxclearmods and !arxresetall both wipe every mod
    assert mod.count('ARX_GM_MOD_STATS.forEach(function (stat) { arxSetAttr(charId, stat + "_gm_mod", "0"); });') == 2


def test_gm_mods_count_in_every_roll_target():
    """Each GM mod feeds its own stat's roll target and nothing else — no
    derived-stat cascade (a strength mod never recomputes close_combat: the
    GM mods close_combat directly instead)."""
    html = build.render_html()
    # Skill rolls, plain and Focus (skill mod + governing attribute's own mod)
    assert '{{Valeur=[[@{stealth}+@{stealth_gm_mod}]]}}' in html
    # Focus's displayed equation must keep adding up under a skill mod: the
    # lead term is the same [[skill+mod]] as the total's first two terms
    assert ('{{Valeur=[[@{stealth}+@{stealth_gm_mod}]] + Dextérité (Focus) = '
            '[[@{stealth}+@{stealth_gm_mod}+@{dexterity}+@{dexterity_gm_mod}]]}}') in html
    # Spellcasting (crafted + memorized — the caster_level row tells them
    # apart from the Magie skill button's own roll), but NOT scrolls: a
    # scroll rolls its own fixed spell_casting, never the caster's live stat
    assert html.count('{{Valeur=[[@{casting}+@{casting_gm_mod}]]}} {{Niveau Magique=@{caster_level}}}') == 2
    assert '{{Valeur=" + item.spell_casting + "}}' in html
    # Damages: the mod joins the stat before the 0.8-1.0 scaling
    handler = _damage_handler(html)
    assert '(parseInt(v.damages, 10) || 0) + (parseInt(v.damages_gm_mod, 10) || 0)' in handler
    # No cascade: the recompute machinery never reads a _gm_mod
    assert "_gm_mod_applied" not in html


def _object_literal(source, marker):
    return source.split(marker)[1].split("\n};")[0]


def test_randstats_formulas_match_the_worker_and_button_is_wired():
    """!arxrandstats writes a full coherent stat block: since API writes never
    run the sheet workers, the mod carries byte-for-byte copies of the
    worker's Arx formulas — this is the test the copies point at."""
    build.build()
    html = build.render_html()
    css = build.build_css("x")
    mod = (build.BUILD / "arx-mod.js").read_text(encoding="utf-8")
    for worker_marker, mod_marker in (
        ("const SKILL_FORMULAS = {", "const ARX_SKILL_FORMULAS = {"),
        ("const SINGLE_STAT_FORMULAS = {", "const ARX_SINGLE_STAT_FORMULAS = {"),
        ("const GAUGE_MAX_FORMULAS = {", "const ARX_GAUGE_MAX_FORMULAS = {"),
    ):
        assert _object_literal(html, worker_marker) == \
            _object_literal(mod, mod_marker), worker_marker
    # GM button: level + archetype popup, same principle as Bonus/Malus. The
    # trailing @{character_id} pins the command to the button's own sheet —
    # a stray selected token can never get its stats regenerated.
    assert ('name="act_gm_rand" value="!arxrandstats ?{Niveau (0-10)|3} '
            '?{Archétype|Guerrier,guerrier|Mage,mage|Voleur,voleur|Équilibré,equilibre} '
            '@{character_id}"') in html
    assert 'if (!getObj("character", parts[3]))' in mod  # explicit-id branch
    assert ".sheet-gm-rand-btn" in css
    assert '.sheet-arx:has(input[name="attr_gm_panel_open"][value="1"]) .sheet-gm-cmd-btn' in css
    # the wiki's budget ON TOP of the base values: attributes start at 6 each
    # (4×6), then 16 + 1/level points; skills get 18 + 15/level raw points
    # (their base is already the formulas at 6/6/6/6)
    assert "arxDistribute(4 * 6 + 16 + level, spec.attrs, 6)" in mod
    assert "arxDistribute(18 + 15 * level, spec.skills, 0)" in mod
    # a guerrier never puts a point in Magie (weight 0 = never drawn)
    assert "casting: 0, close_combat: 3" in mod
    # a rerun overwrites the WHOLE character: the shared factory reset runs
    # before the draw (called by both !arxresetall and arxApplyRandomStats)
    assert mod.count("arxResetCharacter(charId);") == 2
    # bookkeeping mirrors !arxresetall: derived shares tracked, gear mods zeroed
    assert "!arxrandstats" in mod
    assert 'arxSetAttr(charId, skill + "_applied_stat_mod", String(derived));' in mod
    assert 'arxSetAttr(charId, name + "_max_applied_stat_mod", String(max));' in mod
    assert "!arxrandstats <niveau 0-10>" in mod  # listed in !arxhelp


def test_sheet_zoom_toggle_cycles_and_scales():
    """Per-character sheet zoom: a toggle cycles 100→90→80→70, `zoom` on
    .sheet-arx shrinks rendering AND layout (no ghost scroll area). 100 is
    the default and gets no rule: the sheet renders exactly as before."""
    html = build.render_html()
    css = build.build_css("x")
    assert '<input type="hidden" class="sheet-hand-mirror" name="attr_sheet_zoom" value="100" />' in html
    assert 'name="act_sheet_zoom"' in html
    assert '"100": "90", "90": "80", "80": "70", "70": "100"' in html
    for value, factor in (("90", "0.9"), ("80", "0.8"), ("70", "0.7")):
        assert (f'.sheet-arx:has(input[name="attr_sheet_zoom"][value="{value}"]) '
                f'{{ zoom: {factor}; }}') in css, value
    assert 'value="100"]) { zoom' not in css
    assert "ui/zoom-button.png" in css
    # hover label, same statbar mechanism as everything else
    assert 'class="sheet-statbar sheet-statbar--zoom"' in html
    assert '.sheet-arx:has(.sheet-zoom-toggle:hover) .sheet-statbar--zoom { display: block; }' in css
    # stacked like the other toggles — .sheet-book (z-index:1, later sibling)
    # paints over any unstacked element declared before it
    zoom_block = css.split(".sheet-zoom-toggle {")[1].split("}")[0]
    assert "z-index: 10;" in zoom_block


def test_dark_surround_covers_the_sheet_window():
    """The white Roll20 window around the sheet is painted warm black two
    ways: a 100vmax box-shadow on .sheet-arx (layout-neutral, survives any
    CSS sanitization mode) and a .charsheet background (modern mode only)."""
    css = build.build_css("x")
    assert "box-shadow: 0 0 0 100vmax #14100c;" in css
    assert ".charsheet {\n  background-color: #14100c;\n}" in css


REGEN_PAIRS = [("heal_pct_min", "heal_pct_max"), ("mana_pct_min", "mana_pct_max")]


def test_regen_items_declare_a_complete_percentage_range():
    """Consuming restores a pool as soon as the item carries the values, with
    no "effect" gate — that is what lets the wine heal while staying "drinks"
    and keeping its "boit" verb. The flip side is that a half-declared range
    is silent: arxRegenReport skips the pool and the potion just does nothing,
    so both ends are pinned here."""
    for item_id, item in build.load_items().items():
        for lo_key, hi_key in REGEN_PAIRS:
            assert (lo_key in item) == (hi_key in item), f"{item_id}: {lo_key}/{hi_key} half-declared"
            if lo_key in item:
                lo, hi = item[lo_key], item[hi_key]
                assert isinstance(lo, int) and isinstance(hi, int), f"{item_id}: {lo_key}/{hi_key}"
                assert 1 <= lo <= hi <= 100, f"{item_id}: {lo}%-{hi}% is not a usable range"


def test_regen_is_wired_to_the_expected_items():
    items = build.load_items()
    healers = {k for k, v in items.items() if "heal_pct_min" in v}
    manaers = {k for k, v in items.items() if "mana_pct_min" in v}
    assert healers == {"health-potion", "bottle-wine"}, healers
    assert manaers == {"potion-mana"}, manaers


def test_consume_regen_is_wired_in_the_mod():
    """The whole thing has to live in !arxconsume: a worker cannot emit a /me
    and Roll20 never fires clicked: for a type="roll" button, so the mod is the
    only place that knows an item was just consumed."""
    mod = build.render_mod()
    # the reader half of the reserved "_max" suffix — a plain arxGetAttr on
    # "health_max" would read a bogus standalone attribute, not the real max
    assert "function arxGetAttrMax(" in mod
    assert 'attr.get("max")' in mod
    # both pools, driven by the values rather than by the item's type
    assert '{ pool: "health", min: "heal_pct_min", max: "heal_pct_max", unit: "PV" }' in mod
    assert '{ pool: "mana",   min: "mana_pct_min", max: "mana_pct_max", unit: "PM" }' in mod
    # rounded to the nearest point, floored at 1, overheal clamped to the max
    assert "Math.max(1, Math.round(poolMax * pct / 100))" in mod
    assert "Math.min(poolMax, before + gain)" in mod
    # and it runs from the consume handler, after the emote
    assert "arxRegenReport(charId, item).forEach(" in mod


def test_regen_keys_never_collide_with_a_real_stat():
    """"mana_max" is the max-mana BONUS: the tooltip's abbr table prints it and
    the worker's MOD_STATS sums it at equip time. Naming a regen bound after it
    made the mana potion read "- [+35 PM]" on hover. The "_pct" suffix is what
    keeps the two apart, so the separation is pinned rather than remembered."""
    # abbr is a Jinja-time table: it shapes the output but never appears in it
    template = (Path(build.SRC) / "templates" / "sheet.html.j2").read_text(encoding="utf-8")
    abbr = set(re.findall(r'"(\w+)": "[A-Z]{2,3}"', template.split("{% set abbr = {")[1].split("} %}")[0]))
    mod_stats = set(re.findall(r'"(\w+)"', build.render_html().split("const MOD_STATS = [")[1].split("]")[0]))
    assert {"mana_max", "health_max", "armor_class"} <= abbr & mod_stats, (abbr, mod_stats)
    for lo_key, hi_key in REGEN_PAIRS:
        for key in (lo_key, hi_key):
            assert key not in abbr, f"{key} would print as an equipment bonus on hover"
            assert key not in mod_stats, f"{key} would be granted for real at equip time"


def test_regen_range_is_spelled_out_in_special():
    """The numbers live twice — as values for the mod, as prose for the hover —
    because nothing renders raw regen keys. Drift between the two would show
    players a range the mod does not roll."""
    for item_id, item in build.load_items().items():
        for lo_key, hi_key in REGEN_PAIRS:
            if lo_key in item:
                prose = item.get("special", "")
                assert f"{item[lo_key]}%" in prose, f"{item_id}: {item[lo_key]}% missing from special"
                assert f"{item[hi_key]}%" in prose, f"{item_id}: {item[hi_key]}% missing from special"
