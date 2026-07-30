/* ARX Mod script — paste into the game's API tab (Pro account).
   Usage (GM only, select the character's token first):
     !arxgive <item_id>          give an item (drops in the first free bag slot)
     !arxlearnall                mark every rune known + fill the grimoire
     !arxforgetrune <rune_id>    un-learn a single rune (e.g. rune-aam)
     !arxforgetallrunes          un-learn every rune (reverse of !arxlearnall)
     !arxlockmap <1-8>           re-lock a single map level (level 1 can't be locked)
     !arxlockallmaps             re-lock every map level except level 1
     !arxunlockguardian          unlock the Guardian posture
     !arxlockguardian            re-lock the Guardian posture
     !arxresetinventory          empty every bag slot + clear the hand (fixes stuck/ghost cells)
     !arxresetall                factory-reset the whole character (stats, inventory, magic, map, postures, gold)
     !arxpreset <1-3> <spell_id> set a memorized-spell slot
     !arxpage <1-10>             switch the magic book to that spell page
     !arxtab base|magic          switch the active sheet page
     !arxhelp                    list every command in a GM whisper          */
const ARX_ITEMS = {{ITEMS_JSON}};
const ARX_COLS = {{GRID_COLS}};
const ARX_ROWS = {{GRID_ROWS}};
const ARX_BAGS = {{GRID_BAGS}};
const ARX_PER_LEVEL = ARX_COLS * ARX_ROWS;
const ARX_RUNE_ORDER = Object.keys(ARX_ITEMS).filter(function (id) { return ARX_ITEMS[id].effect === "rune"; });

/* Mirrors base.html.j2's own `defaults`/`single_stat_mod_seeds` dicts — kept
   in sync by hand (see !arxresetall below), since that template has no JSON
   file of its own to share with this mod script. */
const ARX_SKILLS = ["stealth", "technical", "intuition", "ethereal_link", "object_knowledge",
                     "casting", "close_combat", "projectile", "defense"];
const ARX_STATS = ["strength", "mental", "dexterity", "constitution"].concat(ARX_SKILLS)
                   .concat(["armor_class", "magic_resistance", "poison_resistance", "damages"]);
const ARX_DEFAULTS = {
  strength: 6, mental: 6, dexterity: 6, constitution: 6,
  stealth: 12, technical: 12, intuition: 12, ethereal_link: 12,
  object_knowledge: 15, casting: 12,
  close_combat: 18, projectile: 18, defense: 18,
  armor_class: 1, magic_resistance: 12, poison_resistance: 16, damages: 3,
  health: 12, mana: 6
};
const ARX_SINGLE_STAT_MOD_SEEDS = { damages: 3, armor_class: 1, magic_resistance: 12, poison_resistance: 16 };

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

/* health_max/mana_max on the sheet (attr_health_max, attr_mana_max) are
   Roll20's own reserved "_max" suffix — they read/write the MAX field of
   the "health"/"mana" attribute itself, not a separate attribute. That
   convention only exists at the sheet/worker layer; the API sandbox's
   findObjs/attr.set know nothing about it, so a plain arxSetAttr(charId,
   "mana_max", …) creates a bogus standalone "mana_max" attribute instead —
   harmless but confusing clutter, and it leaves the real max untouched. */
function arxSetAttrMax(charId, baseName, value) {
  let attr = findObjs({ type: "attribute", characterid: charId, name: baseName })[0];
  if (!attr) { attr = createObj("attribute", { characterid: charId, name: baseName, current: "" }); }
  attr.set("max", value);
  const stray = findObjs({ type: "attribute", characterid: charId, name: baseName + "_max" })[0];
  if (stray) { stray.remove(); }
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
  if (msg.type !== "api" || msg.content.indexOf("!arxforgetallrunes") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  ARX_RUNE_ORDER.forEach(function (id, i) {
    arxSetAttr(charId, "known_" + id.slice(5), "");
    arxSetAttr(charId, "spellbook_" + (i + 1), "");
  });
  whisper("Toutes les runes oubliées (" + ARX_RUNE_ORDER.length + ").");
});

/* Checked before !arxforgetrune below: "!arxforgetallrunes" doesn't share a
   prefix with "!arxforgetrune" past "!arxforget" (rune vs allrunes), so the
   two never collide — no ordering dependency between these two handlers. */
on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxforgetrune") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const runeId = msg.content.trim().split(/\s+/)[1];
  const idx = ARX_RUNE_ORDER.indexOf(runeId);
  if (idx === -1) { whisper("Rune inconnue : " + (runeId || "(vide)")); return; }
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "known_" + runeId.slice(5), "");
  arxSetAttr(charId, "spellbook_" + (idx + 1), "");
  whisper("Rune oubliée : " + ARX_ITEMS[runeId].label);
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxlockallmaps") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  for (let n = 2; n <= 8; n++) { arxSetAttr(charId, "known_map_" + n, ""); }
  whisper("Niveaux 2-8 re-verrouillés (niveau 1 reste libre).");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxlockmap") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const level = parseInt(msg.content.trim().split(/\s+/)[1], 10);
  if (!(level >= 1 && level <= 8)) { whisper("Usage : !arxlockmap <1-8>"); return; }
  if (level === 1) { whisper("Le niveau 1 ne peut pas être verrouillé."); return; }
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "known_map_" + level, "");
  whisper("Niveau " + level + " re-verrouillé.");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxunlockguardian") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "posture_guardian_unlocked", "1");
  whisper("Posture du Gardien débloquée.");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxlockguardian") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "posture_guardian_unlocked", "");
  whisper("Posture du Gardien re-verrouillée.");
});

