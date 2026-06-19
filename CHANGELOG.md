# Changelog

All notable changes to the **Storyteller engine**. Newest version on top.

Each campaign carries a `VERSION` file naming the engine it last synced to. When you tell the GM *"update storyteller,"* it compares your `VERSION` to the latest, applies the changes below, and follows any **Campaign migration** note to reconcile files you've already filled in — without erasing your story. See `UPDATING.md` for how the sync works.

Version numbers are `MAJOR.MINOR.PATCH`:
- **PATCH** — wording or fixes to engine files. Safe; no migration.
- **MINOR** — new features or new engine files. May add an *optional* **Campaign migration** step.
- **MAJOR** — changes that need attention to your existing save data. Always carries a migration note.

---

## 2.11.1 — 2026-06-19

### Fixed — review findings from v2.10.0 / v2.11.0

A retrospective Opus review of PRs #15 and #16 surfaced two real defects (both verified by reproduction) and two doc-accuracy gaps. The firewall *security* core was unaffected — these are an availability bug and a dead code path, not secret leaks.

- **`resources.py --show` crashed on a stock Windows console (Critical).** The Willpower pip string (`●●●●●○○○○○`) and Health glyphs were printed straight to stdout, which on Windows is cp1252 and cannot encode `●`/`○` — so the most-used command (`"what are my current pools?"`) raised `UnicodeEncodeError`. Console output now renders ASCII (`[#####.....] (5/10)`, `#`/`/`/`*`/`.` for Health); the sheet **file** still stores the real glyphs (it's UTF-8). New `render_show()` is testable, and `--self-test` assertion #9 encodes the output to cp1252 so the crash can't regress.
- **`actor_brief.py` retrieval was dead code (Major).** The optional "Relevant context" pass called `memory_search.search(scene, …, top_k=3, mode="lexical")` — wrong function and wrong signature (`search` takes `(root, query_vec, …)` with no `top_k`/`mode`), so it raised `TypeError` 100% of the time and was swallowed by a bare `except: pass`. Fixed to call `search_text(root, scene, scope="public", owner=name, k=3, mode="lexical")`, adapt the `(score, record)` result shape, and log the cause to stderr instead of hiding it.
- **`firewall.append_observation` is now genuinely atomic.** Writes stage to a temp file and `replace()` into place, so a crash mid-write can't truncate a learner's `memory.md` (the docs already claimed atomic; now it's true).
- **`gather_secrets` scope documented.** Its docstring now states the boundary explicitly: it covers the per-Cast-agent corpus (drives.md + secrets.md), **not** campaign-level secret files (`gm-secrets.md`, hidden `developments.md`, `plots.md` prose). Upstream discipline (a fixed, goal-free headline) remains the primary defense.
- **Nit:** `op_gain`'s capped-at-max label uses `--` instead of an em-dash (cp1252-safe, consistent with the rest of the log format).

### Campaign migration (none required)
Pure engine-file fixes; no save-data changes.

---

## 2.11.0 — 2026-06-19

### Added — firewall-safe actor pipeline (`Tools/firewall.py` + `Tools/actor_brief.py`)

Two persistent manual-process risks: (a) a director writing an observation line that accidentally echoes a hidden goal or secret into `Cast/*/memory.md`, where it could surface to the `npc-actor`; (b) the GM hand-assembling an npc-actor briefing and forgetting to exclude one of the GM-only files. This release closes both with structural tools — not convention, not trust.

**Part A — `Tools/firewall.py`: the sanctioned write path and per-post scan**

- **Promoted fingerprint functions.** `_tokens`, `_shares_ngram`, `safe_headline`, and `_forbidden_texts` — previously defined inline in `social.py` — are moved into `firewall.py` as the single source of truth. `social.py` now imports them from there. Behavior is byte-identical; `social --self-test` still passes.
- **`append_observation(root, learner, day, text)` — the only sanctioned write path** into "What I've learned about others." Validates `text` against the full secret corpus (front-matter + drives prose body + `secrets.md`) before writing. Social.py's `append_observation` now routes through this. Directors must validate with `--check "<line>"` before any raw write, or call this programmatically.
- **`gather_secrets(root)` — comprehensive scope.** Extends the propagation guard (front-matter only) to include the prose body of `drives.md` (reflection beliefs) and `secrets.md` text — so the per-post scan catches reflection-appended beliefs that the propagation guard never saw.
- **`--scan` (per-post, not just session-end).** Checks every `Cast/*/memory.md` for observation lines that echo a secret fingerprint. Folds into the per-post loop (after the director pass) so a leak surfaces the same turn it's written. Exit 1 = leak found.
- **`--check "<text>"` — director validation gate.** `python Tools/firewall.py --check "<line>"` lets a director verify a single line before writing. Exit 0 = safe; exit 1 = rejected.
- **`--scrub [--dry-run]` — targeted repair.** Removes only auto-generated observation lines (matching the `- *[Day N]* — about \`X\`:` pattern) that fail the fingerprint. Never touches authored log entries. Always run `--dry-run` first.
- **`--self-test` (5 assertions):** verbatim secret rejected; abstract observation passes; common-words false-positive not triggered; scrub dry-run lists offenders without writing / live scrub removes only them; Unicode NPC name can't dodge the match.

**Part B — `Tools/actor_brief.py`: the allowlist-enforced briefing assembler**

- **Path allowlist (`_ALLOWED_FILENAMES = {"profile.md", "memory.md"}`)** enforced by `_read_safe()`. Any read attempt on a file outside this set — `secrets.md`, `drives.md`, `sheet.md`, `gm-secrets.md`, or any other character's files — raises `PermissionError` before a single byte is read. Structural safety, not convention.
- **CLI:** `actor_brief.py <name> [--scene] [--recent] [--stance] [--said] [--day N]`. Outputs the complete npc-actor briefing to stdout for pasting. `--no-retrieve` skips the optional `memory_search --scope public` retrieval pass.
- **`--self-test` (5 assertions):** briefing contains profile + memory content + day; secrets.md/drives.md content never appears; missing profile fails loudly; path allowlist rejects `secrets.md`/`drives.md` explicitly; safe files are allowed.

**Directors mandate updated.** Both `world-director.md` and `world-director-lite.md` now require all "What I've learned about others" writes to be validated via `--check` or routed through `firewall.append_observation`. `CLAUDE.md` adds `python Tools/firewall.py --scan` as step 4 of the per-post loop and references `actor_brief.py` in the NPC voicing section.

### Campaign migration (none required)
Additive. No save-data changes. `Tools/firewall.py` and `Tools/actor_brief.py` are new engine files added to the UPDATING.md manifest and the `git checkout` step.

---

## 2.10.0 — 2026-06-19

### Added — deterministic resource tracking (`Tools/resources.py`)

In play, the GM was hand-editing `Character/sheet.md` ~8 times per session to track Willpower, Quintessence, Paradox, and Health, and ruling refill amounts on the fly because the engine's floor didn't specify them. That's the one place "be seen to be fair" wasn't tool-backed the same way `dice.py` and `ledger.py` are. This release closes the gap.

- **New tool (`Tools/resources.py`).** Reads and writes the volatile pool block in `Character/sheet.md`, applies rule-based spends/gains/recovery, and logs every change to `Character/resource-log.md` — day-stamped and reason-tagged, auditable on demand. The GM calls it instead of hand-editing; the rules become consistent instead of improvised. Pure stdlib, no model, no randomness — same bar as `dice.py`.
- **Operations:** `--show` (current pools + wound penalty), `--spend POOL N`, `--gain POOL N`, `--rest [--full]` (WP recovery), `--node N` (Quint refill from a Node), `--damage TYPE N [--soak N]`, `--heal N`, `--paradox +N/-N`. `--dry-run` previews without writing. `--sheet PATH` targets an NPC's sheet for statted opposition.
- **Pools covered:** Willpower (rating + current + pip string), Quintessence, Paradox, Health (7 levels; bashing/lethal/aggravated marks; derived wound penalty). Splat analogues (Blood/Vitae, Rage, Gnosis) parsed and supported when present on the sheet.
- **Recovery rules get a home:** WP rest (+1/call, default; configurable), Node refill (capped at Node rating and permanent max), soak step (the tool never rolls — `dice.py` does; the GM passes the result as `--soak N`), Health healing (GM-paced via `--heal`). Override any default via `Game/resource-rules.json`.
- **Firewall.** `Character/resource-log.md` is classified `secret` in `memory_index.py` — never indexed for `--scope public`, never handed to an `npc-actor`. Regression assertion in `--self-test`.
- **Built-in `--self-test`** (no model, no network): round-trip safety, clamp guards, rest rule, Node rule, Health marking/soak/healing, digest override, day inference, firewall classification.

### Campaign migration (none required)
Additive; no save-data changes. `Character/resource-log.md` is authored history (like `Game/timeline.md`) — commit it alongside the sheet. A `Game/resource-rules.json` scaffold is optional; defaults are documented in the tool header.

---

## 2.9.0 — 2026-06-17

### Added — the living-world dashboard (author god-view console)
The world's state was scattered across GM-only files (`plots.md`, `developments.md`, the living cast, `ledgers.md`), with no single place to *see* the world move or to pick a thread to lean into. This release adds a deterministic, dependency-free console that renders one readable view of it.

- **New tool (`Tools/world_dashboard.py`).** Renders `Game/world-dashboard.md` with two sections: **the world right now** (who's in motion — state, clock, salience, mood, goal target; what just moved off-screen; where contested-control pressure is building) and **threads you could pull** (every plot grouped by the Player's involvement, so the Player can scan the world and choose what to engage). It reads existing state and **invents nothing** — pure stdlib, no model, no randomness, output stable across runs. Reuses `world_tick.py`'s agent discovery / collision helpers and `ledger.py`'s standing/phase rather than re-parsing.
- **Spoiler-tiered, not spoiler-filtered.** The file is GM/author tier and *contains secrets*, so instead of hiding them it **tags** every item 🟢 KNOWN / 🟡 SENSED / 🔴 HIDDEN to show what the character has actually earned. A strict `--player` mode produces a genuinely spoiler-free view (KNOWN/SENSED only, no GM internals; tier defaults fail closed to HIDDEN).
- **Firewall.** `Tools/memory_index.py`'s `classify()` now **skips** `world-dashboard.md` — it is never indexed, never returned by `--scope public`, never handed to an `npc-actor`. The generated file is **gitignored** alongside the other rebuildable, spoiler-bearing artifacts (`.world-health.md`, the memory index).
- **Wired into the loop.** `CLAUDE.md` refreshes it as a step of the per-post tick loop and on *"show me the world,"* and documents it under "The world dashboard." Built-in `--self-test` covers tiering, the `--player` firewall, fenced-example/`---`-rule parsing, a no-`Surface` development failing closed, and graceful empty-world output.

### Campaign migration (optional, automatic)
- No action required. The dashboard is additive and touches no save data; `Game/world-dashboard.md` is a rebuildable, gitignored artifact you regenerate any time with `python Tools/world_dashboard.py`. The `memory_index.py` change only adds the new file to the skip list, so a re-index is harmless (and not required).

## 2.8.0 — 2026-06-16

### Fixed — close a social-propagation firewall leak (secret goal text reaching actor-safe memory)
Playtesting surfaced a firewall breach: the per-post social propagation was writing **secret `drives.md` goal/`success` text** into actor-safe `Cast/*/memory.md` ("What I've learned about others"). Any NPC voiced via `npc-actor` (which is handed `profile.md` + `memory.md`) would then "know" the very thing a mystery depends on. `world_scribe.py` propagated `_short(a.get("goal"))` as the observation headline — i.e. the goal line, which carries the agent's `success` clause — and `social.py` faithfully wrote whatever headline it was handed. The propagation step's own contract is that *only the visible move is recorded, never the hidden cause*; this violated it.

- **Source fix (`world_scribe.py`).** The headline propagated into a learner's memory is now a fixed, goal-free constant (`OBSERVABLE_HEADLINE` — "has been quietly pursuing aims of their own lately"), never the agent's goal/`success` text. The GM-only `developments.md` entry still names the real goal (that file is not actor-safe); the NPC memory note no longer does.
- **Defense-in-depth (`social.py`).** `propagate()` no longer trusts its caller. It fingerprints every living agent's secret front-matter — goal `pursue`/`success` **and** relationship `note`s — and validates each headline (`safe_headline`): a verbatim word-run (4-gram for long secrets; the whole phrase for short ones, so a 3-word `success` can't slip the window) or an over-long headline is dropped, never written. Tokenization is Unicode-aware, so a non-ASCII NPC name can't dodge the match. This is a backstop over known secret fields, not a second airtight wall — the primary defense remains the upstream fixed headline.
- **Migration detection (`world_health.py`).** A new **Firewall** check scans every actor-safe `memory.md` for leaked secret text and warns with the offending file + whose secret leaked, so a campaign that ran an affected earlier tick can find and scrub it. The session-end scan goes beyond the per-post guard: it fingerprints the drives.md prose body (## Agenda, ## Reflection notes) and `secrets.md` too. If the `social` module can't be imported it returns an explicit "scan skipped" note — a broken import never reads as a clean bill of health.
- **Regression tests** added to all three tools' `--self-test` so a future edit that re-opens the firewall fails loudly.

### Campaign migration (important if you played on 2.6.x–2.7.0)
- Run `python Tools/world_health.py` once after updating. If the new **Firewall** section flags any `Cast/*/memory.md`, open the named file and delete the offending `- *[Day N]* — about \`X\`: …` line(s) under "What I've learned about others" — these leaked secret goal text. A quick manual check: `grep -rn "What I've learned" -A20 Cast/*/memory.md` and remove any line that reads like a goal/agenda rather than a witnessed event.
- No automated edit touches your save data; the scrub is yours to confirm. Nothing in story, cast profiles, plots, or character is otherwise changed.

## 2.7.0 — 2026-06-15

### Changed — retire the local generative tier; upgrade local retrieval to hybrid search
Playtesting surfaced the predictable failure of a small local model asked to *invent* World-of-Darkness facts: the qwen plot-scribe gave a Toreador a memory-erasure power, a Mind charm to a vampire with no Mind sphere, and staged a reality-shredding mage standoff that contradicted the live scene. The drift was structural (generation, not retrieval), so this release **splits the two local jobs and treats them oppositely** — keep the well-behaved embedder, retire the generative model — and controls Claude cost with a clean three-tier escalation. Engine law holds: Claude is the brain, tools stay deterministic and dependency-free.

- **The local generative tier is retired.** `Tools/world_scribe.py` no longer calls any LLM. It now **templates routine off-screen movers deterministically** from the metronome's structured state — a true, abstract fact ("X pressed on toward their goal; clock now 4/6"), never an invented event or power, so that class of drift is now *structurally impossible*. It prints a **hand-off manifest** (collisions, reflection, pivotal movers) instead of resolving them locally. The generative prompts `Tools/local-agents/{plot-scribe,critic,reflector}.md` are removed.
- **New everyday director on Sonnet.** `.claude/agents/world-director-lite.md` (`model: sonnet`) resolves the routine collisions, faction turns, and reflection/re-planning — faithful to the splat's rules and cheap. `world-director.md` (Opus) is now scoped to the **secret-bearing pivots**: planned reveals, beats turning on a hidden secret's payoff, a major faction's whole trajectory, or the Player's own arc. The lite director flags anything it hits that belongs to Opus.
- **Hybrid semantic search.** `Tools/memory_search.py` now fuses dense embeddings with a pure-Python **BM25** lexical ranking via **Reciprocal Rank Fusion**, plus small auditable metadata boosts (an owner named in the query; optional `--recency`). New flags: `--mode hybrid|dense|lexical` (lexical needs **no model**) and `--recency`. Exact proper nouns ("Club Schwarm") that dense alone missed now land.
- **Embedder swapped to `bge-m3`** (1024-dim, MIT) in `Tools/local_config.py` and `Game/local-models.json`. `llm_model` is now off the per-post hot path (used only by the optional `world_health` tone read and the deferred reranker seam).
- **Reranker seam (deferred).** `memory_search.maybe_rerank()` is a documented no-op; Ollama has no native rerank endpoint, so a neural reranker is left as an optional future step.

### Campaign migration (optional)
- After updating, set `embed_model` to `bge-m3` in your campaign's `Game/local-models.json` (or keep your current embedder — both work) and run `python Tools/memory_index.py --rebuild` once. The index records its embedder and refuses to search a mismatched one, so it rebuilds safely either way.
- Pull the embedder: `ollama pull bge-m3`. No LLM pull is required anymore.
- Nothing in your save data (story, cast, plots, character) is touched.

## 2.6.0 — 2026-06-13

### Added — three patterns harvested from the 2025 D&D-agents literature
Two papers from the Concordia/generative-agents lineage — Sancheti et al., *Towards LLM-Agents That Play Dungeons & Dragons Using Iterative Prompting* (CEUR Vol-4097), and Vezhnevets et al., *Multi-Actor Generative AI as a Game Engine* (arXiv 2507.08892) — largely *validate* the engine's existing architecture (GM-as-reality-arbiter, grounded variables, witness-only propagation, the explicitly Dramatist director). This release adopts the three findings that were genuinely net-new, staying inside the engine's law: Claude is the brain, tools stay deterministic and dependency-free.

- **Play mode — the engine's stance (the Evaluationist/Dramatist/Simulationist typology).** A new `## Play mode` block in `Game/system.md` and a matching section in `CLAUDE.md` name the engine's stance (Dramatist-on-a-Simulationist-substrate) and make it campaign-configurable. The dial **never changes the dice or tools** — only how the GM and `world-director` *interpret* the same deterministic state. `world-director.md` now reads and weights it; Session Zero settles it alongside tone.
- **The NPC compliance loop (iterative prompting).** Paper 1's empirical finding — single-pass actors drift from context and go passively agreeable, and iterative prompting fixes it — ported two ways: `npc-actor.md` gains a silent three-test self-check (narrative compliance / in-character consistency / deliberate intent — the enemy is *sycophancy*, never a quiet or reserved line) with one revise pass, and `CLAUDE.md`'s NPC-voicing section gains a GM-side **compliance gate** that re-invokes the actor only when its line contradicts canon the blind actor couldn't see or goes genuinely non-responsive — with an explicit "quiet is not stalled" guard so restrained, subtext-heavy scenes are never re-prompted into pushiness.
- **The drift self-eval harness.** New `Tools/world_health.py` (deterministic, dependency-free, reuses `world_tick.py`'s parser and agent discovery) turns the papers' three action categories into a periodic health audit: frozen agents, stalled clocks, a world too quiet to generate plot, stale threads, an un-drained `Surface: now` backlog. An optional local tone/compliance read (`Tools/local-agents/health-auditor.md`) degrades cleanly to "skipped" with no Ollama. Writes only the GM-only `Game/.world-health.md`; run it at session end (now in the "Ending a session" checklist).

### Campaign migration
- **Optional, automatic.** `Game/system.md` gains a `## Play mode` block — if yours predates this release it simply reads as "Dramatist (default)" until you set it; nothing breaks. `world_health.py` is additive and touches no save data. No action required.

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
