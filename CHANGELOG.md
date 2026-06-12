# Changelog

All notable changes to the **Storyteller engine**. Newest version on top.

Each campaign carries a `VERSION` file naming the engine it last synced to. When you tell the GM *"update storyteller,"* it compares your `VERSION` to the latest, applies the changes below, and follows any **Campaign migration** note to reconcile files you've already filled in — without erasing your story. See `UPDATING.md` for how the sync works.

Version numbers are `MAJOR.MINOR.PATCH`:
- **PATCH** — wording or fixes to engine files. Safe; no migration.
- **MINOR** — new features or new engine files. May add an *optional* **Campaign migration** step.
- **MAJOR** — changes that need attention to your existing save data. Always carries a migration note.

---

## 2.5.0 — 2026-06-12

### Added — the agent loop (reflection + re-planning)
The third and capstone generative-agents subsystem. The pieces of the Concordia loop already existed but weren't *closed*: agents observed (memory) and retrieved (`memory_search`) but rarely **reflected**, and never **re-planned**. Now they do — so an NPC's behaviour changes in response to what they've learned and how a contest is going, integrating the ledger pressure (2.3) and the social observations (2.4).

- **Reflect** — `world_tick.py` flags an agent for reflection when it completes an FSM phase or culminates a clock (deterministic trigger, no new state), in a new queue `## Reflection` section. `world_scribe.py` runs a local **reflection pass**: it retrieves the agent's own recent memory and synthesises 1–2 higher-level **beliefs**, appended to their `drives.md` Reflection notes. New overridable prompt `Tools/local-agents/reflector.md`.
- **Plan** — `.claude/agents/world-director.md` gains a **re-planning** responsibility: when an agent has reflected or a control ledger swings hard (`phase: climax`), the director may change what they *want* — retarget the `goal`, resize the `clock`, flip a `relationships` edge — so rivals adapt instead of looping. Consequential and secret-aware, so it stays on Claude.
- **`world_scribe.py`** parsing hardened: the `## Reflection` and `## Interactions` sections can no longer be mistaken for agent movers.
- **`CLAUDE.md`** documents "The agent loop" (observe → retrieve → reflect → plan) in The living world; `Cast/_template/drives.md` Reflection-notes guidance updated.

This completes the arc begun in 2.1: the living world is now a fair, legible **generative-agents social simulation** — agents with goals and values that collide over deterministic stakes, spread news along a social graph, and adapt their plans as they learn.

### Campaign migration
- **Optional, automatic.** Reflection runs locally whenever an agent completes a phase and has a `drives.md`; re-planning happens through the normal `world-director` escalation. Nothing to set up.

## 2.4.0 — 2026-06-12

### Added — social topology & information propagation
The second of the three planned generative-agents subsystems. The relationship graphs in every `drives.md` already *form* a social network; now the world reads it so information spreads **asymmetrically** — an NPC learns of an off-screen event only if they're socially close to it, instead of everyone magically knowing everything. Ported in spirit from [`the_city`](https://github.com/synerdjin/the_city)'s `SocialConfig` (network_structure / reputation / groups).

- **New `Tools/social.py`** (dependency-free, reuses `world_tick.discover_agents`):
  - **Propagation** — `propagate()` takes the tick's *observable* developments and appends an **actor-safe** observation to the `memory.md` ("What I've learned about others") of every NPC within ~2 hops of a participant on the relationship graph. Deterministic BFS decides *who learns*; the note carries only the visible move, never a hidden secret. Idempotent.
  - **Groups** — a `group:` id on the agent block; same-group agents hear news one hop further.
  - **Reputation** — a *derived* standing (control held across `ledgers.md` + salience), so it never drifts from the deterministic world state and needs no store.
  - CLI `--graph` / `--self-test`.
- **`world_scribe.py`** runs propagation after writing developments (only non-hidden beats), reporting how many observations it seeded; defensive import keeps it optional.
- **`world_tick.py`** — `_allied` now treats **same-group** agents as allied, so faction-mates don't collide over a shared target. New optional `group:` field documented in `Cast/_template/drives.md`.
- **`CLAUDE.md`** documents "Social topology" in The living world; `UPDATING.md` registers `Tools/social.py`.

### Campaign migration
- **Optional, automatic.** Propagation runs whenever the local scribe writes an observable development and the involved NPCs have `memory.md` files (they do, from the template). Add a `group:` to a few NPCs' `drives.md` to enable in-group dynamics; nothing else to set up.

## 2.3.0 — 2026-06-12

