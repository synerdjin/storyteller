---
living: true
state: scheming
goal: { pursue: control, target: harbor-council, success: "holds the swing vote before the festival" }
clock: { filled: 0, total: 6 }
advances_when: dawdle
salience: 3
group: camarilla
resources: { influence: 3, muscle: 1, coin: 2, secrets: 4 }
mood: { confidence: 3, desperation: 1 }
relationships:
  vance:  { tie: rival,  weight: -4, note: "the one person who can block the seat" }
  player: { tie: wary,   weight: -1 }
  sabbat: { tie: patron, weight: 3,  note: "owes them, and they know it" }
states:
  scheming:    { to: moving,      when: "clock>=3" }
  moving:      { to: confronting, when: "clock>=6" }
  confronting: { to: regrouping,  when: "always" }
  regrouping:  { to: scheming,    when: "clock>=2" }
---

# <Name> — DRIVES (GM ONLY)

> ⚠️ **Optional, and GM-only.** This is what makes a character *living* — it lets `Tools/world_tick.py` advance their agenda off-screen, detect when their goals **collide** with another agent's, and flag them for the `world-director`. Like `secrets.md` and `sheet.md`, it is **never** handed to the `npc-actor`. Add it when you want this character to pursue goals — and contend with others — while the Player isn't watching (see `CLAUDE.md` → "The living world" and `CRAFTING-NPCS.md` lever #5). An incidental face needs none.

## The machine block (top, between the `---` lines)

The metronome parses *only* the front-matter above. Keep it to this shape — inline `{ ... }` maps and one level of `key:`-nested children, exactly like `states:` and `relationships:` below.

**Core (the solo clock — unchanged from earlier versions):**
- **`living`** — `true` to include them in the tick; `false` (or delete the file) to mothball.
- **`state`** — their current node in the FSM. The metronome updates this in place.
- **`clock`** — a progress clock `{ filled: N, total: M }`. The metronome fills it; the director may reset or resize it.
- **`advances_when`** — when the clock ticks: `always` (every tick, by elapsed time) · `dawdle` (only when the Player stalls) · `on_fail` (only when a roll fails forward) · `manual` (only the director moves it).
- **`salience`** — 1–5. How loudly they press on the story; raises their priority when the metronome picks who gets attention this tick.
- **`group`** — *optional* — a faction/clique id (e.g. `camarilla`, `pack-zero`). Same-group agents default **allied** (they don't collide over a shared target) and hear each other's news one hop further on the social graph (see `CLAUDE.md` → "Social topology"). Omit for an unaligned loner.
- **`states`** — the FSM. Each `node: { to: <next>, when: <guard> }`. Guards understood: `always`, `clock_full`, or `clock <op> N` (`>=`, `>`, `<=`, `<`, `==`, `!=`). Anything else never fires (fail-safe). One transition per tick at most.

**The agent model (what makes plots *emerge*):**
- **`goal`** — a **targeted** intent: `{ pursue: <verb>, target: <entity-id>, success: <one line> }`. The `target` is the engine of emergence — when two living agents aim at the **same** target, the metronome flags a collision. Keep `pursue` to a short verb the collision rule can read as opposed or aligned: `control` / `protect` / `destroy` / `seize` / `expose` / `court` / `undermine`. (A bare string still parses, but won't collide — give it a target to bring it into the simulation.)
- **`target` / entity IDs** — stable identifiers other agents can name: a `Cast/<name>` folder name, a faction `##` heading in `Game/world-state.md`, a location id from `Game/world.md`, or the literal `player`. Use the id, not prose.
- **`resources`** — abstract pools the agent can spend to get its way: `{ influence, muscle, coin, secrets, ... }` (0–5 each, pick the few that fit). The metronome passes these to the resolver as an **advantage hint** in a clash — it never decides the winner itself (that stays in the model tier, like `dice.py`).
- **`mood`** — short, volatile tracks (`{ confidence, desperation, ... }`, 0–5) the director nudges over time. Rising desperation makes an agent reach for the move they'd normally never make — this is how an NPC's pressure escalates believably.
- **`relationships`** — the graph. Each `<entity-id>: { tie: <kind>, weight: -5..5, note: <opt> }`. `tie` is the relationship's shape (`ally`, `rival`, `debt`, `grudge`, `kin`, `lover`, `patron`, `wary`, …); `weight` is its charge (negative = antagonism, positive = bond). A `rival`/`grudge` edge between two agents whose clocks both advance is the second way the metronome detects a brewing clash.

## Agenda (prose for the director)
What they actually *want* off-screen, how they pursue it, who they'd move against, what a "win" looks like for them. The FSM is the skeleton; this is the flesh the director reads to decide what they *do*.

## Relationships (prose)
The story behind the graph edges above — the history with each named entity, why the tie is what it is, and what would flip it. The numbers are for the metronome; this is for the director.

## Resources & leverage (prose)
What each resource pool actually *is* in the fiction (whose ear the `influence` buys, who the `muscle` is, what the `secrets` are) — so a clash resolves in concrete terms, not abstract points.

## Reflection notes
Higher-level conclusions the director has drawn over past ticks — about the Player, rivals, or their own situation. (The Generative-Agents "reflection" step: synthesizing events into beliefs keeps a long-running character coherent instead of drifting.) Start empty; the director appends here.
