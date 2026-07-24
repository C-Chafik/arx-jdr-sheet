# ARX Character Sheet — Spec

Fiche de personnage custom pour le JDR **Arx Fatalis**, sur Roll20.

## Roadmap globale

1. **Version legacy** (en cours) — fiche HTML/CSS/sheet-worker classique, copier-coller dans Game Settings, autonomie totale (pas de pipeline de publication Roll20). C'est la version qu'on finit maintenant.
2. **Portage Beacon SDK** (plus tard) — reconstruction de la fiche legacy avec le Beacon SDK (Vue.js + Vite + `@roll20-official/beacon-sdk`), pour débloquer le vrai dessin à la souris (accès DOM complet, plus de sandbox sheet-worker). Contrainte connue et acceptée : même en usage 100% privé, Roll20 exige une review manuelle + PR sur leur repo Community Sheets avant que la fiche soit utilisable (formulaire d'accès par email, par joueur). Objectif : réussir la review dès la première PR, donc être aussi rigoureux que possible sur l'implémentation avant soumission.

## Pourquoi legacy plutôt que Beacon dès le départ

- Legacy = copier-coller HTML+CSS dans Game Settings, aucune dépendance à une review externe, itération instantanée.
- Beacon = stack Node/Vue/Vite complète + review Roll20 obligatoire même pour un usage privé (aucun moyen de contourner, confirmé via la doc officielle et les forums).
- Le dessin libre à la souris (tracer une rune) est **impossible en legacy**, confirmé par 3 sources indépendantes :
  - Les sheet workers Roll20 n'ont aucun accès DOM (`getAttrs`/`setAttrs`/`on()` uniquement, pas de `document`, pas de canvas, pas d'event listeners).
  - Les balises `<script>` classiques (hors `type="text/worker"`) ne s'exécutent pas dans le HTML de fiche custom (confirmé empiriquement : un prototype canvas + script plein ne rend rien du tout sur une vraie fiche Roll20).
  - Confirmé par un développeur expérimenté sur le forum Roll20 : *"You can use css and use hover and possibly active. That's it."*
- D'où la décision : finir la version legacy avec un système de runes **basé sur des clics** (pas de dessin), et migrer vers Beacon plus tard uniquement pour débloquer le vrai dessin si on le souhaite encore à ce moment-là.

## Ce qui est déjà fait (version legacy)

