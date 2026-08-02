const ITEMS = {{ITEMS_JSON}};
const PRESETS = {{PRESETS_JSON}};
const SPELLS = {{SPELLS_JSON}};

const COLS = {{GRID_COLS}};
const ROWS = {{GRID_ROWS}};
const BAGS = {{GRID_BAGS}};
const PER_LEVEL = COLS * ROWS;
const BAG_SLOTS = [];
for (let i = 1; i <= PER_LEVEL * BAGS; i++) { BAG_SLOTS.push("bag_" + i); }

/* main_principale: main hand only (heavy/dominant-hand weapons).
   main_secondaire: off hand only (shields). ambidextrie: either hand —
   daggers, torches, grimoires, or anything else not tied to a specific
   hand (was called "arme_secondaire" before, a name that lied about it
   already working in both hands). deux_mains: greatswords, staves, bows —
   takes both hand slots at once (see the equip-target branch of
   clicked:slot_<slot> below), accepted by either slot so you can drop it
   on whichever hand happens to be free. */
const EQUIP_ACCEPTS = {
  equip_head: ["casque"],
  equip_torso: ["armure_haute"],
  equip_belt: ["armure_basse"],
  equip_main_hand: ["main_principale", "ambidextrie", "deux_mains"],
  equip_off_hand: ["ambidextrie", "main_secondaire", "deux_mains"],
  equip_jewel_1: ["bijoux"],
  equip_jewel_2: ["bijoux"]
};
const ALL_SLOTS = BAG_SLOTS.concat(Object.keys(EQUIP_ACCEPTS));

const SPELLBOOK_SLOTS = [];
for (let i = 1; i <= 20; i++) { SPELLBOOK_SLOTS.push("spellbook_" + i); }

/* Fixed spellbook slot per rune, by items.json's rune order (the book's own
   page order) — a rune always lands in the same slot no matter the order
   it's actually learned in. */
const RUNE_ORDER = Object.keys(ITEMS).filter(function (id) { return ITEMS[id].effect === "rune"; });
function spellbookSlotFor(runeId) {
  const idx = RUNE_ORDER.indexOf(runeId);
  return idx === -1 ? null : "spellbook_" + (idx + 1);
}

function sizeOf(itemId) {
  const s = (ITEMS[itemId] && ITEMS[itemId].size) || "1x1";
  const parts = s.split("x");
  return { w: parseInt(parts[0], 10) || 1, h: parseInt(parts[1], 10) || 1 };
}

/* Gold stacking: dropping a coin onto another coin merges their combined
   value like real change — greedily broken back down into the fewest coins
   among the denominations that actually exist in items.json (1 always
   exists, so every total is representable; nothing is ever invented) — see
   the bag-drop branch of clicked:slot_<slot>. */
function currencyValue(itemId) {
  const item = ITEMS[itemId];
  return item && item.effect === "currency" ? parseInt(item.value, 10) || 0 : null;
}
const CURRENCY_BY_VALUE = {};
Object.keys(ITEMS).forEach(function (id) {
  if (ITEMS[id].effect === "currency") { CURRENCY_BY_VALUE[ITEMS[id].value] = id; }
});
const CURRENCY_VALUES_DESC = Object.keys(CURRENCY_BY_VALUE).map(Number).sort(function (a, b) { return b - a; });
function decomposeCoins(total) {
  const result = [];
  let remaining = total;
  CURRENCY_VALUES_DESC.forEach(function (val) {
    while (remaining >= val) { result.push(CURRENCY_BY_VALUE[val]); remaining -= val; }
  });
  return result;
}

/* Cells covered by a footprint anchored at bag index (1-based); null if the
   rectangle leaves the anchor's level grid. Footprints never span levels. */
function cellsFor(anchorIndex, w, h) {
  const base = Math.floor((anchorIndex - 1) / PER_LEVEL) * PER_LEVEL;
  const idx = (anchorIndex - 1) % PER_LEVEL;
  const col = idx % COLS;
  const row = Math.floor(idx / COLS);
  if (col + w > COLS || row + h > ROWS) { return null; }
  const cells = [];
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) {
      cells.push("bag_" + (base + 1 + (row + r) * COLS + col + c));
    }
  }
  return cells;
}

function bagIndex(slot) { return parseInt(slot.slice(4), 10); }

const OTHER_HAND_SLOT = { equip_main_hand: "equip_off_hand", equip_off_hand: "equip_main_hand" };

/* Footprint of the item currently anchored at `anchor` ([] for other equip
   slots) — a "deux_mains" item occupies BOTH hand slots at once (see the
   equip-target branch below), so its footprint is the pair of them
   regardless of which one was actually clicked to equip it, mirroring how
   a multi-cell bag item's footprint always includes its own anchor cell. */
function ownCells(anchor, itemId) {
  if (anchor.indexOf("bag_") === 0) {
    return cellsFor(bagIndex(anchor), sizeOf(itemId).w, sizeOf(itemId).h) || [];
  }
  const item = ITEMS[itemId];
  if (item && item.cat === "deux_mains" && OTHER_HAND_SLOT[anchor]) {
    return ["equip_main_hand", "equip_off_hand"];
  }
  return [];
}

function equipAccepts(slot, itemId) {
  if (!itemId || !ITEMS[itemId]) { return false; }
  return (EQUIP_ACCEPTS[slot] || []).indexOf(ITEMS[itemId].cat) !== -1;
}

/* Optional "min_<attribute>" keys on any item.json entry (min_strength,
   min_mental, min_dexterity, min_constitution — any subset, all optional):
   the character can carry the item around freely (bag, purse, loot, GM
   give), but cannot put it ON while ANY of them is unmet. Compared against
   attr_<attribute> as displayed — gear bonuses already worn count — and only
   at the moment of the equip click: an item already equipped is never
   auto-removed if an attribute later drops. Note that an item sitting in
   hand is still equipped (the source slot is only cleared on drop), so its
   own bonuses still count while re-equipping it; once stored in the bag
   those bonuses are gone, and it may become unwearable. */
const MIN_STATS = ["strength", "mental", "dexterity", "constitution"];

function tooHeavy(v, itemId) {
  const item = ITEMS[itemId];
  if (!item) { return false; }
  return MIN_STATS.some(function (stat) {
    const min = Number(item["min_" + stat]) || 0;
    return min > 0 && (parseInt(v[stat], 10) || 0) < min;
  });
}

