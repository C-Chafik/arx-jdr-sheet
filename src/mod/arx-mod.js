/* ARX Mod script — paste into the game's API tab (Pro account).
   Usage (GM only): select a token, then  !arxgive <item_id>          */
const ARX_ITEMS = {{ITEMS_JSON}};
const ARX_COLS = 16;
const ARX_ROWS = 3;

function arxSizeOf(itemId) {
  const s = (ARX_ITEMS[itemId] && ARX_ITEMS[itemId].size) || "1x1";
  const parts = s.split("x");
  return { w: parseInt(parts[0], 10) || 1, h: parseInt(parts[1], 10) || 1 };
}

/* Cells covered by a footprint anchored at bag index (1-based); null if out of grid. */
function arxCellsFor(anchorIndex, w, h) {
  const col = (anchorIndex - 1) % ARX_COLS;
  const row = Math.floor((anchorIndex - 1) / ARX_COLS);
  if (col + w > ARX_COLS || row + h > ARX_ROWS) { return null; }
  const cells = [];
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) {
      cells.push("bag_" + (1 + (row + r) * ARX_COLS + col + c));
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

  const attrs = {};
  for (let i = 1; i <= ARX_COLS * ARX_ROWS; i++) {
    const name = "bag_" + i;
    let attr = findObjs({ type: "attribute", characterid: charId, name: name })[0];
    if (!attr) { attr = createObj("attribute", { characterid: charId, name: name, current: "" }); }
    attrs[name] = attr;
  }

  const size = arxSizeOf(itemId);
  for (let a = 1; a <= ARX_COLS * ARX_ROWS; a++) {
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