Architecture : `build.py` (Python + Jinja2) assemble `src/templates/` + `src/css/` + `src/workers/inventory.js` en un fragment HTML unique + CSS, à copier-coller dans Roll20 (Game Settings → Custom). `build/preview.html` simule Roll20 en local pour itérer vite (avec un panel DEV qui n'existe que là, jamais envoyé à Roll20).

- **Page de base** : niveau, 4 attributs, 9 compétences, jauges HP/Mana, dégâts, 3 résistances, nom du personnage (synchronisé avec le journal Roll20), tooltips au survol, animation de clic doré.
- **Navigation de page** (base ↔ magie) : boutons + sheet worker (`act_goto_base`/`act_goto_magic`, attribut `attr_sheet_tab`). **Important** : n'utilise PAS de radio/label `for`/`id` — Roll20 ne respecte pas fiablement cette association (plusieurs copies de la fiche peuvent coexister dans le DOM, les `id` entrent en collision). Tout le reste de la navigation (pages de sorts, toggle inventaire) suit ce même pattern bouton+worker.
- **Inventaire complet** : grille de sac 15×3, jusqu'à 4 niveaux déblocables, empreintes multi-cases, pick/place (sans échange), slots d'équipement (tête/torse/ceinture/main principale/secondaire/2 bijoux), pouche (débloque un niveau de sac), bourse (dépôt/retrait d'or), poubelle, items légendaires (halo + nom en rouge).
- **Toggle inventaire** : bouton + worker (`act_inventory_toggle`, attribut `attr_inventory_open`), même raison que la navigation.
- **Page magie** :
  - 10 pages de sorts numérotées, boutons + worker (`act_goto_spellpage_N`, attribut `attr_spell_page`). Un onglet de page ne s'ouvre que si au moins un sort de cette page est débloqué (runes connues), page 1 toujours visible.
  - Grille de 20 slots à droite : révèle l'icône magicbook d'une rune apprise, remplissage à **position fixe** par rune (basé sur l'ordre de `items.json`), pas par ordre de consommation.
  - Grimoire : glisser une rune consommée dessus l'apprend définitivement (`attr_known_<suffixe>`), refuse les doublons.
  - 2×2 emplacements de sorts actifs par page (`spells.json` : label, runes requises, page, slot, icône).
  - 3 emplacements de sorts **mémorisés (presets)** : `presets.json` (auto-suffisant : label + runes + icône + `secret: true/false`), lié par id partagé avec `spells.json` pour les sorts du livre ; sorts secrets définis uniquement dans `presets.json`.
- **`arx-mod.js`** (script API Roll20, compte Pro, GM only) : `!arxgive <item_id>`, `!arxlearnall`, `!arxpreset <1-3> <spell_id>`, `!arxpage <1-10>`, `!arxtab base|magic`.
- **Tests** : `tests/test_build.py` (pytest), ~32 tests structurels sur le HTML/CSS généré.

### Fichiers de données (source de vérité)

- `items.json` — catalogue d'objets (armes, armures, bijoux, objets, runes, or).
- `spells.json` — sorts du livre magique (label, runes requises, page, slot, icône).
- `presets.json` — sorts mémorisables (auto-suffisant, inclut les sorts secrets).
- ~~`rune-patterns.json`~~ — **obsolète**, était les séquences directionnelles du système de boussole (abandonné), à supprimer.

## Ce qu'il reste à faire (version legacy)

### 1. Clic sur un sort → lance le jet sur Roll20

**Reporté** — l'utilisateur a explicitement choisi de finir le système de craft/presets d'abord ("Non le lancée de dée on verra plus tard, finissons le systeme d'abord, sur les presets et les runes"). Un sort actif (dans un des 2×2 slots) doit devenir un vrai bouton `type="roll"` (comme les stats de la page de base) au lieu d'un `type="action"` inerte, avec une formule de dés associée. **À définir avec l'utilisateur** : quelle formule/quel roll pour chaque sort — trois options envisagées (1d20+attribut, dés fixes par sort dans `spells.json`, ou pas de dé/juste un message de chat) n'ont pas encore été tranchées.

### 2. Système de craft de runes (remplace la boussole abandonnée) — ✅ fait

Mécanique implémentée :
1. Le joueur clique sur une **rune apprise** (bouton sur un des 20 slots de la grille, à droite du grimoire) → la rune s'ajoute **dans l'ordre** à `attr_craft_runes` (liste délimitée `|rune-a|rune-b|`, même idée que `fitMask`, pour éviter les collisions de préfixe entre id de rune).
2. Chaque clic supplémentaire sur une autre rune apprise l'ajoute à la suite.
3. Bouton **Valider** (`act_craft_confirm`) : compare l'**ensemble** (ordre non important) des runes accumulées à chaque entrée de `presets.json` (qui couvre déjà tous les sorts du livre + les sorts secrets) → si match exact, écrit l'id du preset dans le premier `attr_preset_slot_N` libre et vide `attr_craft_runes`. Sans match, ne fait rien (le joueur peut continuer à ajouter des runes ou réinitialiser).
4. Bouton **Annuler/Reset** (`act_craft_reset`) : vide `attr_craft_runes` sans valider.

Implémentation : `src/workers/inventory.js` (`craftList`/`craftJoin`, boucle `clicked:craft_rune_N` pour N=1..20, `clicked:craft_confirm`, `clicked:craft_reset` — `PRESETS` injecté dans le worker via `{{PRESETS_JSON}}` dans `build.py`) ; `src/templates/partials/pages/magic.html.j2` (les 20 slots du spellbook sont maintenant des `button type="action"`, + `attr_craft_runes` caché + boutons Valider/Annuler, texte brut pour l'instant faute d'asset dédié) ; `src/templates/css/magic-slots.css.j2` (reset des styles de bouton sur les slots, glow doré sur la/les rune(s) en cours de combinaison via sélecteur `[value*="|rune-x|"]`, styles des boutons Valider/Annuler). Vérifié par simulation Node (ordre de clic inversé → même match, deux presets différents remplissent bien les slots 1 puis 2, combinaison sans correspondance ne remplit rien).

## Migration Beacon SDK (plus tard)

Objectif : reproduire **tout** ce qui est listé ci-dessus (legacy complet), avec en plus le vrai dessin de rune à la souris (canvas + reconnaissance de tracé), en visant une implémentation correcte dès la première soumission (review Roll20 = latence hors de notre contrôle, donc pas de droit à l'erreur superflu).

- Stack : Node.js, Vue.js (recommandé par Roll20) ou autre framework SPA, Vite, `@roll20-official/beacon-sdk`.
- Dev local : `initRelay`, bac à sable Roll20 pointé sur `localhost:7620` (comparable à notre `preview.html` actuel).
- Publication : PR sur `Roll20/roll20-beacon-sheets`, checklist de soumission, puis formulaire d'accès listant les emails Roll20 des joueurs autorisés (aucun mode privé sans review).
- Cette migration n'a pas commencé — à reprendre une fois la version legacy jugée complète.