function bagCount(v) {
  const n = parseInt(v.bag_count, 10);
  return (n >= 1 && n <= BAGS) ? n : 1;
}

/* All valid bag anchors for `itemId` across UNLOCKED levels, `own` cells free. */
function fitMask(v, itemId, own) {
  const size = sizeOf(itemId);
  const fits = [];
  const limit = PER_LEVEL * bagCount(v);
  for (let a = 1; a <= limit; a++) {
    const cells = cellsFor(a, size.w, size.h);
    if (!cells) { continue; }
    let free = true;
    for (let k = 0; k < cells.length; k++) {
      const val = v[cells[k]] || "";
      if (val !== "" && own.indexOf(cells[k]) === -1) { free = false; break; }
    }
    if (free) { fits.push("bag_" + a); }
  }
  return fits.length ? "|" + fits.join("|") + "|" : "";
}

ALL_SLOTS.forEach(function (slot) {
  on("clicked:slot_" + slot, function () {
    getAttrs(ALL_SLOTS.concat(["hand", "hand_from", "bag_count"]).concat(MIN_STATS), function (v) {
      const hand = v.hand || "";
      const from = v.hand_from || "";
      const here = v[slot] || "";

      if (!hand) {
        if (here === "") { return; }
        /* Covered cell (#anchor) redirects to the whole item. */
        const anchor = here.charAt(0) === "#" ? here.slice(1) : slot;
        const item = v[anchor] || "";
        if (!ITEMS[item]) { return; }
        setAttrs({
          hand: item,
          hand_from: anchor,
          hand_cat: ITEMS[item].cat,
          hand_effect: ITEMS[item].effect || "",
          /* Mirrored for CSS only: turns the equip-slot glow red instead of
             gold, so the refusal below is visible BEFORE the click. Never
             needs clearing — every glow rule also keys off attr_hand_cat,
             which is reset with the hand, and each pickup rewrites it. */
          hand_too_heavy: tooHeavy(v, item) ? "1" : "",
          fit: fitMask(v, item, ownCells(anchor, item))
        });
        return;
      }

      /* Cancel: click the origin anchor or any of its covered cells. */
      if (slot === from || here === "#" + from) {
        setAttrs({ hand: "", hand_from: "", hand_cat: "", hand_effect: "", fit: "" });
        return;
      }

      const clear = { hand: "", hand_from: "", hand_cat: "", hand_effect: "", fit: "" };
      const own = ownCells(from, hand);
      /* The item leaving `from` was a two-handed weapon occupying both hand
         slots — reset the primary marker regardless of where it's headed
         (bag or a fresh equip target, which sets its own value right back
         if it's still two-handed there). */
      if (own.indexOf("equip_main_hand") !== -1 && own.indexOf("equip_off_hand") !== -1) {
        clear.two_handed_primary = "";
      }

      if (slot.indexOf("bag_") === 0) {
        if (bagIndex(slot) > PER_LEVEL * bagCount(v)) { return; } /* locked level */

        /* Gold stacking: coin dropped onto coin, combined value broken back
           down into the fewest coins (see decomposeCoins). The target slot
           and the coin's own freed cell absorb the first two results;
           anything beyond that needs extra free bag cells — reject the
           whole merge (nothing consumed) if there isn't enough room. */
        const handValue = currencyValue(hand);
        const targetValue = currencyValue(here);
        if (handValue !== null && targetValue !== null) {
          const coins = decomposeCoins(handValue + targetValue);
          const placements = [slot].concat(own);
          if (coins.length > placements.length) {
            const limit = PER_LEVEL * bagCount(v);
            for (let a = 1; a <= limit && placements.length < coins.length; a++) {
              const s = "bag_" + a;
              if (!v[s] && placements.indexOf(s) === -1) { placements.push(s); }
            }
            if (placements.length < coins.length) { return; } /* not enough room */
          }
          own.forEach(function (c) { clear[c] = ""; });
          if (own.length === 0) { clear[from] = ""; } /* origin was an equip slot */
          coins.forEach(function (id, i) { clear[placements[i]] = id; });
          setAttrs(clear);
          return;
        }

        const size = sizeOf(hand);
        const cells = cellsFor(bagIndex(slot), size.w, size.h);
        if (!cells) { return; }
        for (let k = 0; k < cells.length; k++) {
          const val = v[cells[k]] || "";
          if (val !== "" && own.indexOf(cells[k]) === -1) { return; }
        }
        own.forEach(function (c) { clear[c] = ""; });
        if (own.length === 0) { clear[from] = ""; } /* origin was an equip slot */
        cells.forEach(function (c) { clear[c] = "#" + slot; });
        clear[slot] = hand;
        setAttrs(clear);
        return;
      }

      /* Equipment target: category match + empty slot (no swap). A
         "deux_mains" item also needs its OTHER hand free — it occupies
         both slots with the same real item id (so the existing icon-
         reveal rule "just works" on both, no per-item CSS needed), marking
         which one was actually clicked via attr_two_handed_primary so the
         other can be dimmed (see inventory-slots.css.j2). */
      if (!equipAccepts(slot, hand) || here !== "") { return; }
      if (tooHeavy(v, hand)) { return; }
      const item = ITEMS[hand];
      const otherHand = OTHER_HAND_SLOT[slot];
      const isTwoHanded = item.cat === "deux_mains" && otherHand;
      if (isTwoHanded && (v[otherHand] || "") !== "") { return; }
      own.forEach(function (c) { clear[c] = ""; });
      if (own.length === 0) { clear[from] = ""; }
      clear[slot] = hand;
      if (isTwoHanded) {
        clear[otherHand] = hand;
        clear.two_handed_primary = slot;
      }
      setAttrs(clear);
    });
  });
});

/* The pouch: consuming an "extra_bag" item there unlocks the next level. */
on("clicked:slot_pouch", function () {
  getAttrs(["hand", "hand_from", "bag_count"], function (v) {
    const hand = v.hand || "";
    const item = ITEMS[hand];
    if (!item || item.effect !== "extra_bag") { return; }
    const count = parseInt(v.bag_count, 10) || 1;
    if (count >= BAGS) { return; }
    const update = { hand: "", hand_from: "", hand_cat: "", hand_effect: "", fit: "",
                     bag_count: count + 1 };
    ownCells(v.hand_from || "", hand).forEach(function (c) { update[c] = ""; });
    if ((v.hand_from || "").indexOf("equip_") === 0) { update[v.hand_from] = ""; }
    setAttrs(update);
  });
});

