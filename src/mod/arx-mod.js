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
     !arxfavor                   grant the Faveur du Noden status
     !arxtwist                   inflict the Coups du sort status
     !arxfateclear               clear the fate status (favor or twist)
     !arxmod <stat> <valeur>     set a GM bonus/malus badge on every selected token (0 removes it)
     !arxclearmods               remove every GM bonus/malus on every selected token
     !arxunlockpanel             unlock the GM admin panel on this character
     !arxlockpanel               re-lock the GM admin panel on this character
     !arxlootopen bag|body|chest|place|secured-chest
                                  open a shared loot pool for the currently selected tokens
     !arxlootadd <item_id>       add an item to the open loot pool
     !arxlootclose               close the loot pool (hides it for everyone who had it)
     !arxloottake <cell>         (not for GM use — fired by a player's own "take" button)
     !arxconsume                 (not for GM use — fired by a player's own "Consommer" button)
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

function arxGetAttr(charId, name) {
  const attr = findObjs({ type: "attribute", characterid: charId, name: name })[0];
  return attr ? String(attr.get("current") || "") : "";
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

/* Places an item in the first free bag slot (respecting its real
   items.json footprint) on the given character — shared by !arxgive and
   !arxloottake so both hand out items exactly the same way. Returns true
   on success, false if there's no room (caller decides how to report that). */
function arxGiveToCharacter(charId, itemId) {
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
    return true;
  }
  return false;
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
  if (arxGiveToCharacter(charId, itemId)) {
    sendChat("ARX", "Obtenu : " + ARX_ITEMS[itemId].label);
  } else {
    const size = arxSizeOf(itemId);
    whisper("Sac plein (pas de place " + size.w + "x" + size.h + ") !");
  }
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

/* Fate status (attr_fate, one at a time): shown to the player on the posture
   row of their sheet, but only ever written from here — the sheet has no
   control wired to it. !arxfateclear checked before !arxfavor/!arxtwist
   would be unnecessary (distinct prefixes), kept in the same one-command-
   per-handler style as everything else. */
on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxfavor") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "fate", "favor");
  whisper("Faveur du Noden accordée.");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxtwist") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "fate", "twist");
  whisper("Coups du sort infligé.");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxfateclear") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "fate", "");
  whisper("Sort du personnage retiré.");
});

/* GM bonus/malus (attr_<stat>_gm_mod, shown as the colored badge beside each
   value — see base.html.j2/base.css.j2): SET semantics (the value replaces
   the current mod, 0 removes it), applied to EVERY selected token at once —
   same multi-token loop as !arxlootopen. Each mod counts in its OWN stat's
   roll targets (skill/Focus/casting rolls in base.html.j2, hand damage in
   inventory.js) but never cascades into derived recomputes — a strength mod
   does not recompute close_combat; the GM mods close_combat directly. */
const ARX_GM_MOD_STATS = ["strength", "mental", "dexterity", "constitution",
  "stealth", "technical", "intuition", "ethereal_link", "object_knowledge",
  "casting", "close_combat", "projectile", "defense", "armor_class",
  "magic_resistance", "poison_resistance", "damages"];

function arxCharIdsFromMsg(msg) {
  const charIds = [];
  (msg.selected || []).forEach(function (sel) {
    const token = getObj("graphic", sel._id);
    const charId = token && token.get("represents");
    if (charId && charIds.indexOf(charId) === -1) { charIds.push(charId); }
  });
  return charIds;
}

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxmod") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const parts = msg.content.trim().split(/\s+/);
  const stat = parts[1];
  const value = parseInt(parts[2], 10);
  if (ARX_GM_MOD_STATS.indexOf(stat) === -1 || isNaN(value)) {
    whisper("Usage : !arxmod <stat> <valeur> (0 retire le mod) — stats : " + ARX_GM_MOD_STATS.join(", "));
    return;
  }
  const charIds = arxCharIdsFromMsg(msg);
  if (!charIds.length) { whisper("Sélectionne d'abord un ou plusieurs tokens."); return; }
  charIds.forEach(function (charId) { arxSetAttr(charId, stat + "_gm_mod", String(value)); });
  whisper(value === 0
    ? "Mod " + stat + " retiré pour " + charIds.length + " personnage(s)."
    : "Mod " + stat + " fixé à " + (value > 0 ? "+" : "") + value + " pour " + charIds.length + " personnage(s).");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxclearmods") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charIds = arxCharIdsFromMsg(msg);
  if (!charIds.length) { whisper("Sélectionne d'abord un ou plusieurs tokens."); return; }
  charIds.forEach(function (charId) {
    ARX_GM_MOD_STATS.forEach(function (stat) { arxSetAttr(charId, stat + "_gm_mod", "0"); });
  });
  whisper("Tous les bonus/malus retirés pour " + charIds.length + " personnage(s).");
});

