# System — how this game is set up

> The single source of truth for the edition, rules, and tone that are live. Every agent and the Storyteller read this first. Update it only with the Player's agreement (e.g. adding a sourcebook digest, changing a house rule).

## Game

- **Game:** Mage: The Ascension (M20) — this engine is dedicated to it.
- **Edition / line:** *(e.g. 20th Anniversary Edition)*
- **Tone:** *(default: the tone the M20 core rulebook suggests. Record here any lean the Player chose at Session Zero — e.g. grittier, more hopeful, grander, more intimate — and keep the content limits and "lines & veils" in `boundaries.md`.)*

## Rules in force

- **Live sourcebook digests** (under `Sourcebooks/_digests/`):
  - **`M20-core.md`** — *the rules in force.* Overrides the CLAUDE.md defaults (resolution nuances, magick & Paradox, condition track/soak, XP costs). Read this for any real ruling.
  - **`M20-how-do-you-do-that.md`** — Sphere-effects reference (expansion): what Spheres/ranks a given feat needs. Reach for it mid-scene.
  - **`M20-book-of-secrets.md`** — character options + expanded rules (expansion): Archetypes, Merits & Flaws, stunts, Certámen. Optional subsystems off unless switched on.
  - **`M20-gods-and-monsters.md`** — antagonist/bestiary reference (expansion) for seeding and statting opposition.
  - **`M20-forbidden-and-forgotten-orders.md`** — extra Disparate Crafts/orders (expansion) as character/NPC options.
- **Dice subcommand:** `m20` — what to pass to `Tools/dice.py`.
- **House rules:** *(any tweaks the Player wants — soak, difficulty conventions, lethality, etc. Keep tone/content limits in `boundaries.md`, not here.)*