/* The purse: with a currency item in hand, consuming it adds its value to
   attr_gold. With an empty hand, withdraws one "gold-one" coin into the first
   free bag cell (so it can be carried, moved, or handed to another player). */
on("clicked:slot_purse", function () {
  getAttrs(BAG_SLOTS.concat(["hand", "hand_from", "gold", "bag_count"]), function (v) {
    const hand = v.hand || "";

    if (hand) {
      const item = ITEMS[hand];
      if (!item || item.effect !== "currency") { return; }
      const gold = (parseInt(v.gold, 10) || 0) + (parseInt(item.value, 10) || 0);
      const update = { hand: "", hand_from: "", hand_cat: "", hand_effect: "", fit: "", gold: gold };
      ownCells(v.hand_from || "", hand).forEach(function (c) { update[c] = ""; });
      setAttrs(update);
      return;
    }

    const gold = parseInt(v.gold, 10) || 0;
    if (gold < 1) { return; }
    const limit = PER_LEVEL * bagCount(v);
    for (let a = 1; a <= limit; a++) {
      const slot = "bag_" + a;
      if (!v[slot]) {
        const update = { gold: gold - 1 };
        update[slot] = "gold-one";
        setAttrs(update);
        return;
      }
    }
  });
});

/* Trash: while holding an item, clicking the red cross deletes it outright
   (frees its footprint, nothing placed anywhere). */
on("clicked:trash", function () {
  getAttrs(["hand", "hand_from"], function (v) {
    const hand = v.hand || "";
    const from = v.hand_from || "";
    if (!hand) { return; }
    const clear = { hand: "", hand_from: "", hand_cat: "", hand_effect: "", fit: "" };
    const own = ownCells(from, hand);
    own.forEach(function (c) { clear[c] = ""; });
    if (own.length === 0) { clear[from] = ""; }
    setAttrs(clear);
  });
});

/* A rune id is always "rune-<suffix>" (see items.json); the matching known-
   flag attribute is "known_<suffix>" — computed, never a stored mapping, so
   adding a rune never needs a second catalog touched. */
function knownFlag(runeId) { return "known_" + runeId.slice(5); }

/* The grimoire: consuming a "rune" item there learns it permanently — placed
   in that rune's own fixed slot (see spellbookSlotFor), never freed again,
   no un-learning — and its known_<rune> flag is set so spells requiring it
   become visible (see magic-slots.css.j2). Each rune can only be learned
   once: an already-known rune is refused (stays in hand). */
on("clicked:slot_grimoire", function () {
  getAttrs(["hand", "hand_from"], function (v) {
    const hand = v.hand || "";
    const item = ITEMS[hand];
    if (!item || item.effect !== "rune") { return; }
    const slot = spellbookSlotFor(hand);
    if (!slot) { return; }
    getAttrs([knownFlag(hand)], function (v2) {
      if (v2[knownFlag(hand)] === "1") { return; }
      const update = { hand: "", hand_from: "", hand_cat: "", hand_effect: "", fit: "" };
      update[slot] = hand;
      update[knownFlag(hand)] = "1";
      ownCells(v.hand_from || "", hand).forEach(function (c) { update[c] = ""; });
      setAttrs(update);
    });
  });
});

/* Reading a scroll (items.json's scroll-* entries, effect "scroll"): 1d100
   roll-under against the scroll's OWN fixed spell_casting and caster_level
   — never the player's live @{casting}/@{caster_level} (wiki.arx-libertatis.
   org/Caster_level: "Precast spells from reading scrolls always have a
   fixed caster level") — labeled with its spell_label, then the scroll is
   consumed (it's one-shot, same as a memorized preset). */
on("clicked:read_scroll", function () {
  getAttrs(["hand", "hand_from"], function (v) {
    const hand = v.hand || "";
    const item = ITEMS[hand];
    if (!item || item.effect !== "scroll") { return; }
    startRoll("&{template:default} {{name=" + item.spell_label + "}} {{Valeur=" + item.spell_casting + "}} {{Niveau Magique=" + item.caster_level + "}} {{Jet=[[1d100]]}}",
      function (results) { finishRoll(results.rollId, {}); });
    const update = { hand: "", hand_from: "", hand_cat: "", hand_effect: "", fit: "" };
    ownCells(v.hand_from || "", hand).forEach(function (c) { update[c] = ""; });
    setAttrs(update);
  });
});

/* Map card slot: consuming a "carte-niveau-N" item (items.json, effect
   "map_card") permanently unlocks that level's tab (attr_known_map_N) —
   same one-time-consume pattern as the grimoire's runes, just without a
   per-level fixed slot (the card is simply gone once used). */
on("clicked:map_card_slot", function () {
  getAttrs(["hand", "hand_from"], function (v) {
    const hand = v.hand || "";
    const item = ITEMS[hand];
    if (!item || item.effect !== "map_card") { return; }
    const flag = "known_map_" + item.level;
    getAttrs([flag], function (v2) {
      if (v2[flag] === "1") { return; }
      const update = { hand: "", hand_from: "", hand_cat: "", hand_effect: "", fit: "" };
      update[flag] = "1";
      ownCells(v.hand_from || "", hand).forEach(function (c) { update[c] = ""; });
      setAttrs(update);
    });
  });
});

/* Level navigation: up = toward bag 1, down = deeper (within unlocked levels). */
on("clicked:bag_up", function () {
  getAttrs(["bag_level"], function (v) {
    const lvl = parseInt(v.bag_level, 10) || 1;
    if (lvl > 1) { setAttrs({ bag_level: lvl - 1 }); }
  });
});
on("clicked:bag_down", function () {
  getAttrs(["bag_level", "bag_count"], function (v) {
    const lvl = parseInt(v.bag_level, 10) || 1;
    const count = parseInt(v.bag_count, 10) || 1;
    if (lvl < count) { setAttrs({ bag_level: lvl + 1 }); }
  });
});

/* GM admin panel: same open/close + page-nav pattern as the bag toggle and
   its level nav above — see gm-panel.css.j2/gm-panel.html.j2. Giving an
   item is NOT handled here: each slot's own button fires "!arxgive <id>"
   straight to chat (see gm-panel.html.j2), reusing arx-mod.js's existing
   command unchanged. */
const GM_PANEL_COLS = 3, GM_PANEL_ROWS = 11;
const GM_PANEL_PAGES = Math.ceil(Object.keys(ITEMS).length / (GM_PANEL_COLS * GM_PANEL_ROWS));