/* Unlocks the GM admin panel (gear icon + full-catalog "give" grid, see
   base.css.j2/sheet.html.j2) on the SELECTED character's own sheet — meant
   for the GM's own utility character, never a player's. Only this command
   can set the flag; a player has no in-sheet way to trigger it themselves. */
on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxunlockpanel") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "gm_panel_unlocked", "1");
  whisper("Panel MJ débloqué sur ce personnage.");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxlockpanel") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const charId = arxCharIdFromMsg(msg);
  if (!charId) { whisper("Sélectionne d'abord un token."); return; }
  arxSetAttr(charId, "gm_panel_unlocked", "");
  whisper("Panel MJ re-verrouillé sur ce personnage.");
});

/* ============================================================================
   Shared loot panel: one pool at a time, visible only to whichever
   characters the GM opened it for (see loot-panel.html.j2/loot-panel.css.j2
   — this sheet never writes attr_loot_*, only this script does, except the
   take buttons, which are static per-cell "!arxloottake N" roll buttons —
   this script resolves cell N's CURRENT contents itself from state.ARX_LOOT
   rather than trusting a possibly-stale mirrored attribute).
   state.ARX_LOOT persists across API sandbox restarts (Roll20's own state
   mechanism), so a loot drop survives a script reload mid-session.
   cells: { <cellNumber>: itemId, or "#<anchorNumber>" for a covered cell of
   a multi-cell item } — same anchor+covered-cell idea as the bag, just on
   its own 3x11 grid with no levels. ============================================ */
const ARX_LOOT_COLS = 3, ARX_LOOT_ROWS = 11;
const ARX_LOOT_TOTAL = ARX_LOOT_COLS * ARX_LOOT_ROWS;
const ARX_LOOT_SKINS = ["bag", "body", "chest", "place", "secured-chest"];
state.ARX_LOOT = state.ARX_LOOT || { skin: "chest", cells: {}, subscribers: [] };

function arxWhisperTo(msg, text) {
  const player = getObj("player", msg.playerid);
  const name = player ? player.get("_displayname") : "gm";
  sendChat("ARX", "/w \"" + name + "\" " + text);
}

/* Resolves which character a player-triggered command (like !arxloottake)
   applies to: a selected token still wins if there is one (lets the GM
   override by selecting a specific token), but with nothing selected —
   e.g. a player clicking "Take" straight from their own open sheet,
   without ever having clicked their token on the map — falls back to
   whichever character lists this player in its "controlled by" list. */
function arxResolveCharacterForPlayer(msg) {
  if (msg.selected && msg.selected.length) {
    const token = getObj("graphic", msg.selected[0]._id);
    const charId = token && token.get("represents");
    if (charId) { return charId; }
  }
  const owned = findObjs({ type: "character" }).find(function (c) {
    const controllers = (c.get("controlledby") || "").split(",").map(function (s) { return s.trim(); });
    return controllers.indexOf(msg.playerid) !== -1;
  });
  return owned ? owned.id : null;
}

function arxLootCellsFor(anchor, w, h) {
  const idx = anchor - 1;
  const col = idx % ARX_LOOT_COLS;
  const row = Math.floor(idx / ARX_LOOT_COLS);
  if (col + w > ARX_LOOT_COLS || row + h > ARX_LOOT_ROWS) { return null; }
  const cells = [];
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) { cells.push(1 + (row + r) * ARX_LOOT_COLS + col + c); }
  }
  return cells;
}

/* Pushes the current shared pool onto every subscribed character's own
   mirrored attributes, so each of their sheets shows the same thing. */
function arxLootRefresh() {
  const loot = state.ARX_LOOT;
  loot.subscribers.forEach(function (charId) {
    for (let i = 1; i <= ARX_LOOT_TOTAL; i++) {
      arxSetAttr(charId, "loot_" + i, loot.cells[i] || "");
    }
    arxSetAttr(charId, "loot_skin", loot.skin);
    arxSetAttr(charId, "loot_open", "1");
  });
}

