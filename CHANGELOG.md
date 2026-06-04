# Changelog

All notable changes to the **Storyteller engine**. Newest version on top.

Each campaign carries a `VERSION` file naming the engine it last synced to. When you tell the GM *"update storyteller,"* it compares your `VERSION` to the latest, applies the changes below, and follows any **Campaign migration** note to reconcile files you've already filled in — without erasing your story. See `UPDATING.md` for how the sync works.

Version numbers are `MAJOR.MINOR.PATCH`:
- **PATCH** — wording or fixes to engine files. Safe; no migration.
- **MINOR** — new features or new engine files. May add an *optional* **Campaign migration** step.
- **MAJOR** — changes that need attention to your existing save data. Always carries a migration note.

---

## 1.2.0 — 2026-06-04

### Added
- **The living world — an opt-in off-screen simulation.** Important NPCs and factions can now pursue their own goals between scenes, so cautious solo play no longer drifts into dead air and the world's threats advance *fairly* instead of only when convenient. It's a two-layer hybrid:
  - **`Tools/world_tick.py`** — a deterministic, dependency-free "metronome" (the `dice.py` of the simulation). It parses the structured state of every living agent, advances their progress clocks by fixed rules, fires finite-state-machine transitions whose guards are met, and selects the few most pressing agents for deliberation — writing an ephemeral queue. It decides *which* threats move; it invents no narrative. Has a built-in `--self-test`.
  - **`.claude/agents/world-director.md`** — a GM-side "drama manager" subagent (opus) that reads the queue and decides *what* each flagged agent actually does off-screen, biased toward dramatic pressure but resolved honestly (no faked dice, no retro-filled clocks). It writes consequences back to the agents' files and stages player-facing developments. **Crucially distinct from `npc-actor`:** the director is trusted with secrets because it advances hidden agendas; the actor still runs blind. The two roles are never to be confused.
  - **`Cast/_template/drives.md`** — the optional, GM-only file that makes an NPC "living": a small machine-readable block (state, goal, clock, FSM, salience) plus prose agenda and accumulating reflection notes. Never handed to the `npc-actor`, alongside `secrets.md` and `sheet.md`.
  - New GM-only scaffolds **`Game/world-state.md`** (living factions + world clocks + roster) and **`Game/developments.md`** (the director's staged, curated inbox of off-screen moves and when each should surface).
- **`CLAUDE.md` gains a "The living world — ticking it" section** (after Progress clocks): how to promote an agent to living, the two-step tick loop, that the metronome's selection is binding, and how to drain `developments.md` into scenes. Includes an **optional Cowork recipe** for running ticks as a scheduled task between sessions.
- **`Cast/CRAFTING-NPCS.md` lever #5 ("Agency off-screen")** now points at the living-world loop, and `Cast/README.md` documents `drives.md`.

### Campaign migration
- **None required.** The feature is additive and **inert until you opt in** — a campaign with no `drives.md` files and an unfilled `world-state.md` plays exactly as before. The two new `Game/` scaffolds are story files (never overwritten by future updates); the tool, subagent, and template are engine files. To bring the world to life in an existing campaign, ask the GM to promote an NPC: copy `Cast/_template/drives.md` into their folder and fill it in.

## 1.1.1 — 2026-06-04

### Changed
- **`npc-actor` continuity across re-invocations.** The actor runs cold every invocation — no scene memory unless the GM puts it in the briefing. Two changes address the drift this causes in multi-turn exchanges: (1) `npc-actor.md` now instructs the actor to treat any quoted prior dialogue and stance notes as *already said / already taken* — building on, qualifying, or visibly turning rather than silently reversing; (2) `CLAUDE.md` now tells the GM what to include when re-invoking mid-scene: the character's own recent words **verbatim** (not paraphrased) plus a 2–3 bullet stance recap. Also notes that inline voicing may serve a fast, secret-free exchange better than repeated subagent calls, since the GM holds the dialogue history for free. Backported from play experience. No migration needed.

## 1.1.0 — 2026-06-04

### Added
- **NPC mechanical sheets.** `Cast/_template/` gains an optional, GM-only `sheet.md` — traits, condition track, edges/troubles, and tactics for any NPC who'll face contested rolls or a fight. It's never handed to the `npc-actor` (added to the "never pass" list, alongside `secrets.md`), so a rival now wins or loses on *consistent* numbers and the dice-fairness rule covers the opposition too. `CLAUDE.md`'s Resolution section now points the GM at the opposing NPC's sheet when setting difficulty or marking harm.
- **A craft guide for deep NPCs** — `Cast/CRAFTING-NPCS.md`. A GM-facing reference for building important/recurring characters with real morals, goals, a wound, off-screen agency, and a distinct voice — scoped so incidental faces stay a quick sketch. `CLAUDE.md` and `Cast/README.md` point to it.

### Changed
- **Richer character template prompts.** `profile.md` (actor-safe) now prompts for a moral code, want-vs-need, the background that shaped them, and a visible contradiction; `secrets.md` (GM-only) now prompts for the unadmitted need, the wound/lie, the moral breaking point, and how they'd change under pressure. Existing characters are unaffected.

### Campaign migration
- **None required.** Your existing `Cast/<name>/` folders stay valid as-is. The new `sheet.md`, the craft guide, and the enriched prompts apply to characters you build *going forward*. If you like, you can **optionally** ask the GM to enrich an existing important NPC with the new fields, or add a `sheet.md` to one who keeps ending up in fights — but nothing breaks if you don't.

## 1.0.2 — 2026-06-03

### Changed
- **`npc-actor` now runs at high reasoning effort** (`effort: high` in its frontmatter). The character-voicing role still runs on Sonnet, but with more deliberation per reply — richer, more in-character performances, at a little more latency/cost. Tuning only; no migration needed.

## 1.0.1 — 2026-06-03

### Changed
- **Roll announcements stay out of the narrative prose.** `CLAUDE.md` now asks the GM to announce a roll's terms — trait/approach, difficulty, what's at stake — in a short aside set apart from the story text, instead of weaving the numbers into the narration. The fiction stays clean; the mechanics stay legible. A trait's *name* may still surface in the fiction when it reads as natural in-world language. (Backported from a play-tested campaign and generalized away from any one system.) Wording only — no migration needed.

## 1.0.0 — 2026-06-02

First versioned release. This is the baseline the update system measures from; campaigns started before this carry no `VERSION` file and are treated as "pre-1.0, update available."

### Added
- **Engine-update mechanism** — `VERSION`, `CHANGELOG.md`, and `UPDATING.md`. You can now pull newer engine files into an existing campaign with *"update storyteller,"* and the GM will leave your character, world, and history untouched.

### Changed
*(Recent engine work, folded into the baseline.)*
- **NPC isolation is now structural.** The `npc-actor` subagent runs with no file tools (`tools: []`), so a character's voice literally cannot reach `secrets.md` or `gm-secrets.md` — the guarantee no longer rests on instructions alone.
- **Recurring characters remember you.** The actor is now handed the character's `memory.md` alongside `profile.md`, fixing the "old ally greets you like a stranger" bug. `secrets.md` still never leaves the GM.
- **Deeper solo-play GMing** in `CLAUDE.md` — adversary honesty and "don't over-resolve" directives, three-tier outcomes, a d6 oracle for world-state questions, progress clocks, a condition track with teeth, fiction-driven advancement, a co-author input model, an in-media-res resume, and an end-of-session ritual.

### Campaign migration
- **`Game/boundaries.md` gained a `## Narrative voice` section** (Person / Tense / Density), set during Session Zero so the GM's prose style stays as consistent as the facts do. If your campaign began before this and your `boundaries.md` has no such section, ask the GM to add it — it will splice in the block below, just before `## Lines — never include`, and leave your Tone, Lines, and Veils exactly as you wrote them:

  ```markdown
  ## Narrative voice
  How the GM should *write*, so the feel stays consistent session to session.
  - **Person:** second ("you draw your blade") or third ("Kara draws her blade")?
  - **Tense:** present or past?
  - **Density:** spare and punchy, lush and descriptive, or somewhere between?
  ```