on("clicked:gm_panel_toggle", function () {
  getAttrs(["gm_panel_open"], function (v) {
    setAttrs({ gm_panel_open: v.gm_panel_open === "1" ? "0" : "1" });
  });
});
on("clicked:gm_panel_page_up", function () {
  getAttrs(["gm_panel_page"], function (v) {
    const page = parseInt(v.gm_panel_page, 10) || 1;
    if (page > 1) { setAttrs({ gm_panel_page: page - 1 }); }
  });
});
on("clicked:gm_panel_page_down", function () {
  getAttrs(["gm_panel_page"], function (v) {
    const page = parseInt(v.gm_panel_page, 10) || 1;
    if (page < GM_PANEL_PAGES) { setAttrs({ gm_panel_page: page + 1 }); }
  });
});

/* Accent-insensitive match: French labels are full of accents (Épée,
   Résistance...), a GM searching "epee" should still find "Épée" — strips
   combining diacritics after NFD-normalizing, so é/è/ê/ë all fold to e. */
function gmPanelFold(s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }

/* Search: glows EVERY item whose id or label contains the typed text
   (accent- and case-insensitive), dims every other item, and jumps to the
   first match's page so at least one result is immediately visible — a
   sheet worker can't physically regroup/hide grid cells (no DOM access
   outside CSS :has() rules), so this is the closest thing to a live filter:
   every match stays lit across every page, not just the first one. Fires
   on both a click AND a plain change (Enter or blur commits the text field
   the same way). Item order = items.json's own order, same as everywhere
   else it's relied on this session. */
const GM_PANEL_ITEM_IDS = Object.keys(ITEMS);
on("clicked:gm_panel_search change:gm_panel_search", function () {
  getAttrs(["gm_panel_search"], function (v) {
    const term = gmPanelFold((v.gm_panel_search || "").trim());
    if (!term) { setAttrs({ gm_panel_filter: "" }); return; }
    const matches = GM_PANEL_ITEM_IDS.filter(function (id) {
      return gmPanelFold(id).indexOf(term) !== -1 || gmPanelFold(ITEMS[id].label).indexOf(term) !== -1;
    });
    if (!matches.length) { setAttrs({ gm_panel_filter: "" }); return; }
    const idx = GM_PANEL_ITEM_IDS.indexOf(matches[0]);
    const page = Math.floor(idx / (GM_PANEL_COLS * GM_PANEL_ROWS)) + 1;
    setAttrs({ gm_panel_page: page, gm_panel_filter: "|" + matches.join("|") + "|" });
  });
});

/* Page navigation (base <-> magic) and the inventory band toggle: buttons +
   this worker, not a radio/checkbox styled with CSS-only tricks — Roll20
   discourages label[for]/input[id] pairing (multiple sheet copies can be in
   the DOM at once), so this is the same button+worker mechanism already used
   for every other interactive element on the sheet (grimoire, trash, purse,
   bag nav). CSS reads the resulting attribute value directly (see tabs.css,
   inventory.css). */
on("clicked:goto_magic", function () { setAttrs({ sheet_tab: "magic" }); });
/* Leaving the magic page hides it via display:none, which fully resets any
   CSS animation running on it — attr_recipe_spell staying set is what made
   the recipe-reveal replay from scratch every time you come back (same
   root cause as sheet:opened, different trigger: a tab switch, not a full
   sheet reopen). Cleared on EVERY route away from magic (base/notes/map),
   not just goto_base — the magic page gets hidden the same way regardless
   of which page you land on next. */
on("clicked:goto_base", function () { setAttrs({ sheet_tab: "base", recipe_spell: "" }); });
/* Notes: reachable from both base and magic (map-menu-button shows on
   both), leaving always goes back to base (single "back" ribbon, same one
   magic already uses). */
on("clicked:goto_notes", function () { setAttrs({ sheet_tab: "notes", recipe_spell: "" }); });

/* Map: the ribbon is rendered on every page anyway (see tabs.css's 3-slot
   assignment table). */
on("clicked:goto_map", function () { setAttrs({ sheet_tab: "map", recipe_spell: "" }); });

/* Map levels: 8 always-reachable tabs (no rune-known gating, unlike the
   grimoire's spell pages) — see clicked:goto_maplevel_N and map.css.j2. */
for (let i = 1; i <= 8; i++) {
  on("clicked:goto_maplevel_" + i, function () { setAttrs({ map_level: i }); });
}

on("clicked:inventory_toggle", function () {
  getAttrs(["inventory_open"], function (v) {
    setAttrs({ inventory_open: v.inventory_open === "1" ? "0" : "1" });
  });
});

/* Spell-page navigation (1-10): same button+worker mechanism, same reason
   (no radio/label id/for). */
for (let p = 1; p <= 10; p++) {
  on("clicked:goto_spellpage_" + p, function () { setAttrs({ spell_page: p }); });
}

/* Rune-craft: click learned runes (in the 20-slot spellbook grid) in order to
   build a combination, then Validate to match it against presets.json (which
   already covers every book spell plus the secret-only ones) and auto-fill
   the first empty preset slot. Stored delimited ("|rune-a|rune-b|", like
   fitMask's own list attribute) so CSS can highlight a rune with a substring
   selector without one rune's id colliding with another's prefix. */
const CRAFT_MAX = 5;
function craftList(v) { return (v.craft_runes || "").split("|").filter(Boolean); }
function craftJoin(list) { return list.length ? "|" + list.join("|") + "|" : ""; }
/* attr_craft_pos_1..CRAFT_MAX mirror the combo so CSS can show each rune's
   own inventory icon in a fixed-position strip (see
   magic.html.j2/magic-slots.css.j2) — attr_craft_runes alone can't drive an
   ORDERED display since CSS has no way to index into a delimited string.
   Indexed from the END of the list: pos_1 is always the MOST RECENTLY
   clicked rune (the strip's corner slot), so each new click bumps every
   earlier rune outward by one slot rather than staying put. */
function craftPositions(list) {
  const update = {};
  for (let i = 1; i <= CRAFT_MAX; i++) { update["craft_pos_" + i] = list[list.length - i] || ""; }
  return update;
}