/* Nuclear option for a stuck/ghost bag cell (e.g. a leftover "#bag_N" covered-
   cell pointer that never got cleared): empties every bag slot on every
   level and drops whatever's in hand, rather than hunting down one attribute
   in Roll20's editor. */
on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxresetinventory") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  const total = ARX_PER_LEVEL * ARX_BAGS;
  for (let i = 1; i <= total; i++) { arxSetAttr(charId, "bag_" + i, ""); }
  ["hand", "hand_from", "hand_cat", "hand_effect", "fit"].forEach(function (name) {
    arxSetAttr(charId, name, "");
  });
  whisper("Inventaire vidé (" + total + " cases) et main relâchée.");
});

/* Factory reset for a fresh test run: everything but the character's own
   name goes back to a brand-new-character state. */
on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxresetall") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }

  const total = ARX_PER_LEVEL * ARX_BAGS;
  for (let i = 1; i <= total; i++) { arxSetAttr(charId, "bag_" + i, ""); }
  ["hand", "hand_from", "hand_cat", "hand_effect", "fit"].forEach(function (n) { arxSetAttr(charId, n, ""); });
  arxSetAttr(charId, "bag_count", "1");
  arxSetAttr(charId, "bag_level", "1");
  arxSetAttr(charId, "gold", "0");

  ["equip_head", "equip_torso", "equip_belt", "equip_main_hand", "equip_off_hand",
   "equip_jewel_1", "equip_jewel_2"].forEach(function (n) { arxSetAttr(charId, n, ""); });

  ARX_RUNE_ORDER.forEach(function (id, i) {
    arxSetAttr(charId, "known_" + id.slice(5), "");
    arxSetAttr(charId, "spellbook_" + (i + 1), "");
  });
  [1, 2, 3].forEach(function (n) { arxSetAttr(charId, "preset_slot_" + n, ""); });
  arxSetAttr(charId, "craft_runes", "");
  for (let i = 1; i <= 5; i++) { arxSetAttr(charId, "craft_pos_" + i, ""); }
  arxSetAttr(charId, "recipe_spell", "");
  arxSetAttr(charId, "forget_mode", "0");
  arxSetAttr(charId, "spell_page", "1");

  for (let n = 2; n <= 8; n++) { arxSetAttr(charId, "known_map_" + n, ""); }

  arxSetAttr(charId, "posture", "");
  arxSetAttr(charId, "posture_guardian_unlocked", "");
  arxSetAttr(charId, "focus_active", "0");

  arxSetAttr(charId, "level", "0");
  ARX_STATS.forEach(function (name) {
    arxSetAttr(charId, name, ARX_DEFAULTS[name]);
    arxSetAttr(charId, name + "_applied_mod", "0");
  });
  ARX_SKILLS.forEach(function (name) {
    arxSetAttr(charId, name + "_applied_stat_mod", ARX_DEFAULTS[name]);
  });
  Object.keys(ARX_SINGLE_STAT_MOD_SEEDS).forEach(function (name) {
    arxSetAttr(charId, name + "_applied_stat_mod", ARX_SINGLE_STAT_MOD_SEEDS[name]);
  });
  ["health", "mana"].forEach(function (name) {
    arxSetAttr(charId, name, ARX_DEFAULTS[name]);
    arxSetAttrMax(charId, name, ARX_DEFAULTS[name]);
    arxSetAttr(charId, name + "_max_applied_mod", "0");
    arxSetAttr(charId, name + "_max_applied_stat_mod", ARX_DEFAULTS[name]);
  });

  arxSetAttr(charId, "sheet_tab", "base");
  whisper("Personnage entièrement réinitialisé.");
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

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxhelp") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  sendChat("ARX", "/w gm " + [
    "Commandes disponibles (sélectionne d'abord le token du perso) :",
    "!arxgive <item_id> — donne un objet (première case libre)",
    "!arxlearnall — apprend toutes les runes + remplit le grimoire",
    "!arxforgetrune <rune_id> — désapprend une rune (ex: rune-aam)",
    "!arxforgetallrunes — désapprend toutes les runes",
    "!arxlockmap <1-8> — reverrouille un niveau de carte (le 1 reste libre)",
    "!arxlockallmaps — reverrouille tous les niveaux sauf le 1",
    "!arxunlockguardian — débloque la posture du Gardien",
    "!arxlockguardian — reverrouille la posture du Gardien",
    "!arxresetinventory — vide toutes les cases de sac + relâche la main",
    "!arxresetall — réinitialise tout le personnage (stats, inventaire, magie, carte, postures, or)",
    "!arxpreset <1-3> <spell_id> — définit un emplacement de sort mémorisé",
    "!arxpage <1-10> — change la page de sorts affichée",
    "!arxtab base|magic — change la page active de la fiche"
  ].join("<br>"));
});
