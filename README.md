# ARX — Arx Fatalis Character Sheet for Roll20

Custom character sheet for the **Arx Fatalis** tabletop RPG, built as a "legacy" Roll20 HTML/CSS/sheet-worker sheet (no Beacon SDK — see [SPEC.md](SPEC.md) for why, and the roadmap).

Nothing is hand-written directly in the final HTML/CSS: everything starts in `src/`, assembled by `build.py`, and generated into `build/`.

<img width="900" height="576" alt="Capture d’écran 2026-07-30 à 23 00 52" src="https://github.com/user-attachments/assets/912cacf2-1d7e-4f84-a835-925b3a1081f5" />
## Features

- **Base page**: level, 4 attributes, 9 skills, Health/Mana gauges, damages, 3 resistances (armor class / magic resistance / poison resistance), postures (Defensive/Offensive/Focus/Guardian), character name synced with the Roll20 journal.
- **Calculations**: skills, armor class / magic resistance / poison resistance, damages and max gauges are all derived from attributes (official formulas, see [wiki.arx-libertatis.org/Stats](https://wiki.arx-libertatis.org/Stats)), with an equipment bonus that stacks on top without ever overwriting a manual edit.
- **Inventory**: 15×3 bag grid, up to 4 unlockable levels, multi-cell items, equipment (head/torso/belt/weapons/jewelry), purse (gold), trash, coin merging.
- **Magic**: grimoire (rune learning), spell crafting via rune combinations, memorized spells (presets), scroll reading.
- **Map**: 8 unlockable dungeon levels via consumable map cards, each with its own handwritten note.
- **Notes**: free-form notes page (multi-page, navigation currently frozen on page 1).

## Getting started

```bash
pip install -r requirements.txt

python3 build.py            # one-off build
python3 build.py --watch    # auto-rebuild on every change under src/
```

- `build/preview.html`: simulates Roll20's rendering locally (open directly in a browser), with a DEV toolbar (give an item, learn every rune, clear the inventory...) that only exists in this file — never shipped to Roll20.
- `build/sheet.html` + `build/sheet.css`: paste into Roll20 (Game Settings → Custom → HTML then CSS).
- `build/arx-mod.js`: paste into the game's API tab (Roll20 Pro account required) — see below.

## Project structure

```
build.py                  assembles everything below into build/
items.json                item catalog (weapons, armor, jewelry, runes, gold, map cards, scrolls...)
spells.json                spellbook spells (label, required runes, page, slot, icon)
presets.json                memorizable spells (self-contained, includes secret spells)
src/
  templates/
    sheet.html.j2          HTML root, includes the pages below
    partials/
      tabs.html.j2         page navigation
      inventory-slots.html.j2
      pages/
        base.html.j2       base page (stats, postures)
        magic.html.j2      grimoire, crafting, presets
        map.html.j2        map + per-level notes
        notes.html.j2      free-form notes page
    css/                    .css.j2 counterparts of the pages above, rendered via Jinja
    data/
      stats.j2             stat tooltip texts
  css/                      static CSS (no Jinja): base, tabs, inventory
  workers/
    inventory.js            THE sheet worker (all player-side logic)
  mod/
    arx-mod.js               Roll20 API script (GM commands)
tests/
  test_build.py             ~32 structural tests on the generated HTML/CSS (pytest)
assets/                      images (book/, ui/, items/, runes/), served from GitHub raw in production
```

## Data files (source of truth)

- **`items.json`** — each item: `label`, `icon`, `cat` (equipment category), `size` (bag footprint), and optionally `legendary`, `effect` (`rune`/`scroll`/`currency`/`map_card`/`extra_bag`), or any stat bonus (`strength`, `armor_class`, `mana_max`, etc.).
- **`spells.json`** — spellbook spells (label, required runes in order, page, slot).
- **`presets.json`** — memorizable spells, self-contained (label + runes + icon + `secret: true/false`).

## GM commands (`arx-mod.js`)

Select the character's token, then in the chat:

```
!arxhelp                    list every command in a GM whisper
!arxgive <item_id>          give an item (drops in the first free bag slot)
!arxlearnall                mark every rune known + fill the grimoire
!arxforgetrune <rune_id>    un-learn a single rune (e.g. rune-aam)
!arxforgetallrunes          un-learn every rune
!arxlockmap <1-8>           re-lock a single map level (level 1 can't be locked)
!arxlockallmaps             re-lock every map level except level 1
!arxunlockguardian          unlock the Guardian posture
!arxlockguardian            re-lock the Guardian posture
!arxresetinventory          empty every bag slot + clear the hand
!arxresetall                factory-reset the whole character (stats, inventory, magic, map, postures, gold)
!arxpreset <1-3> <spell_id> set a memorized-spell slot
!arxpage <1-10>              switch the displayed spell page
!arxtab base|magic           switch the active sheet page
```

## Tests

```bash
python3 -m pytest tests/test_build.py -q
```

Structural tests: presence of the right attributes/buttons in the generated HTML, expected CSS rules, JSON catalog consistency. No visual tests — after a change, also check `build/preview.html`.