for (let i = 1; i <= 20; i++) {
  on("clicked:craft_rune_" + i, function () {
    const slotAttr = "spellbook_" + i;
    getAttrs([slotAttr, "craft_runes"], function (v) {
      const rune = v[slotAttr];
      if (!rune) { return; }
      const list = craftList(v);
      if (list.length >= CRAFT_MAX) { return; }
      list.push(rune);
      const update = craftPositions(list);
      update.craft_runes = craftJoin(list);
      update.forget_mode = "0"; /* crafting cancels a pending "forget a preset" */
      setAttrs(update);
    });
  });
}

/* Launch: matches the crafted rune combination (order matters — see
   clicked:memorize) against spells.json and, on a match, rolls 1d100
   roll-under against Magie/casting labeled with the spell's own translated
   name. Consumes the combo either way, matched or not. */
on("clicked:craft_confirm", function () {
  getAttrs(["craft_runes"], function (v) {
    const combo = craftList(v);
    if (!combo.length) { return; }
    const comboKey = combo.join("|");
    let matchId = null;
    Object.keys(SPELLS).forEach(function (id) {
      if (matchId) { return; }
      if (SPELLS[id].runes.join("|") === comboKey) { matchId = id; }
    });
    if (matchId) {
      const label = SPELLS[matchId].label;
      startRoll("&{template:default} {{name=" + label + "}} {{Valeur=@{casting}}} {{Niveau Magique=@{caster_level}}} {{Jet=[[1d100]]}}",
        function (results) { finishRoll(results.rollId, {}); });
    }
    const update = craftPositions([]);
    update.craft_runes = "";
    update.forget_mode = "0";
    setAttrs(update);
  });
});

/* Reset clears an in-progress combo; with nothing crafted yet, it instead
   toggles "forget a preset" mode (see clicked:preset_N below). */
on("clicked:craft_reset", function () {
  getAttrs(["craft_runes", "forget_mode"], function (v) {
    if (craftList(v).length) {
      const update = craftPositions([]);
      update.craft_runes = "";
      setAttrs(update);
      return;
    }
    setAttrs({ forget_mode: v.forget_mode === "1" ? "0" : "1" });
  });
});

/* Clicking a memorized preset: while forget_mode is on it forgets it (see
   magic-slots.css.j2 for the delete cursor shown over the preset slots) —
   forgetting is NEVER gated by anything else. Otherwise, a filled slot
   CASTS that spell (1d100 roll-under against Magie/casting, explicitly
   labeled "sort mémorisé" to distinguish it from casting straight from the
   book) and is consumed — a memorized spell is one-shot, the slot empties
   right after. */
[1, 2, 3].forEach(function (n) {
  on("clicked:preset_" + n, function () {
    getAttrs(["forget_mode", "preset_slot_" + n], function (v) {
      if (v.forget_mode === "1") {
        const update = { forget_mode: "0" };
        update["preset_slot_" + n] = "";
        setAttrs(update);
        return;
      }
      const presetId = v["preset_slot_" + n];
      if (!presetId || !PRESETS[presetId]) { return; }
      const label = PRESETS[presetId].label;
      startRoll("&{template:default} {{name=Sort mémorisé : " + label + "}} {{Valeur=@{casting}}} {{Niveau Magique=@{caster_level}}} {{Jet=[[1d100]]}}",
        function (results) { finishRoll(results.rollId, {}); });
      const update = {};
      update["preset_slot_" + n] = "";
      setAttrs(update);
    });
  });
});

/* Clicking a spell in the 2x2 slots only highlights its rune recipe in the
   20-slot grid (see magic-slots.css.j2's attr_recipe_spell rules); clicking
   the SAME spell again clears it. Casting itself only happens by incanting
   those runes and clicking "Lancer un sort" (see clicked:craft_confirm). */
Object.keys(SPELLS).forEach(function (spellId) {
  on("clicked:cast_" + spellId, function () {
    getAttrs(["recipe_spell"], function (v) {
      setAttrs({ recipe_spell: v.recipe_spell === spellId ? "" : spellId });
    });
  });
});

/* Damages: needs the equipped weapon's own label (an item lookup, which a
   static roll button's value="" can't do) — main hand, plus " + <off-hand>"
   if the off hand holds an "ambidextrie" item (dagger, etc — not a shield).
   NOTE: "ambidextrie" also covers non-weapon utility items (torch, grimoire)
   by design — none exist in items.json yet, but once one does, this will
   need a real "is this actually a weapon" check instead of just the cat. */
on("clicked:roll_damages", function () {
  getAttrs(["equip_main_hand", "equip_off_hand", "posture", "damages"], function (v) {
    const mainItem = ITEMS[v.equip_main_hand];
    const offItem = ITEMS[v.equip_off_hand];
    let weaponLabel = mainItem ? mainItem.label : "Mains nues";
    if (offItem && offItem.cat === "ambidextrie") { weaponLabel += " + " + offItem.label; }
    const offensive = v.posture === "offensive";
    /* Normally 1d<damages> (e.g. 15 damages -> 1d15); Offensive skips the
       die and just deals the flat value — its actual "always max damage"
       effect, now that damage is a real range. damages<1 also skips the
       die (1d0 is invalid) and just shows 0. */
    const damages = parseInt(v.damages, 10) || 0;
    const valeur = (offensive || damages < 1) ? "[[@{damages}]]" : "[[1d@{damages}]]";
    if (offensive) { weaponLabel += " (Offensive)"; }
    startRoll("&{template:default} {{name=Dégâts — " + weaponLabel + "}} {{Valeur=" + valeur + "}}",
      function (results) { finishRoll(results.rollId, {}); });
  });
});

/* attr_recipe_spell is a normal (persisted) attribute — left set from a
   previous session, the reveal animation plays again the moment the sheet
   re-renders on open, since CSS animations trigger whenever the matching
   condition becomes true, not just on an actual change. It's a purely
   transient "what am I looking at" indicator, so just clear it on open. */
on("sheet:opened", function () { setAttrs({ recipe_spell: "" }); });

/* Memorize: matches the crafted rune combination against presets.json (which
   covers both book spells and secret-only ones) and fills the first empty
   preset slot on an exact match — consumes the combo either way. */
on("clicked:memorize", function () {
  getAttrs(["craft_runes", "preset_slot_1", "preset_slot_2", "preset_slot_3"], function (v) {
    const combo = craftList(v);
    if (!combo.length) { return; }
    /* Order matters: some recipes would otherwise be indistinguishable from
       another using the exact same runes in a different sequence. */
    const comboKey = combo.join("|");
    let matchId = null;
    Object.keys(PRESETS).forEach(function (id) {
      if (matchId) { return; }
      if (PRESETS[id].runes.join("|") === comboKey) { matchId = id; }
    });
    const update = craftPositions([]);
    update.craft_runes = "";
    update.forget_mode = "0";
    if (matchId) {
      for (let n = 1; n <= 3; n++) {
        if (!v["preset_slot_" + n]) { update["preset_slot_" + n] = matchId; break; }
      }
    }
    setAttrs(update);
  });
});

