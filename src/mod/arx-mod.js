/* ARX Mod script — paste into the game's API tab (Pro account).
   Usage (GM only, select the character's token first):
     !arxgive <item_id>          give an item (drops in the first free bag slot)
     !arxlearnall                mark every rune known + fill the grimoire
     !arxpreset <1-3> <spell_id> set a memorized-spell slot
     !arxpage <1-10>             switch the magic book to that spell page
     !arxtab base|magic          switch the active sheet page               */
const ARX_ITEMS = {{ITEMS_JSON}};
const ARX_COLS = {{GRID_COLS}};
const ARX_ROWS = {{GRID_ROWS}};
const ARX_BAGS = {{GRID_BAGS}};
const ARX_PER_LEVEL = ARX_COLS * ARX_ROWS;
const ARX_RUNE_ORDER = Object.keys(ARX_ITEMS).filter(function (id) { return ARX_ITEMS[id].effect === "rune"; });

function arxCharIdFromMsg(msg) {
  if (!msg.selected || !msg.selected.length) { return null; }
  const token = getObj("graphic", msg.selected[0]._id);
  return token && token.get("represents");
}

function arxSetAttr(charId, name, value) {
  let attr = findObjs({ type: "attribute", characterid: charId, name: name })[0];
  if (!attr) { attr = createObj("attribute", { characterid: charId, name: name, current: "" }); }
  attr.set("current", value);
}

function arxSizeOf(itemId) {
  const s = (ARX_ITEMS[itemId] && ARX_ITEMS[itemId].size) || "1x1";
  const parts = s.split("x");
  return { w: parseInt(parts[0], 10) || 1, h: parseInt(parts[1], 10) || 1 };
}

/* Cells covered by a footprint anchored at bag index (1-based); null if the
   rectangle leaves the anchor's level grid. Footprints never span levels. */
function arxCellsFor(anchorIndex, w, h) {
  const base = Math.floor((anchorIndex - 1) / ARX_PER_LEVEL) * ARX_PER_LEVEL;
  const idx = (anchorIndex - 1) % ARX_PER_LEVEL;
  const col = idx % ARX_COLS;
  const row = Math.floor(idx / ARX_COLS);
  if (col + w > ARX_COLS || row + h > ARX_ROWS) { return null; }
  const cells = [];
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) {
      cells.push("bag_" + (base + 1 + (row + r) * ARX_COLS + col + c));
    }
  }
  return cells;
}

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxgive") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const itemId = msg.content.trim().split(/\s+/)[1];
  if (!itemId || !ARX_ITEMS[itemId]) { whisper("Item inconnu : " + (itemId || "(vide)")); return; }
  if (!msg.selected || !msg.selected.length) { whisper("Sélectionne d'abord un token."); return; }
  const token = getObj("graphic", msg.selected[0]._id);
  const charId = token && token.get("represents");
  if (!charId) { whisper("Ce token ne représente aucun personnage."); return; }

  const countAttr = findObjs({ type: "attribute", characterid: charId, name: "bag_count" })[0];
  let count = countAttr ? parseInt(countAttr.get("current"), 10) : 1;
  if (!(count >= 1 && count <= ARX_BAGS)) { count = 1; }
  const limit = ARX_PER_LEVEL * count;

  const attrs = {};
  for (let i = 1; i <= limit; i++) {
    const name = "bag_" + i;
    let attr = findObjs({ type: "attribute", characterid: charId, name: name })[0];
    if (!attr) { attr = createObj("attribute", { characterid: charId, name: name, current: "" }); }
    attrs[name] = attr;
  }

  const size = arxSizeOf(itemId);
  for (let a = 1; a <= limit; a++) {
    const cells = arxCellsFor(a, size.w, size.h);
    if (!cells) { continue; }
    const free = cells.every(function (c) { return !attrs[c].get("current"); });
    if (!free) { continue; }
    const anchor = "bag_" + a;
    cells.forEach(function (c) { attrs[c].set("current", c === anchor ? itemId : "#" + anchor); });
    sendChat("ARX", "Obtenu : " + ARX_ITEMS[itemId].label);
    return;
  }
  whisper("Sac plein (pas de place " + size.w + "x" + size.h + ") !");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxlearnall") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  ARX_RUNE_ORDER.forEach(function (id, i) {
    arxSetAttr(charId, "known_" + id.slice(5), "1");
    arxSetAttr(charId, "spellbook_" + (i + 1), id);
  });
  whisper("Toutes les runes apprises (" + ARX_RUNE_ORDER.length + ").");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxpreset") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const parts = msg.content.trim().split(/\s+/);
  const slot = parseInt(parts[1], 10);
  const spellId = parts[2];
  if (!(slot >= 1 && slot <= 3) || !spellId) { whisper("Usage : !arxpreset <1-3> <spell_id>"); return; }
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "preset_slot_" + slot, spellId);
  whisper("Preset " + slot + " = " + spellId);
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxpage") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const page = parseInt(msg.content.trim().split(/\s+/)[1], 10);
  if (!(page >= 1 && page <= 10)) { whisper("Usage : !arxpage <1-10>"); return; }
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "spell_page", page);
  whisper("Page de sorts = " + page);
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxtab") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const tab = msg.content.trim().split(/\s+/)[1];
  if (tab !== "base" && tab !== "magic") { whisper("Usage : !arxtab base|magic"); return; }
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "sheet_tab", tab);
  whisper("Page active = " + tab);
});