/* Flips the GM admin panel's own "is a loot pool open" flag on every
   admin character (gm_panel_unlocked=1) — drives the two-mode catalog
   click (give directly vs add to the open pool, see gm-panel.css.j2). Not
   scoped to loot subscribers: the admin character giving/adding items is
   usually NOT one of the players watching the loot. */
function arxRefreshAdminLootFlag(isOpen) {
  findObjs({ type: "attribute", name: "gm_panel_unlocked", current: "1" }).forEach(function (attr) {
    arxSetAttr(attr.get("characterid"), "gm_panel_loot_open", isOpen ? "1" : "0");
  });
}

/* Opens a fresh pool for exactly the currently selected tokens' characters
   (trusted-players model: whoever the GM selects "sees" the loot — some
   players in, some out, is the whole point, so this is manual, not an
   auto-detect-every-ARX-character scan). */
on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxlootopen") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const skin = msg.content.trim().split(/\s+/)[1];
  if (ARX_LOOT_SKINS.indexOf(skin) === -1) { whisper("Usage : !arxlootopen " + ARX_LOOT_SKINS.join("|")); return; }
  if (!msg.selected || !msg.selected.length) { whisper("Sélectionne les tokens qui doivent voir ce butin."); return; }
  const charIds = [];
  msg.selected.forEach(function (sel) {
    const token = getObj("graphic", sel._id);
    const charId = token && token.get("represents");
    if (charId && charIds.indexOf(charId) === -1) { charIds.push(charId); }
  });
  if (!charIds.length) { whisper("Aucun des tokens sélectionnés ne représente un personnage."); return; }
  state.ARX_LOOT = { skin: skin, cells: {}, subscribers: charIds };
  arxLootRefresh();
  arxRefreshAdminLootFlag(true);
  whisper("Butin ouvert (" + skin + ") pour " + charIds.length + " personnage(s).");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxlootadd") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  const whisper = function (text) { sendChat("ARX", "/w gm " + text); };
  const itemId = msg.content.trim().split(/\s+/)[1];
  if (!itemId || !ARX_ITEMS[itemId]) { whisper("Item inconnu : " + (itemId || "(vide)")); return; }
  if (!state.ARX_LOOT.subscribers.length) { whisper("Aucun butin ouvert (!arxlootopen d'abord)."); return; }
  const loot = state.ARX_LOOT;
  const size = arxSizeOf(itemId);
  for (let a = 1; a <= ARX_LOOT_TOTAL; a++) {
    const cells = arxLootCellsFor(a, size.w, size.h);
    if (!cells) { continue; }
    const free = cells.every(function (c) { return !loot.cells[c]; });
    if (!free) { continue; }
    cells.forEach(function (c) { loot.cells[c] = (c === a) ? itemId : "#" + a; });
    arxLootRefresh();
    sendChat("ARX", "Ajouté au butin : " + ARX_ITEMS[itemId].label);
    return;
  }
  whisper("Butin plein (pas de place " + size.w + "x" + size.h + ") !");
});

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxlootclose") !== 0) { return; }
  if (!playerIsGM(msg.playerid)) { return; }
  state.ARX_LOOT.subscribers.forEach(function (charId) { arxSetAttr(charId, "loot_open", "0"); });
  state.ARX_LOOT = { skin: "chest", cells: {}, subscribers: [] };
  arxRefreshAdminLootFlag(false);
  sendChat("ARX", "/w gm Butin fermé.");
});

/* Take: NOT gated by playerIsGM — any player's own sheet fires this
   directly (see loot-panel.html.j2's take buttons). Resolves cell N's
   CURRENT contents from state.ARX_LOOT itself (the authoritative source,
   not the mirrored attribute), gives it to whichever token the clicking
   player has selected (their own, in the trusted-players model this was
   built for), clears it from the shared pool, and refreshes every
   subscriber so it disappears everywhere at once — a public message
   announces the pickup, since a shared loot pile is meant to be seen. */