/* Equipment modifiers: any item.json entry MAY carry any of these stat keys
   (optional, exactly like "legendary" — present means "apply this", absent
   means no effect, never a 0/false default baked into every item).
   Single visible/editable attr_<stat> — no separate base field — stays
   correct across manual edits (leveling, point-buy) by applying only the
   DELTA between the old and new equipment bonus, never a full recompute
   from a fixed default:
     new visible = current visible + (new equip total − previously applied)
   attr_<stat>_applied_mod (hidden) remembers what was last baked in, so a
   manual edit made between two equipment changes is never overwritten —
   only the change in gear bonus is layered on top of whatever is there. */
const MOD_STATS = [
  "strength", "mental", "dexterity", "constitution",
  "stealth", "technical", "intuition", "ethereal_link", "object_knowledge", "casting",
  "close_combat", "projectile", "defense",
  "armor_class", "magic_resistance", "poison_resistance", "damages",
  "health_max", "mana_max"
];
const EQUIP_SLOTS_FOR_MODS = Object.keys(EQUIP_ACCEPTS);

function recomputeModifiers(v) {
  const newTotals = {};
  MOD_STATS.forEach(function (stat) { newTotals[stat] = 0; });
  /* A "deux_mains" weapon's real item id sits in BOTH equip_main_hand and
     equip_off_hand (see the equip-target branch of clicked:slot_<slot>) —
     purely so the off-hand slot shows a dimmed mirror icon, not a second
     copy of the item. Counting it from equip_off_hand too would double
     its stat bonuses, so skip that slot whenever it's just mirroring the
     two-handed weapon already counted from equip_main_hand. */
  const twoHandedMain = ITEMS[v.equip_main_hand] && ITEMS[v.equip_main_hand].cat === "deux_mains";
  EQUIP_SLOTS_FOR_MODS.forEach(function (slot) {
    if (slot === "equip_off_hand" && twoHandedMain && v.equip_off_hand === v.equip_main_hand) { return; }
    const item = ITEMS[v[slot]];
    if (!item) { return; }
    MOD_STATS.forEach(function (stat) {
      if (item[stat] !== undefined) { newTotals[stat] += Number(item[stat]); }
    });
  });
  const update = {};
  MOD_STATS.forEach(function (stat) {
    const prevApplied = parseInt(v[stat + "_applied_mod"], 10) || 0;
    const current = parseInt(v[stat], 10) || 0;
    const delta = newTotals[stat] - prevApplied;
    if (delta !== 0) { update[stat] = current + delta; }
    update[stat + "_applied_mod"] = newTotals[stat];
  });
  setAttrs(update);
}

on("change:equip_head change:equip_torso change:equip_belt change:equip_main_hand change:equip_off_hand change:equip_jewel_1 change:equip_jewel_2",
  function () { getAttrs(EQUIP_SLOTS_FOR_MODS.concat(MOD_STATS).concat(MOD_STATS.map(function (s) { return s + "_applied_mod"; })), recomputeModifiers); });

/* Also recompute on load: gear equipped before this system existed (or set
   by the GM directly) never fires a change: event, so the bonus would never
   get baked in until the player re-equips something. */
on("sheet:opened", function () { getAttrs(EQUIP_SLOTS_FOR_MODS.concat(MOD_STATS).concat(MOD_STATS.map(function (s) { return s + "_applied_mod"; })), recomputeModifiers); });

/* If a gauge's max drops below its current value (e.g. unequipping
   something that was boosting health_max/mana_max), clamp current down to
   the new max instead of leaving it stranded above the ceiling. */
["health", "mana"].forEach(function (name) {
  on("change:" + name + "_max", function () {
    getAttrs([name, name + "_max"], function (v) {
      const current = parseInt(v[name], 10) || 0;
      const max = parseInt(v[name + "_max"], 10) || 0;
      if (current > max) {
        const update = {};
        update[name] = max;
        setAttrs(update);
      }
    });
  });
});

/* Arx Fatalis skill formulas (wiki.arx-libertatis.org/Skills): each skill's
   value is boosted by the character's attributes. Same delta technique as
   equipment mods, tracked separately (attr_<skill>_applied_stat_mod) so
   items and attributes never clobber each other's contribution — and so
   this NEVER touches attr_<skill>_applied_mod, keeping the equipment-only
   color tint (see base.css.j2) blind to attribute-driven changes, as
   requested. Coefficients are the game's own, unscaled. */
const SKILL_FORMULAS = {
  stealth: function (a) { return a.dexterity * 2; },
  technical: function (a) { return a.dexterity + a.mental; },
  intuition: function (a) { return a.mental * 2; },
  ethereal_link: function (a) { return a.mental * 2; },
  object_knowledge: function (a) { return Math.round(a.strength * 0.5 + a.dexterity * 0.5 + a.mental * 1.5); },
  casting: function (a) { return a.mental * 2; },
  close_combat: function (a) { return a.strength * 2 + a.dexterity; },
  projectile: function (a) { return a.dexterity * 2 + a.strength; },
  defense: function (a) { return a.constitution * 3; }
};
const SKILL_NAMES = Object.keys(SKILL_FORMULAS);
const ATTR_NAMES = ["strength", "mental", "dexterity", "constitution"];

function recomputeStatMods(v) {
  const a = {};
  ATTR_NAMES.forEach(function (attr) { a[attr] = parseInt(v[attr], 10) || 0; });
  const update = {};
  SKILL_NAMES.forEach(function (skill) {
    const newTotal = SKILL_FORMULAS[skill](a);
    const prevApplied = parseInt(v[skill + "_applied_stat_mod"], 10) || 0;
    const current = parseInt(v[skill], 10) || 0;
    const delta = newTotal - prevApplied;
    if (delta !== 0) { update[skill] = current + delta; }
    update[skill + "_applied_stat_mod"] = newTotal;
  });
  setAttrs(update);
}

const STAT_MOD_GETATTRS = ATTR_NAMES.concat(SKILL_NAMES).concat(SKILL_NAMES.map(function (s) { return s + "_applied_stat_mod"; }));

