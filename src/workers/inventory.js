const ITEMS = {{ITEMS_JSON}};

const COLS = {{GRID_COLS}};
const ROWS = {{GRID_ROWS}};
const BAGS = {{GRID_BAGS}};
const PER_LEVEL = COLS * ROWS;
const BAG_SLOTS = [];
for (let i = 1; i <= PER_LEVEL * BAGS; i++) { BAG_SLOTS.push("bag_" + i); }

const EQUIP_ACCEPTS = {
  equip_head: ["casque"],
  equip_torso: ["armure_haute"],
  equip_belt: ["armure_basse"],
  equip_main_hand: ["arme_principale"],
  equip_off_hand: ["arme_secondaire", "bouclier"],
  equip_jewel_1: ["bijoux"],
  equip_jewel_2: ["bijoux"]
};
const ALL_SLOTS = BAG_SLOTS.concat(Object.keys(EQUIP_ACCEPTS));

function sizeOf(itemId) {
  const s = (ITEMS[itemId] && ITEMS[itemId].size) || "1x1";
  const parts = s.split("x");
  return { w: parseInt(parts[0], 10) || 1, h: parseInt(parts[1], 10) || 1 };
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

/* Footprint of the item currently anchored at `anchor` ([] for equip slots). */
function ownCells(anchor, itemId) {
  if (anchor.indexOf("bag_") !== 0) { return []; }
  return cellsFor(bagIndex(anchor), sizeOf(itemId).w, sizeOf(itemId).h) || [];
}

function equipAccepts(slot, itemId) {
  if (!itemId || !ITEMS[itemId]) { return false; }
  return (EQUIP_ACCEPTS[slot] || []).indexOf(ITEMS[itemId].cat) !== -1;
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
    getAttrs(ALL_SLOTS.concat(["hand", "hand_from", "bag_count"]), function (v) {
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
          fit: fitMask(v, item, ownCells(anchor, item))
        });
        return;
      }

      /* Cancel: click the origin anchor or any of its covered cells. */
      if (slot === from || here === "#" + from) {
        setAttrs({ hand: "", hand_from: "", hand_cat: "", fit: "" });
        return;
      }

      const clear = { hand: "", hand_from: "", hand_cat: "", fit: "" };
      const own = ownCells(from, hand);

      if (slot.indexOf("bag_") === 0) {
        if (bagIndex(slot) > PER_LEVEL * bagCount(v)) { return; } /* locked level */
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

      /* Equipment target: category match + empty slot (no swap). */
      if (!equipAccepts(slot, hand) || here !== "") { return; }
      own.forEach(function (c) { clear[c] = ""; });
      if (own.length === 0) { clear[from] = ""; }
      clear[slot] = hand;
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
    const update = { hand: "", hand_from: "", hand_cat: "", fit: "",
                     bag_count: count + 1 };
    ownCells(v.hand_from || "", hand).forEach(function (c) { update[c] = ""; });
    if ((v.hand_from || "").indexOf("equip_") === 0) { update[v.hand_from] = ""; }
    setAttrs(update);
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
