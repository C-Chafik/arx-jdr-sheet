#!/usr/bin/env python3
"""Assemble the Roll20 sheet: render Jinja2 templates, concatenate CSS."""
import argparse
import json
import re
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
SRC = ROOT / "src"
BUILD = ROOT / "build"

# Concatenation order matters: later files override earlier ones.
# Entries ending in .j2 are rendered via Jinja (from src/templates/css/).
CSS_FILES = ["base.css", "tabs.css", "inventory.css",
             "pages/base.css.j2", "pages/base-hover.css", "pages/notes.css.j2",
             "pages/map.css.j2",
             "inventory-slots.css.j2", "magic-slots.css.j2", "gm-panel.css.j2",
             "loot-panel.css.j2"]

WORKER_FILES = ["inventory.js"]

# Roll20 only loads HTTPS assets; preview uses the local files instead.
ASSET_BASE = "https://raw.githubusercontent.com/C-Chafik/arx-jdr-sheet/main/assets"
PREVIEW_ASSET_BASE = "../assets"

# ? Increase this value everytime you need to clear the cache of github assets
ASSET_VERSION = "10"

ITEMS_FILE = ROOT / "items.json"
SPELLS_FILE = ROOT / "spells.json"
PRESETS_FILE = ROOT / "presets.json"

# Bag grid dimensions — single source of truth, injected into templates,
# the sheet worker, the mod script and the dev shim.
# (Column 16 on Inventory.png is the pouch: not a storage cell.)
GRID_COLS = 15
GRID_ROWS = 3
# Bag levels ("étages"): 1 by default, unlocked up to this max by consuming
# an "effect": "extra_bag" item into the pouch. All levels are pre-wired.
GRID_BAGS = 4


PRIVATE_KEYS = ("desc", "note")


def strip_private(catalog: dict) -> dict:
    """Champs RP prives (desc, note) : utiles dans les JSON sources, mais jamais
    embarques dans la feuille — un joueur curieux lirait les secrets dans le
    code de la page. Retires de chaque injection de catalogue."""
    return {key: {f: v for f, v in entry.items() if f not in PRIVATE_KEYS}
            for key, entry in catalog.items()}


def load_items() -> dict:
    return json.loads(ITEMS_FILE.read_text(encoding="utf-8"))


def load_spells() -> dict:
    return json.loads(SPELLS_FILE.read_text(encoding="utf-8"))


def load_presets() -> dict:
    # Preset-eligible spells: self-contained (label + runes + icon), so it
    # doubles as the catalog used later to detect rune combinations without
    # needing spells.json. Book spells share their id with spells.json;
    # "secret" spells (never in the book) only ever exist here.
    return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))


def inject_grid(code: str) -> str:
    return (code.replace("{{GRID_COLS}}", str(GRID_COLS))
                .replace("{{GRID_ROWS}}", str(GRID_ROWS))
                .replace("{{GRID_BAGS}}", str(GRID_BAGS)))


PREVIEW_WRAPPER = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ARX sheet preview</title>
<link rel="stylesheet" href="preview.css">
<style>
  body { background: #111; }
  #arx-devbar { position: fixed; bottom: 0; left: 0; right: 0; background: #1e1a14;
    color: #e8d9b0; font: 13px sans-serif; padding: 6px 10px; display: flex;
    gap: 8px; align-items: center; z-index: 99; }
  #arx-devbar select, #arx-devbar button { font: inherit; }
</style>
</head>
<body>
__CONTENT__
<div id="arx-devbar">
  <strong>DEV</strong>
  <select id="arx-item"></select>
  <button id="arx-give">Donner</button>
  <button id="arx-give-runes">Toutes les runes</button>
  <button id="arx-learn-runes">Ingérer toutes les runes</button>
  <select id="arx-preset"></select>
  <button id="arx-preset-1">Preset 1</button>
  <button id="arx-preset-2">Preset 2</button>
  <button id="arx-preset-3">Preset 3</button>
  <button id="arx-reset">Vider</button>
  <span id="arx-msg"></span>
</div>
<script>
/* ===== ARX dev shim: emulates the Roll20 sheet-worker runtime in the local
   preview ONLY (this wrapper never ships to Roll20). ===== */
