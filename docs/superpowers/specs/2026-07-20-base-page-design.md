# ARX Roll20 Sheet — Step 1: Base Page (Level, Stats, Vitals)

**Date:** 2026-07-20
**Status:** Approved by Chafik

## Context

Custom Roll20 character sheet for the ARX JDR, built with the **legacy method** (HTML + CSS, no Beacon SDK). The whole sheet design rests on hand-made composed images; step 1 covers the base double-page spread (`assets/ARX-BASE.png`): a medieval grimoire showing level, attributes, skills, vitals and resistances.

Roll20 constraints that shape this design:

- Final deliverable is a single `sheet.html` fragment (no `<html>/<head>/<body>`) + a single `sheet.css`.
- Data fields are `attr_*`-named inputs, saved automatically by Roll20.
- Images must be served over HTTPS (no upload into the sheet).
- Google Fonts allowed via CSS `@import`.

## Scope of step 1

The full ARX-BASE double page, **except** the two ring (jewelry) slots at the bottom of the left page (deferred).

- **No dice rolls** — icons are not clickable for now.
- **No auto-calculations** — every field is manually entered. No sheet workers in step 1.
- **No identity fields** (name/race/class) — the Roll20 journal handles the character name.
- **No XP field** — the "Xp" label is being removed from the image; only Level remains.

## Approach (decided)

**Approach A — full composed image as background + absolutely positioned inputs.**

`ARX-BASE.png` is used as-is as the `background-image` of a fixed-size container; each numeric input is absolutely positioned (in % of the container) centered **below** its engraved icon, on the free parchment space. Icons, frames and engraved labels stay baked into the image.

Rejected alternative (B): cutting the book background and every icon into separate assets and rebuilding the layout in CSS grid. More flexible (hover states, reordering) but far more work, and brings nothing while icons are not interactive. If icons later become roll buttons, invisible clickable zones will be layered on top of the image — no approach change needed.

## Source structure and build

```
src/
  templates/
    sheet.html.j2          # root template
    partials/
      base-page.html.j2    # the ARX-BASE double page (step 1)
  css/
    base.css               # input reset + container
    base-page.css          # field positioning over the image
build.py                   # Jinja2 render → build/sheet.html, CSS concat → build/sheet.css
build/
  sheet.html
  sheet.css
```

- `build.py`: renders the Jinja2 template, concatenates CSS files in a defined order, and reserves an injection point for future `<script type="text/worker">` content (unused in step 1). `--watch` flag via mtime polling. Only dependency: `jinja2`.
- Attributes and skills are emitted by a Jinja loop over a `(attr_name, position)` list — one HTML structure to maintain.
- The Roll20 Custom Sheet Sandbox points to `build/sheet.html` + `build/sheet.css`.

## Fields (Roll20 attributes)

All plain `<input type="number">`, free entry:

| Zone | Attributes |
|---|---|
| Right page header | `attr_level` (engraved label on the image stays "Niveau") |
| Attributes row (4) | `attr_strength`, `attr_mental`, `attr_dexterity`, `attr_constitution` |
| Skills grid (3×3) | `attr_stealth`, `attr_technical`, `attr_intuition`, `attr_ethereal_link`, `attr_object_knowledge`, `attr_casting`, `attr_close_combat`, `attr_projectile`, `attr_defense` |
| Left page | `attr_health` + `attr_health_max`, `attr_mana` + `attr_mana_max`, `attr_damages`, `attr_armor_class`, `attr_magic_resistance`, `attr_poison_resistance` |

Icon → field mapping (right page): muscular arm = Strength, head = Mental, target = Dexterity, torso = Constitution; runner = Stealth, gear = Technical, eye = Intuition, thinking head = Ethereal link, dagger = Object knowledge, open hand = Casting, crossed axe/sword = Close combat, bow = Projectile, shield = Defense.

Left page: sword shield = Armor Class, pentacle shield = Magic Resistance, serpent "S" shield = Poison Resistance, heart = Health, round pentacle = Mana, lone sword = Damages.

`attr_health` / `attr_health_max` (and same for mana) use Roll20's `_max` convention, so token bars can be linked to these attributes directly.

## Visual rendering

- Fixed-size container (~1100 px wide, height from the image aspect ratio), `position: relative`, `ARX-BASE.png` as HTTPS `background-image`.
- Inputs absolutely positioned in **% of the container**, centered below their icon.
- Input styling: transparent background, no border (subtle underline/halo on `:focus`), ink/sepia text color, medieval Google Font (2-3 candidates to be proposed during implementation). Number spinners hidden.
- Health and Mana: two small side-by-side fields separated by a styled `/`, below the heart and the pentacle.
- CSS must account for Roll20's `.sheet-` class prefixing (target both forms where needed).

## Positioning workflow

Field coordinates are **measured from the PNG** (center of each engraved frame, in pixels, converted to %) — not eyeballed. Measurements are taken on the **final re-exported image** (after the "Xp" label removal); implementation waits for that file. Final adjustment happens in the Custom Sheet Sandbox.

## Hosting and deployment

- Repo pushed to GitHub; images referenced via `raw.githubusercontent.com` URLs (required even for the sandbox — Roll20 only loads HTTPS).
- `ARX-BASE.png` compressed before push (target < 800 KB, via Squoosh/OxiPNG), no visible loss.
- Final deployment: paste `build/sheet.html` + `build/sheet.css` into the game's Custom Sheet settings (requires Roll20 Pro).

## Verification

- `build.py` runs and produces `build/sheet.html` + `build/sheet.css` with no Jinja errors.
- Sheet loads in the Custom Sheet Sandbox: image displays, every field sits under its icon, values persist after reload (Roll20 attribute save).
- Token bar can be linked to `health` (value + max).

## Later steps (out of scope)

Ring slots, armor, weapons, inventory (see `assets/inventaire side.png`, `HP.png`, `Mana.png`, food/torch icons), dice roll buttons, roll templates, auto-calculations via sheet workers.