on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxloottake") !== 0) { return; }
  if (!state.ARX_LOOT.subscribers.length) { return; }
  const cellArg = parseInt(msg.content.trim().split(/\s+/)[1], 10);
  if (!(cellArg >= 1 && cellArg <= ARX_LOOT_TOTAL)) { return; }
  const loot = state.ARX_LOOT;
  const raw = loot.cells[cellArg];
  if (!raw) { return; }
  const anchor = (String(raw).charAt(0) === "#") ? parseInt(String(raw).slice(1), 10) : cellArg;
  const itemId = loot.cells[anchor];
  if (!itemId || !ARX_ITEMS[itemId]) { return; }
  const charId = arxResolveCharacterForPlayer(msg);
  if (!charId) { arxWhisperTo(msg, "Impossible de savoir quel personnage récupère l'objet — sélectionne ton token."); return; }
  if (!arxGiveToCharacter(charId, itemId)) {
    arxWhisperTo(msg, "Sac plein, impossible de prendre : " + ARX_ITEMS[itemId].label);
    return;
  }
  Object.keys(loot.cells).forEach(function (k) {
    if (Number(k) === anchor || loot.cells[k] === "#" + anchor) { delete loot.cells[k]; }
  });
  arxLootRefresh();
  sendChat("ARX", ARX_ITEMS[itemId].label + " pris dans le butin.");
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
  arxSetAttr(charId, "fate", "");
  ARX_GM_MOD_STATS.forEach(function (stat) { arxSetAttr(charId, stat + "_gm_mod", "0"); });

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

/* !arxconsume — fired by the sheet's own "Consommer" button, never typed.
   It lives here rather than in a sheet worker for two reasons, both verified
   in game: a worker cannot emit a /me (startRoll only ever renders a roll
   template, which is why the scroll button could stay sheet-side), and Roll20
   does not fire clicked: for a type="roll" button, so the worker could not
   have removed the item either. Same shape as !arxloottake: player-triggered,
   no playerIsGM gate, character resolved from the token or from ownership.
   The verbs are duplicated from nothing — the sheet no longer holds a copy,
   this map is the only one. */
const ARX_CONSUME_VERBS = { food: "mange", drinks: "boit", potions: "consomme" };

on("chat:message", function (msg) {
  if (msg.type !== "api" || msg.content.indexOf("!arxconsume") !== 0) { return; }
  const charId = arxResolveCharacterForPlayer(msg);
  if (!charId) {
    arxWhisperTo(msg, "Impossible de savoir quel personnage consomme — sélectionne ton token.");
    return;
  }
  const itemId = arxGetAttr(charId, "hand");
  const item = ARX_ITEMS[itemId];
  const verb = item && ARX_CONSUME_VERBS[item.effect];
  if (!verb) { arxWhisperTo(msg, "Rien de consommable en main."); return; }

  /* Free the cells the item occupied. Held from the bag it owns a whole
     footprint (anchor + covered cells); held from an equip slot — no
     consumable is equippable today, but the sheet allows any slot to hand an
     item over — it is just that one slot. */
  const from = arxGetAttr(charId, "hand_from");
  if (from.indexOf("bag_") === 0) {
    const size = arxSizeOf(itemId);
    const cells = arxCellsFor(parseInt(from.slice(4), 10), size.w, size.h) || [from];
    cells.forEach(function (cell) { arxSetAttr(charId, cell, ""); });
  } else if (from) {
    arxSetAttr(charId, from, "");
  }
  ["hand", "hand_from", "hand_cat", "hand_effect", "hand_too_heavy", "fit"]
    .forEach(function (n) { arxSetAttr(charId, n, ""); });

  sendChat("character|" + charId, "/me " + verb + " : " + item.label);
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
    "!arxfavor — accorde la Faveur du Noden",
    "!arxtwist — inflige un Coups du sort",
    "!arxfateclear — retire le sort (faveur ou coup) du personnage",
    "!arxmod <stat> <valeur> — fixe un bonus/malus MJ sur les tokens sélectionnés (0 le retire)",
    "!arxclearmods — retire tous les bonus/malus MJ des tokens sélectionnés",
    "!arxunlockpanel — débloque le panel MJ sur ce personnage",
    "!arxlockpanel — reverrouille le panel MJ sur ce personnage",
    "!arxlootopen bag|body|chest|place|secured-chest — ouvre un butin partagé pour les tokens sélectionnés",
    "!arxlootadd <item_id> — ajoute un objet au butin ouvert",
    "!arxlootclose — ferme le butin partagé",
    "!arxloottake <case> — pas pour le MJ, déclenché par le bouton \"Prendre\" du joueur",
    "!arxconsume — pas pour le MJ, déclenché par le bouton \"Consommer\" du joueur",
    "!arxresetinventory — vide toutes les cases de sac + relâche la main",
    "!arxresetall — réinitialise tout le personnage (stats, inventaire, magie, carte, postures, or)",
    "!arxpreset <1-3> <spell_id> — définit un emplacement de sort mémorisé",
    "!arxpage <1-10> — change la page de sorts affichée",
    "!arxtab base|magic — change la page active de la fiche"
  ].join("<br>"));
});