(function () {
  const ITEMS = __ITEMS__;
  const PRESETS = __PRESETS__;
  const handlers = {};
  function inputsFor(name) { return document.querySelectorAll('input[name="attr_' + name + '"]'); }
  function getAttr(name) { const el = inputsFor(name)[0]; return el ? (el.getAttribute("value") || "") : ""; }
  function setAttr(name, val) {
    inputsFor(name).forEach(function (el) { el.setAttribute("value", val); el.value = val; });
  }
  window.on = function (ev, fn) { handlers[ev] = fn; };
  window.getAttrs = function (keys, cb) {
    const v = {}; keys.forEach(function (k) { v[k] = getAttr(k); }); cb(v);
  };
  window.setAttrs = function (upd) { Object.keys(upd).forEach(function (k) { setAttr(k, String(upd[k])); }); };

  /* startRoll/finishRoll: absent du shim jusqu'ici — lancer un sort dans la
     preview jetait une ReferenceError. Ce stub resout les @{attr} depuis le
     DOM, lance reellement les des des [[...]] (formes NdF et (A*B)dF) et
     affiche la carte dans un chat de dev. */
  const chat = document.createElement("div");
  chat.id = "arx-chat";
  chat.style.cssText = "position:fixed;top:8px;right:8px;width:290px;max-height:70vh;overflow:auto;" +
    "z-index:98;font:12px sans-serif;display:flex;flex-direction:column;gap:6px;";
  document.body.appendChild(chat);
  function rollDice(count, faces) {
    let total = 0, parts = [];
    for (let i = 0; i < count; i++) { const r = 1 + Math.floor(Math.random() * faces); total += r; parts.push(r); }
    return { total: total, parts: parts };
  }
  window.startRoll = function (template, cb) {
    let txt = template.replace(/@\\{([^}]+)\\}/g, function (_, n) { return getAttr(n) || "0"; });
    txt = txt.replace(/\\[\\[([^\\]]+)\\]\\]/g, function (_, expr) {
      /* Group rolls, innermost first (the character class excludes braces, so
         a nested {..}kh1 resolves before the {..}kl1 wrapping it), then the
         rounding helpers Roll20 offers inside an inline roll. */
      let grouped = expr;
      for (let pass = 0; pass < 3; pass++) {
        grouped = grouped.replace(/\\{([^{}]+)\\}kh1/g, function (_, inner) { return "Math.max(" + inner + ")"; })
                         .replace(/\\{([^{}]+)\\}kl1/g, function (_, inner) { return "Math.min(" + inner + ")"; });
      }
      grouped = grouped.replace(/\\bfloor\\(/g, "Math.floor(").replace(/\\bceil\\(/g, "Math.ceil(");
      const withDice = grouped.replace(/(\\d+|\\([^()]*\\))d(\\d+)/g, function (_, cnt, faces) {
        let count = 0;
        try { count = Math.max(0, Math.floor(new Function("return (" + cnt + ")")())); } catch (e) { return "0"; }
        const r = rollDice(count, parseInt(faces, 10));
        return "(" + (r.parts.join("+") || "0") + ")";
      });
      try { return "\\u27E6" + new Function("return (" + withDice + ")")() + "\\u27E7"; } catch (e) { return expr; }
    });
    const card = document.createElement("div");
    card.style.cssText = "background:#20242b;color:#e8e2d5;border:1px solid #3a404b;border-radius:6px;padding:7px 9px;";
    txt.replace(/^&\\{template:default\\}\\s*/, "").split(/\\}\\}\\s*/).forEach(function (row) {
      const m = /\\{\\{([^=]+)=([\\s\\S]*)$/.exec(row);
      if (!m) { return; }
      const line = document.createElement("div");
      if (m[1] === "name") { line.style.cssText = "font-weight:bold;color:#d2a44a;border-bottom:1px solid #3a404b;margin-bottom:3px;"; line.textContent = m[2]; }
      else { line.textContent = m[1] + " : " + m[2]; }
      card.appendChild(line);
    });
    chat.prepend(card);
    cb({ rollId: 0, results: {} });
  };
  window.finishRoll = function () {};

  const workerScript = document.querySelector('script[type="text/worker"]');
  if (workerScript) { new Function(workerScript.textContent)(); }

  document.querySelectorAll('button[type="action"]').forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const h = handlers["clicked:" + btn.getAttribute("name").replace(/^act_/, "")];
      if (h) { h(); }
    });
  });

  /* Dev bar: first-fit give + reset (mirrors the mod script's placement). */
  const COLS = {{GRID_COLS}}, ROWS = {{GRID_ROWS}}, BAGS = {{GRID_BAGS}};
  const PER_LEVEL = COLS * ROWS;
  function cellsFor(a, w, h) {
    const base = Math.floor((a - 1) / PER_LEVEL) * PER_LEVEL;
    const idx = (a - 1) % PER_LEVEL;
    const col = idx % COLS, row = Math.floor(idx / COLS);
    if (col + w > COLS || row + h > ROWS) { return null; }
    const cells = [];
    for (let r = 0; r < h; r++) { for (let c = 0; c < w; c++) { cells.push("bag_" + (base + 1 + (row + r) * COLS + col + c)); } }
    return cells;
  }
  const sel = document.getElementById("arx-item");
  Object.keys(ITEMS).forEach(function (id) {
    const o = document.createElement("option");
    o.value = id;
    o.textContent = ITEMS[id].label + " (" + (ITEMS[id].size || "1x1") + ")";
    sel.appendChild(o);
  });
  function give(id) {
    const s = (ITEMS[id].size || "1x1").split("x"), w = +s[0], h = +s[1];
    const count = Math.min(BAGS, parseInt(getAttr("bag_count"), 10) || 1);
    for (let a = 1; a <= PER_LEVEL * count; a++) {
      const cells = cellsFor(a, w, h);
      if (!cells) { continue; }
      if (cells.some(function (c) { return getAttr(c) !== ""; })) { continue; }
      cells.forEach(function (c) { setAttr(c, "#bag_" + a); });
      setAttr("bag_" + a, id);
      document.getElementById("arx-msg").textContent = "+ " + ITEMS[id].label;
      return;
    }
    document.getElementById("arx-msg").textContent = "Sac plein !";
  }
  document.getElementById("arx-give").addEventListener("click", function () { give(sel.value); });
  document.getElementById("arx-give-runes").addEventListener("click", function () {
    Object.keys(ITEMS).forEach(function (id) { if (ITEMS[id].effect === "rune") { give(id); } });
    document.getElementById("arx-msg").textContent = "Toutes les runes données";
  });

  /* Skips the bag+grimoire dance entirely: marks every rune known and fills
     the 20 spellbook slots in their fixed order (see inventory.js's
     spellbookSlotFor), so pages/spells unlock instantly for testing. */
  document.getElementById("arx-learn-runes").addEventListener("click", function () {
    const runeIds = Object.keys(ITEMS).filter(function (id) { return ITEMS[id].effect === "rune"; });
    runeIds.forEach(function (id, i) {
      setAttr("known_" + id.slice(5), "1");
      setAttr("spellbook_" + (i + 1), id);
    });
    document.getElementById("arx-msg").textContent = "Toutes les runes ingérées";
  });

  /* Presets have no real obtention mechanic yet (scroll item / actions, TBD) —
     this dev-only control just drops a preset id straight into a slot to
     check the memorized-spell visuals. */
  const presetSel = document.getElementById("arx-preset");
  Object.keys(PRESETS).forEach(function (id) {
    const o = document.createElement("option");
    o.value = id;
    o.textContent = PRESETS[id].label;
    presetSel.appendChild(o);
  });
  [1, 2, 3].forEach(function (n) {
    document.getElementById("arx-preset-" + n).addEventListener("click", function () {
      setAttr("preset_slot_" + n, presetSel.value);
      document.getElementById("arx-msg").textContent = "Preset " + n + " = " + presetSel.value;
    });
  });

  document.getElementById("arx-reset").addEventListener("click", function () {
    for (let i = 1; i <= PER_LEVEL * BAGS; i++) { setAttr("bag_" + i, ""); }
    ["equip_head", "equip_torso", "equip_belt", "equip_main_hand", "equip_off_hand",
     "equip_jewel_1", "equip_jewel_2", "hand", "hand_from", "hand_cat", "fit"]
      .forEach(function (n) { setAttr(n, ""); });
    [1, 2, 3].forEach(function (n) { setAttr("preset_slot_" + n, ""); });
    for (let i = 1; i <= 20; i++) { setAttr("spellbook_" + i, ""); }
    Object.keys(ITEMS).forEach(function (id) { if (ITEMS[id].effect === "rune") { setAttr("known_" + id.slice(5), ""); } });
    setAttr("craft_runes", "");
    [1, 2, 3, 4, 5].forEach(function (n) { setAttr("craft_pos_" + n, ""); });
    setAttr("recipe_spell", "");
    setAttr("forget_mode", "0");
    setAttr("bag_count", "1");
    setAttr("bag_level", "1");
    document.getElementById("arx-msg").textContent = "Inventaire vidé";
  });
  const q = new URLSearchParams(location.search).get("give");
  if (q) { q.split(",").forEach(function (id) { if (ITEMS[id]) { give(id); } }); }
  document.body.classList.add("arx-shim-ready");
})();
</script>
</body>
</html>
"""


def jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(SRC / "templates"), keep_trailing_newline=True)


def render_html() -> str:
    html = jinja_env().get_template("sheet.html.j2").render(
        items=load_items(), spells=load_spells(), presets=load_presets(),
        cols=GRID_COLS, rows=GRID_ROWS, bags=GRID_BAGS)
    return html + render_worker()


def build_css(asset_base: str) -> str:
    parts = []
    for name in CSS_FILES:
        if name.endswith(".j2"):
            parts.append(jinja_env().get_template(f"css/{name}").render(
                items=load_items(), spells=load_spells(), presets=load_presets(),
                cols=GRID_COLS, rows=GRID_ROWS, bags=GRID_BAGS))
        else:
            parts.append((SRC / "css" / name).read_text(encoding="utf-8"))
    css = "\n".join(parts).replace("{{ASSET_BASE}}", asset_base)
    # Anchored to url('...') itself (not a bare asset_base.replace, which can
    # also match asset_base as a stray substring elsewhere in the CSS).
    pattern = r"url\((['\"])" + re.escape(asset_base) + r"([^'\"]*)\1\)"
    return re.sub(pattern, r"url(\1" + asset_base + r"\2?v=" + ASSET_VERSION + r"\1)", css)


def render_worker() -> str:
    # Spell visibility (page + rune-combination) is pure CSS (see magic-slots.css.j2);
    # the worker only ever needs to know about runes, not spells.
    parts = [(SRC / "workers" / name).read_text(encoding="utf-8") for name in WORKER_FILES]
    code = ("\n".join(parts)
            .replace("{{ITEMS_JSON}}", json.dumps(strip_private(load_items()), ensure_ascii=False))
            .replace("{{PRESETS_JSON}}", json.dumps(load_presets(), ensure_ascii=False))
            .replace("{{SPELLS_JSON}}", json.dumps(strip_private(load_spells()), ensure_ascii=False)))
    return f'<script type="text/worker">\n{inject_grid(code)}\n</script>\n'


def render_mod() -> str:
    code = (SRC / "mod" / "arx-mod.js").read_text(encoding="utf-8")
    return inject_grid(code.replace("{{ITEMS_JSON}}", json.dumps(strip_private(load_items()), ensure_ascii=False)))


def build() -> None:
    BUILD.mkdir(exist_ok=True)
    html = render_html()
    (BUILD / "sheet.html").write_text(html, encoding="utf-8")
    (BUILD / "sheet.css").write_text(build_css(ASSET_BASE), encoding="utf-8")
    (BUILD / "preview.css").write_text(build_css(PREVIEW_ASSET_BASE), encoding="utf-8")
    preview = inject_grid(PREVIEW_WRAPPER
                          .replace("__CONTENT__", html)
                          .replace("__ITEMS__", json.dumps(strip_private(load_items()), ensure_ascii=False))
                          .replace("__PRESETS__", json.dumps(load_presets(), ensure_ascii=False)))
    (BUILD / "preview.html").write_text(preview, encoding="utf-8")
    (BUILD / "arx-mod.js").write_text(render_mod(), encoding="utf-8")
    print("built: build/sheet.html sheet.css preview.html preview.css arx-mod.js")


def watch() -> None:
    last = None
    while True:
        current = {p: p.stat().st_mtime for p in SRC.rglob("*") if p.is_file()}
        if current != last:
            # Keep watching through transient errors (half-saved file, Jinja typo).
            try:
                build()
            except Exception as exc:
                print(f"build failed: {exc}")
            last = current
        time.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    (watch if args.watch else build)()