on("change:strength change:mental change:dexterity change:constitution",
  function () { getAttrs(STAT_MOD_GETATTRS, recomputeStatMods); });

/* Also on load: attributes leveled up in an earlier session (before this
   system existed) never fired a change: event for the affected skills. */
on("sheet:opened", function () { getAttrs(STAT_MOD_GETATTRS, recomputeStatMods); });

/* ============================================================================
   Hard caps: attributes 24, level 10, skills 125. A dedicated change:
   listener per field, same pattern as the health/mana "clamp current to
   max" rule above — it runs AFTER whatever just wrote the value (manual
   edit, equipment mod, or attribute-derived skill bonus), so it always
   sees the latest total.
   The attribute and level caps do NOT apply to a GM character (see
   forceGmStats below): its 600s and its level 200 are deliberate, and
   clamping them back down would fight the forcing on every load. The skill
   cap stays in force for everyone — the skills keep their ordinary formula
   here, so with 600 in every attribute they all simply land on 125. */
ATTR_NAMES.forEach(function (attr) {
  on("change:" + attr, function () {
    getAttrs([attr, "gm_panel_unlocked"], function (v) {
      if (v.gm_panel_unlocked === "1") { return; }
      if ((parseInt(v[attr], 10) || 0) > 24) {
        const update = {};
        update[attr] = 24;
        setAttrs(update);
      }
    });
  });
});

on("change:level", function () {
  getAttrs(["level", "gm_panel_unlocked"], function (v) {
    if (v.gm_panel_unlocked === "1") { return; }
    if ((parseInt(v.level, 10) || 0) > 10) { setAttrs({ level: 10 }); }
  });
});

SKILL_NAMES.forEach(function (skill) {
  on("change:" + skill, function () {
    getAttrs([skill], function (v) {
      if ((parseInt(v[skill], 10) || 0) > 125) {
        const update = {};
        update[skill] = 125;
        setAttrs(update);
      }
    });
  });
});

/* Character name field is a fixed-width box (base.css.j2) — long names
   would otherwise overflow it at the default font size. attr_character_
   name_size buckets the name's length into a handful of steps (see the
   matching font-size rules in base.css.j2); short names stay at full
   size, longer ones shrink just enough to keep fitting. */
on("change:character_name", function () {
  getAttrs(["character_name"], function (v) {
    const length = (v.character_name || "").length;
    let size;
    if (length <= 12) { size = "normal"; }
    else if (length <= 16) { size = "long"; }
    else if (length <= 20) { size = "longer"; }
    else if (length <= 25) { size = "longest"; }
    else { size = "tiny"; }
    setAttrs({ character_name_size: size });
  });
});

/* ============================================================================
   SEPARATE, REMOVABLE BLOCK — attribute/skill-derived bonuses to things that
   are NOT skills themselves (damages, armor class, poison/magic resistance),
   straight from wiki.arx-libertatis.org/Stats's "Other stats" formulas
   (dropping the modrel/modspell/cheats terms: no percentage-based item
   bonuses or spell buffs exist in this sheet, only the flat modabs ones
   already handled by recomputeModifiers/MOD_STATS above). Kept fully
   isolated from SKILL_FORMULAS/recomputeStatMods on purpose — different
   constants, different applied_stat_mod trackers, different listener — so
   this whole mechanic can be deleted later without touching the skill math
   at all.

   All four below are the wiki's real formulas (dropping cheats). damages
   and armor_class/poison_resistance are floor/round of a sum that already
   includes its own inner max(1, ...) or max(0, ...) term (per the wiki),
   so each lands exactly on this sheet's own default at level 0 /
   attributes-and-skills at their starting values — no jump on a fresh
   character (same reasoning as GAUGE_MAX_FORMULAS below). damages is
   rounded rather than floored (matches this sheet's own default of 3;
   floor would give 2) since the wiki doesn't specify either way. ======== */
const SINGLE_STAT_FORMULAS = {
  damages: function (a) { return Math.round(Math.max(1, a.strength / 2 - 5) + a.close_combat / 10); },
  armor_class: function (a) { return Math.max(1, Math.floor(a.defense / 10 - 1)); },
  magic_resistance: function (a) { return Math.floor(a.mental * (2 + a.casting / 100)); },
  poison_resistance: function (a) { return Math.floor(a.constitution * 2 + a.defense / 4); }
};
const SINGLE_STAT_NAMES = Object.keys(SINGLE_STAT_FORMULAS);
const SINGLE_STAT_SKILL_INPUTS = ["defense", "casting", "close_combat"];

function recomputeSingleStatMods(v) {
  const a = {};
  ATTR_NAMES.forEach(function (attr) { a[attr] = parseInt(v[attr], 10) || 0; });
  SINGLE_STAT_SKILL_INPUTS.forEach(function (skill) { a[skill] = parseInt(v[skill], 10) || 0; });
  const update = {};
  SINGLE_STAT_NAMES.forEach(function (name) {
    const newTotal = SINGLE_STAT_FORMULAS[name](a);
    const prevApplied = parseInt(v[name + "_applied_stat_mod"], 10) || 0;
    const current = parseInt(v[name], 10) || 0;
    const delta = newTotal - prevApplied;
    if (delta !== 0) { update[name] = current + delta; }
    update[name + "_applied_stat_mod"] = newTotal;
  });
  setAttrs(update);
}

const SINGLE_STAT_MOD_GETATTRS = ATTR_NAMES.concat(SINGLE_STAT_SKILL_INPUTS).concat(SINGLE_STAT_NAMES)
  .concat(SINGLE_STAT_NAMES.map(function (s) { return s + "_applied_stat_mod"; }));

on("change:strength change:mental change:dexterity change:constitution change:defense change:casting change:close_combat",
  function () { getAttrs(SINGLE_STAT_MOD_GETATTRS, recomputeSingleStatMods); });

on("sheet:opened", function () { getAttrs(SINGLE_STAT_MOD_GETATTRS, recomputeSingleStatMods); });
/* ========================================================================= */

/* Caster level: hidden (never shown to the player), wiki.arx-libertatis.org/
   Caster_level — "(full_casting + full_mind) / 10", clamped 1-10 ("full_mind"
   is that wiki's own name for the Mental attribute). Not equipment-moddable
   (no item.json field for it) and never manually edited, so a plain
   recompute-and-set is enough — no delta/seed tracking needed like the
   visible stats above. Meant for spell power/duration/mana cost and scroll
   potency later, not wired into anything yet. */
