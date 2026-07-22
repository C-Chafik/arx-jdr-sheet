#!/usr/bin/env python3
"""Assemble the Roll20 sheet: render Jinja2 templates, concatenate CSS."""
import argparse
import json
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
SRC = ROOT / "src"
BUILD = ROOT / "build"

# Concatenation order matters: later files override earlier ones.
# Entries ending in .j2 are rendered via Jinja (from src/templates/css/).
CSS_FILES = ["base.css", "tabs.css", "inventory.css",
             "pages/base.css", "pages/base-hover.css",
             "inventory-slots.css.j2"]

WORKER_FILES = ["inventory.js"]

# Roll20 only loads HTTPS assets; preview uses the local files instead.
ASSET_BASE = "https://raw.githubusercontent.com/C-Chafik/arx-jdr-sheet/main/assets"
PREVIEW_ASSET_BASE = "../assets"

ITEMS_FILE = ROOT / "items.json"

# Bag grid dimensions — single source of truth, injected into templates,
# the sheet worker, the mod script and the dev shim.
# (Column 16 on Inventory.png is the pouch: not a storage cell.)
GRID_COLS = 15
GRID_ROWS = 3


def load_items() -> dict:
    return json.loads(ITEMS_FILE.read_text(encoding="utf-8"))


def inject_grid(code: str) -> str:
    return code.replace("{{GRID_COLS}}", str(GRID_COLS)).replace("{{GRID_ROWS}}", str(GRID_ROWS))


PREVIEW_WRAPPER = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ARX sheet preview</title>
<link rel="stylesheet" href="preview.css">
<style>
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
  <button id="arx-reset">Vider</button>
  <span id="arx-msg"></span>
</div>
<script>
/* ===== ARX dev shim: emulates the Roll20 sheet-worker runtime in the local
   preview ONLY (this wrapper never ships to Roll20). ===== */
(function () {
  const ITEMS = __ITEMS__;
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
  const COLS = {{GRID_COLS}}, ROWS = {{GRID_ROWS}};
  function cellsFor(a, w, h) {
    const col = (a - 1) % COLS, row = Math.floor((a - 1) / COLS);
    if (col + w > COLS || row + h > ROWS) { return null; }
    const cells = [];
    for (let r = 0; r < h; r++) { for (let c = 0; c < w; c++) { cells.push("bag_" + (1 + (row + r) * COLS + col + c)); } }
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
    for (let a = 1; a <= COLS * ROWS; a++) {
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
  document.getElementById("arx-reset").addEventListener("click", function () {
    for (let i = 1; i <= COLS * ROWS; i++) { setAttr("bag_" + i, ""); }
    ["equip_head", "equip_torso", "equip_belt", "equip_main_hand", "equip_off_hand",
     "equip_jewel_1", "equip_jewel_2", "hand", "hand_from", "hand_cat", "fit"]
      .forEach(function (n) { setAttr(n, ""); });
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
        items=load_items(), cols=GRID_COLS, rows=GRID_ROWS)
    return html + render_worker()


def build_css(asset_base: str) -> str:
    parts = []
    for name in CSS_FILES:
        if name.endswith(".j2"):
            parts.append(jinja_env().get_template(f"css/{name}").render(
                items=load_items(), cols=GRID_COLS, rows=GRID_ROWS))
        else:
            parts.append((SRC / "css" / name).read_text(encoding="utf-8"))
    return "\n".join(parts).replace("{{ASSET_BASE}}", asset_base)


def render_worker() -> str:
    parts = [(SRC / "workers" / name).read_text(encoding="utf-8") for name in WORKER_FILES]
    code = "\n".join(parts).replace("{{ITEMS_JSON}}", json.dumps(load_items(), ensure_ascii=False))
    return f'<script type="text/worker">\n{inject_grid(code)}\n</script>\n'


def render_mod() -> str:
    code = (SRC / "mod" / "arx-mod.js").read_text(encoding="utf-8")
    return inject_grid(code.replace("{{ITEMS_JSON}}", json.dumps(load_items(), ensure_ascii=False)))


def build() -> None:
    BUILD.mkdir(exist_ok=True)
    html = render_html()
    (BUILD / "sheet.html").write_text(html, encoding="utf-8")
    (BUILD / "sheet.css").write_text(build_css(ASSET_BASE), encoding="utf-8")
    (BUILD / "preview.css").write_text(build_css(PREVIEW_ASSET_BASE), encoding="utf-8")
    preview = inject_grid(PREVIEW_WRAPPER
                          .replace("__CONTENT__", html)
                          .replace("__ITEMS__", json.dumps(load_items(), ensure_ascii=False)))
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