### Added — deterministic control ledgers (contested-entity shared state)
Collision *detection* shipped in 2.1.0, but the *outcome* was decided fresh by the model each tick — so a recurring contest had no memory. Now every contested entity carries a **control ledger**: numeric shared state moved by a fixed rule, never by an LLM. Ported in spirit from [`the_city`](https://github.com/synerdjin/the_city)'s `CommonsResource` game-master component (numbers captured deterministically, a per-round ledger). This is the first of three planned generative-agents subsystems (ledger → social propagation → the full agent loop).

- **New `Tools/ledger.py`** — owns `Game/ledgers.md` (GM-only, tool-owned). Each contested entity is a pool of control points; `apply_pressure` shifts them toward the higher-**pressure** claimant (pressure = resources + mood + salience), drawn from a neutral pool then from the weakest opponent. Deterministic and auditable — `dice.py`'s "be seen to be fair" applied to politics. Exposes `holder` and a `phase` (forming → rising → climax). Dependency-free, with `--show` and `--self-test`.
- **`world_tick.py`** opens/advances a ledger for each contested target every tick and writes the standing + phase into the queue's `## Interactions` block. The metronome stays **fully deterministic** (no model, no randomness). Backward compatible: legacy string goals and ledger-less campaigns are unaffected; the ledger module is imported defensively.
- **`world_scribe.py`** reads the ledger standing for a collision and is instructed to **narrate what the number means** — never to change it or invent a winner.
- **Firewall:** `memory_index.py` classifies `Game/ledgers.md` as **secret** (never `--scope public`, never to an actor).
- **`CLAUDE.md`** documents the ledger inside "The living world"; `UPDATING.md` registers `Tools/ledger.py` (engine) and `Game/ledgers.md` (scaffold).

### Campaign migration
- **Optional, automatic.** `Game/ledgers.md` is created by the tools the first time a collision over a shared target is detected — nothing to set up. To use it, just ensure contesting NPCs aim opposed goals at the same `target` id (as the agent model already encourages).

## 2.2.0 — 2026-06-12

### Added — calibratable NPC worldviews (cultural profiles)
NPC *motivations* now rest on a **value substrate**, so a cast reasons from genuinely different worldviews instead of just different voices — which makes the emergent collisions of 2.1.0 feel inevitable rather than arbitrary. Adapted from the sibling research project [`the_city`](https://github.com/synerdjin/the_city) (a Concordia-based generative-agents framework): the pattern of turning numeric Hofstede / World Values Survey value dimensions into worldview text, ported as a dependency-free helper.

- **New `Tools/cultural_profile.py`** — a pure function (no model call, no dependencies) from a numeric value profile to a worldview sentence, with illustrative, **calibratable** presets: generic anchors (`individualist`/`collectivist`/`egalitarian`/`hierarchical`) and World-of-Darkness faction outlooks (`camarilla`, `sabbat`, `anarch`, `technocratic`, `tradition-mage`, `garou-tribal`). CLI: `python Tools/cultural_profile.py --list` / `<preset> --name "<who>"`; `--self-test` included.
- **Optional `## Worldview & values` section** in `Cast/_template/profile.md` (actor-safe — values are openly expressed), seeded from the tool.
- **`Cast/CRAFTING-NPCS.md`** lever #1 now grounds the *want* in a worldview; **`campaign-architect`** assigns each seeded NPC a distinct outlook so the living cast differs by value, not just voice.

### Campaign migration
- **Optional, additive.** Nothing changes for existing NPCs. To deepen a living NPC, run `python Tools/cultural_profile.py <preset>` and fold the worldview sentence into their `profile.md`. The presets are starting points — calibrate the numbers (or write your own `CulturalProfile`) for your chronicle.

## 2.1.0 — 2026-06-12

### Added — the living-world story engine
The engine becomes a **living-world story engine**: the Player is now **one protagonist among many**, the world's other characters pursue their own goals and **collide with each other**, and **plots emerge** from those collisions rather than from a pre-scripted outline. The world ticks on **every in-character post** (the local model is the per-post workhorse), and the whole chronicle can be archived as **fan-fiction** — mechanics hidden, prose chaptered. Backward-compatible: a campaign with no living agents still plays exactly as before, and old-shape `drives.md` files still parse.

- **Full agent NPC model** — `Cast/_template/drives.md` gains a **targeted `goal`** (`{ pursue, target, success }`), a **`relationships`** graph (typed, weighted edges to other entities), **`resources`** (advantage pools), and **`mood`** (volatile tracks). Two agents aiming at the same `target` is the minimal unit of emergence. `Cast/_template/memory.md` adds a *"What I've learned about others"* observation section; `Cast/CRAFTING-NPCS.md` is rewritten around emergence with a worked collision example.
- **Interaction/emergence engine** — `Tools/world_tick.py` stays deterministic and auditable but now **detects collisions** (contested-goal, rivalry, player-pressure) from the agent graph and writes them to a `## Interactions` queue section with a resource *advantage hint* (a hint, never a verdict). The parser handles the new fields unchanged.
- **Master plot registry** — new **`Game/plots.md`** tracks every plot (the Player's and the emergent ones) with state and `Player involvement` (unaware → participating); `Game/threads.md` is demoted to the **player-known view** derived from it.
- **Per-post local loop** — `Tools/world_scribe.py` gains an **interaction resolver**: it resolves collisions on the local model and **promotes hardened ones into `Game/plots.md`** (idempotently), escalating only pivotal beats to the Opus `world-director`.
- **Fan-fiction output** — new **`Story/`** tree (`index.md` front page, `chapters/NNNN-slug.md`, `compiled.md`), a new **`chapter-renderer`** subagent (Opus, secret-aware but governed by a strict **spoiler rule** for *meanwhile* chapters), and `Tools/story_compile.py` to export. `Tools/dice.py` gains **`-q/--quiet`** for resolve-then-narrate: the dice resolve off-page, the prose carries only the result.
- **`CLAUDE.md`** reframed: the ensemble + living-world prime directives, the per-post tick as step 6 of the play loop, the **resolve-then-narrate** dice contract (mechanics off the page, fairness on the record), the living world promoted from optional to core, and a new *"Rendering the story"* section.
- **Subagents:** `campaign-architect` now seeds a **connected living cast** (5–8 NPCs whose goals already collide) plus `plots.md`; `world-director` resolves `## Interactions` and maintains `plots.md`. Firewall preserved: `memory_index.py` classifies `plots.md` (and the enriched `drives.md`) as **secret**, never `--scope public`.

### Campaign migration
- **Optional, additive.** Existing campaigns keep working untouched. To light up the living world in an in-progress game, ask the GM to: promote a few NPCs by enriching their `drives.md` to the new agent model (targeted goals + relationships that **collide**), create `Game/plots.md` (copy the blank from the engine) and seed it from your open threads, and — for fan-fiction output — render with the `chapter-renderer` into the new `Story/` tree. A local model is strongly recommended for the per-post cadence; without one, tick at scene cuts and let the `world-director` handle the queue.
- **No save data is touched by the update** — `Game/*.md`, `Cast/<name>/`, `Character/`, `Sourcebooks/` are yours as always. `Game/plots.md` and `Story/` are scaffolds (your story), so the sync won't create them for you — ask the GM to set them up.

## 2.0.0 — 2026-06-07

### Changed — the engine is now a World of Darkness Storyteller
The generic, system-agnostic engine is **specialized for the World of Darkness**, running three games on the classic **Storyteller System** (d10 success pools): **Mage: The Ascension 20th (M20)**, **Vampire: The Masquerade 20th (V20)**, and **Werewolf: The Apocalypse 20th (W20)**. The old d20-and-traits defaults are **replaced**, not layered. Rules content stays **scaffolding-only** — the engine ships a faithful, lightweight Storyteller floor and the Player drops their own (copyrighted) rulebooks into `Sourcebooks/` for the GM to digest; a digest then overrides the defaults as before.

- **`CLAUDE.md`** is re-based on the Storyteller System:
  - Resolution is now the **d10 dice pool** — pool = Attribute + Ability (+ splat trait), difficulty 3–9 (default 6), successes counted, **1s cancel**, **botch** on 1s with zero successes, specialties (10 = 2), Willpower = +1 automatic success. Net successes set the degree (marginal → phenomenal).
  - The condition track is now **Health levels** (Bruised → Hurt → Injured → Wounded → Mauled → Crippled → Incapacitated) with bashing/lethal/aggravated damage and wound penalties.
  - **Growth/XP** is reframed for WoD (raise Attributes/Abilities, buy Sphere/Discipline/Gift dots), with a deliberately simple default scaffold and the explicit rule that a live game's **digest costs override** it.
  - New **"Which game are we playing?"** section anchored on a new state file (below); the intro, Session Zero order, and the resume checklist all now lead with it.
- **New `Game/system.md`** — the single source of truth for the live game, edition, **crossover** splats, and which digests are in force. Read first every session; written at Session Zero.
- **`Tools/dice.py`** — adds **`v20`/`vampire`** and **`w20`/`werewolf`** subcommands alongside the existing `m20`, all sharing the Storyteller resolver; `w20` adds a `-r/--rage` flag for Rage dice. Output now names the game (M20/V20/W20).
- **Subagents:**
  - **`character-creator`** builds a real Storyteller sheet — nine Attributes, Abilities (Talents/Skills/Knowledges), Backgrounds, Willpower, Health levels, Merits/Flaws — plus the **splat block** for the live game (Spheres/Arete/Paradox · Disciplines/Humanity/Beast · Gifts/Rage/Gnosis/Renown). Reads `Game/system.md` first; defers exact costs to a digest.
  - **`campaign-architect`** hooks the chronicle into the character's **splat identity** and builds WoD factions (Camarilla/Sabbat/Anarch · Traditions/Technocracy · Garou Nation/Wyrm-Weaver-Wyld), with crossover guidance.
  - **`world-director`** may resolve uncertain world-facts with a splat pool; WoD factions called out as ideal living agents.
  - **`npc-actor`** unchanged (already system-agnostic).
- **Templates & docs:** `Cast/_template/sheet.md` is now a Storyteller stat block (pools, Health levels, soak/aggravated, supernatural levers); `Sourcebooks/README.md` explains the bring-your-own-book WoD workflow; new `Sourcebooks/_digests/_TEMPLATE.md` digest skeleton; `README.md` reframed for the World of Darkness.

### Campaign migration
- **This is a MAJOR change: existing non-WoD campaigns should not blind-update.** A campaign already running on the old generic d20 defaults would have its rules pulled out from under it. If you want to keep a generic game, stay on `1.5.0`. To convert an existing game to a World of Darkness chronicle, update the engine files, then ask the GM to "set up `Game/system.md`" and re-stat your `Character/sheet.md` into the chosen splat — your story files (`Game/*.md`, `Cast/<name>/`, backstory, notebook) are untouched as always.
- **New engine file `Game/system.md`** is a *scaffold* (your story), so an update won't create it for you — ask the GM to "set up the system file," or copy the blank from the engine.

## 1.5.0 — 2026-06-05

### Added
- **Triggered-milestone XP — advancement you can see accrue.** The engine had only *invisible* growth: the GM eyeballed when a character had earned a change and nudged the sheet by feel, with nothing the Player could watch and no guard against GM-to-GM drift. There was no XP, no levels, and deliberately nothing tied to time or post count (per-session XP rewards exactly the cautious dawdling the engine is built to discourage). Now there's a lightweight default that keeps the fiction-first spirit while making progress **visible and auditable** — the `dice.py` "be seen to be fair" principle applied to growth.
  - **`CLAUDE.md`'s "Growth" section is rewritten** around a default **triggered-milestone XP** system, logged in a new `## Advancement` section of `Character/sheet.md`. XP is awarded **at scene/session close** for earned story beats (overcoming danger, resolving threads, discoveries, leaning into a Trouble, forging bonds) — **never** for time played or messages sent — and spent against a default cost table expressed in the sheet's own vocabulary (nudge a trait, gain an edge, retire a trouble, forge a bond). Every award is **day-stamped and logged in the Player's view**.
  - **The sourcebook override is mandatory, not optional, and settled at the start.** If a ruleset in `Sourcebooks/` defines its own XP, levels, or advancement, **its rules replace the entire default** — established at Session Zero (or when the sourcebook is added), exactly the way a sourcebook replaces the default resolution mechanic. The engine XP system is never layered on top of a book's own progression. The Sourcebooks digest "Overrides" checklist now lists advancement/XP alongside resolution, condition track, and oracle.
  - **The "Ending a session" ritual now tallies XP** — logging the session's milestones to the ledger and telling the Player what they earned and what it can buy.
  - **`character-creator`** seeds a zeroed `## Advancement` ledger on every new sheet (or builds a sourcebook's own progression structure instead), so a character starts with a dashboard rather than a blank. `Character/README.md` points to it.

### Campaign migration
- **Optional, low-effort.** The engine files (`CLAUDE.md`, `.claude/agents/character-creator.md`, `Character/README.md`) update automatically, so the XP discipline takes effect immediately. Your existing `Character/sheet.md` is **your save data and is never overwritten** — to adopt the ledger, just ask the GM to "start my XP ledger," and it'll add a zeroed `## Advancement` section (or back-fill a starting balance from your `timeline.md` if you'd rather). **If your campaign already runs on a `Sourcebooks/` ruleset with its own advancement, do nothing** — that book's rules already win by default.

## 1.4.0 — 2026-06-05

### Added
- **The Player's notebook — a spoiler-free dashboard written *for the Player to read*.** Every other state file is GM-facing or secret-laden; there was no single place that mirrored, in plain player-facing terms, *what the character knows, wants, and is chasing.* New scaffold **`PLAYER-NOTES.md`** (repo root) fills that gap: the situation in one breath, what you firmly know, your open questions, decisions on the table, your people, your toolkit — plus a **"Your own notes"** section the Player owns. (Generalized from a play-tested campaign — [synerdjin/storyteller-campaign#1](https://github.com/synerdjin/storyteller-campaign/pull/1).)
  - **`CLAUDE.md`** adds it to the Continuity file list with two governing rules — **never put a GM secret in it** (it's the one continuity file the Player reads), and **it's a curated mirror, not a dump** (written in the campaign's narrative voice, carrying only what the character has earned in play — distinct from the GM-facing `threads.md`/`current-scene.md`). The end-of-session ritual now refreshes it alongside `current-scene.md` and `timeline.md`.
  - **`campaign-architect`** seeds the opening entry at Session Zero (spoiler-free, in the campaign's voice, stamped Day 1), so a new campaign starts with a notebook rather than a blank page.
  - **`UPDATING.md`** files it in the **scaffold bucket** — never overwritten by an engine update, structure-spliced interactively if the shape ever changes — and the splice step now covers root scaffolds, not only `Game/*.md`.
  - Carries the v1.3.0 day-stamp convention (`Last updated: Day N`).

### Campaign migration
- **Optional, low-effort.** The engine files (`CLAUDE.md`, `UPDATING.md`, `.claude/agents/campaign-architect.md`, `README.md`) update automatically. An existing campaign won't have a `PLAYER-NOTES.md` — the scaffold is a *story file*, so an update never creates it for you. To adopt it, copy the blank scaffold from the engine (`git show engine/main:PLAYER-NOTES.md > PLAYER-NOTES.md`) or just ask the GM to "start my player notebook," and it'll build the dashboard from where your story currently stands.

## 1.3.0 — 2026-06-04

### Added
- **In-fiction timestamps — a campaign clock to stop chronology drift.** The GM and the `npc-actor` used to *guess* when things happened ("a few weeks ago…") because nothing in the save files let them compute it — every event log carried only an undefined date placeholder. Now there's one cheap, universal convention: **count the days.**
  - **`CLAUDE.md` gains a "Keeping in-fiction time — the campaign clock" subsection** (under Continuity). Day 1 = the first scene; the GM advances the count as in-fiction time passes and keeps the live value in the first line of `current-scene.md`'s "Where & when." Every logged entry is stamped `[Day N — in-world date]`, and elapsed time is **computed by subtracting day numbers, never estimated** — the dice-fairness rule applied to time.
  - **The `npc-actor` briefing now includes the current in-fiction date,** and the actor is told to reason about elapsed time from the day-stamps in its memory rather than guessing — the direct fix for NPCs hallucinating "how long it's been."
  - **Templates bake the format in** so it's copied, not improvised: `Cast/_template/memory.md`, `Game/timeline.md`, `Game/current-scene.md`, `Game/developments.md`, and `Game/threads.md` (opened/resolved day markers).
  - **The `campaign-architect`** now seeds **Day 1** and a one-line **Calendar** note in `Game/world.md` at Session Zero; **the `world-director`** reads the current day from `current-scene.md` and day-stamps everything it writes to `memory.md` and `developments.md`.
  - `Tools/world_tick.py` is **unchanged** — the calendar stays a GM-maintained convention, deliberately decoupled from the metronome's abstract FSM clocks. On a time-skip the GM advances the day count *and* passes the matching `--elapsed N`, keeping the two in sync.

### Campaign migration
- **Optional, low-effort.** The engine files (`CLAUDE.md`, `.claude/agents/*`, `Cast/_template/memory.md`) update automatically, so the day-counting discipline takes effect immediately. The `Game/*.md` **scaffolds** (`timeline.md`, `current-scene.md`, `developments.md`, `threads.md`) gained a date-stamp structure but are never overwritten — to adopt it in an existing campaign, set the current day in `current-scene.md`'s "Where & when" (Day 1 = your first session; estimate the count to today), add a one-line Calendar note to `world.md`, and start stamping new entries going forward. Back-dating old entries is unnecessary — the convention only needs to hold from here on.

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