function recomputeCasterLevel(v) {
  const casting = parseInt(v.casting, 10) || 0;
  const mental = parseInt(v.mental, 10) || 0;
  setAttrs({ caster_level: Math.max(1, Math.min(10, Math.floor((casting + mental) / 10))) });
}

on("change:casting change:mental", function () { getAttrs(["casting", "mental"], recomputeCasterLevel); });

on("sheet:opened", function () { getAttrs(["casting", "mental"], recomputeCasterLevel); });

/* ============================================================================
   SEPARATE, REMOVABLE BLOCK — health_max/mana_max scale with level and their
   own governing attribute (wiki.arx-libertatis.org/Stats: "full_max_health =
   full_constitution * (level + 2)", "full_max_mana = full_mental * (level +
   1)"). Same delta technique as the blocks above, tracked in its own
   attr_<name>_max_applied_stat_mod (see base.html.j2) so it never clobbers
   the equipment bonus living in attr_<name>_max_applied_mod on the same
   field. Level 0 + constitution/mental = 6 (this sheet's own starting
   values) already lands exactly on the current health/mana defaults (12/6),
   so a fresh character sees no jump — only leveling up or changing the
   governing attribute moves it. ============================================ */
const GAUGE_MAX_FORMULAS = {
  health_max: function (a) { return a.constitution * (a.level + 2); },
  mana_max: function (a) { return a.mental * (a.level + 1); }
};
const GAUGE_MAX_NAMES = Object.keys(GAUGE_MAX_FORMULAS);

function recomputeGaugeMax(v) {
  const a = {
    constitution: parseInt(v.constitution, 10) || 0,
    mental: parseInt(v.mental, 10) || 0,
    level: parseInt(v.level, 10) || 0
  };
  const update = {};
  GAUGE_MAX_NAMES.forEach(function (name) {
    const newTotal = GAUGE_MAX_FORMULAS[name](a);
    /* GM sheet: both gauges are pinned (see GM_GAUGE_MAX). The formula would
       otherwise read 600 × 202 = 121200 off its forced attributes. The
       bookkeeping below still records what the formula WOULD have given, so
       nothing drifts once the character goes back to being ordinary. */
    if (v.gm_panel_unlocked === "1") {
      if ((parseInt(v[name], 10) || 0) !== GM_GAUGE_MAX) { update[name] = GM_GAUGE_MAX; }
    } else {
      const prevApplied = parseInt(v[name + "_applied_stat_mod"], 10) || 0;
      const current = parseInt(v[name], 10) || 0;
      const delta = newTotal - prevApplied;
      if (delta !== 0) { update[name] = current + delta; }
    }
    update[name + "_applied_stat_mod"] = newTotal;
  });
  setAttrs(update);
}

const GAUGE_MAX_GETATTRS = ["constitution", "mental", "level", "gm_panel_unlocked"]
  .concat(GAUGE_MAX_NAMES)
  .concat(GAUGE_MAX_NAMES.map(function (s) { return s + "_applied_stat_mod"; }));

on("change:constitution change:mental change:level",
  function () { getAttrs(GAUGE_MAX_GETATTRS, recomputeGaugeMax); });

on("sheet:opened", function () { getAttrs(GAUGE_MAX_GETATTRS, recomputeGaugeMax); });

/* The GM is not a character: on a sheet the API has unlocked
   (attr_gm_panel_unlocked, see !arxunlockpanel) the level and the four
   attributes are pinned, out of reach of the caps above. Writing them fires
   the ordinary change: listeners, so the skills follow through their normal
   formulas — and, being ordinary skills, still stop at their own 125 cap.
   Only ever writes what actually differs, so re-opening the sheet is a
   no-op rather than a fresh setAttrs storm.
   The two gauge maxes are pinned as well, at a flat GM_GAUGE_MAX rather than
   at what their formula gives (constitution × (level + 2) = 121200 here):
   six digits do not fit the gauge's box. recomputeGaugeMax honours the same
   pin, so an attribute change cannot put the formula's value back. */
const GM_LEVEL = 200;
const GM_ATTR = 600;
const GM_GAUGE_MAX = 500;

function forceGmStats(v) {
  if (v.gm_panel_unlocked !== "1") { return; }
  const update = {};
  if ((parseInt(v.level, 10) || 0) !== GM_LEVEL) { update.level = GM_LEVEL; }
  ATTR_NAMES.forEach(function (attr) {
    if ((parseInt(v[attr], 10) || 0) !== GM_ATTR) { update[attr] = GM_ATTR; }
  });
  GAUGE_MAX_NAMES.forEach(function (name) {
    if ((parseInt(v[name], 10) || 0) !== GM_GAUGE_MAX) { update[name] = GM_GAUGE_MAX; }
  });
  if (Object.keys(update).length) { setAttrs(update); }
}

const GM_STAT_GETATTRS = ["gm_panel_unlocked", "level"]
  .concat(ATTR_NAMES).concat(GAUGE_MAX_NAMES);

on("sheet:opened change:gm_panel_unlocked",
  function () { getAttrs(GM_STAT_GETATTRS, forceGmStats); });
/* ========================================================================= */

/* Postures: one active at a time (attr_posture), clicking the active one
   again clears it — same toggle pattern as clicked:cast_<spellId>. */
["defensive", "offensive", "focus", "guardian"].forEach(function (name) {
  on("clicked:posture_" + name, function () {
    getAttrs(["posture"], function (v) {
      setAttrs({ posture: v.posture === name ? "" : name });
    });
  });
});

/* Guardian is GM-gated, not level-gated: attr_posture_guardian_unlocked is
   only ever set by the !arxunlockguardian API command (see arx-mod.js). If
   the GM re-locks it (!arxlockguardian) while it's the active posture,
   clear the posture too (same clamp-on-drop pattern as the gauges). */
on("change:posture_guardian_unlocked", function () {
  getAttrs(["posture_guardian_unlocked", "posture"], function (v) {
    if (v.posture_guardian_unlocked !== "1" && v.posture === "guardian") { setAttrs({ posture: "" }); }
  });
});

/* Focus posture: 0/1 flag multiplied into the skill roll formulas (see
   base.html.j2) — recomputed on every posture change, not just Focus's own
   click, since switching AWAY from Focus must also flip it back off. */
on("change:posture", function () {
  getAttrs(["posture"], function (v) { setAttrs({ focus_active: v.posture === "focus" ? "1" : "0" }); });
});
