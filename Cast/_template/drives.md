---
living: true
state: scheming
goal: "What they're driving toward off-screen, in a line"
clock: { filled: 0, total: 6 }
advances_when: dawdle
salience: 3
states:
  scheming:    { to: moving,      when: "clock>=3" }
  moving:      { to: confronting, when: "clock>=6" }
  confronting: { to: regrouping,  when: "always" }
  regrouping:  { to: scheming,    when: "clock>=2" }
---

# <Name> — DRIVES (GM ONLY)

> ⚠️ **Optional, and GM-only.** This is what makes a character *living* — it lets `Tools/world_tick.py` advance their agenda off-screen and flag them for the `world-director`. Like `secrets.md` and `sheet.md`, it is **never** handed to the `npc-actor`. Add it only when you want this character to pursue goals while the Player isn't watching (see `CLAUDE.md` → "The living world" and `CRAFTING-NPCS.md` lever #5). An incidental face needs none.

## The machine block (top, between the `---` lines)

The metronome parses *only* the front-matter above. Keep it to this shape:

- **`living`** — `true` to include them in the tick; set `false` (or delete the file) to mothball them.
- **`state`** — their current node in the FSM below. The metronome updates this in place.
- **`goal`** — one line; what they're chasing off-screen. The director reads it.
- **`clock`** — a progress clock: `{ filled: N, total: M }`. The metronome fills it; the director may reset or resize it after a turn.
- **`advances_when`** — when the clock ticks:
  - `always` — every tick (advances by the tick's elapsed time).
  - `dawdle` — only when the Player stalls or plays it safe.
  - `on_fail` — only when a roll fails forward.
  - `manual` — never automatically; only the director moves it.
- **`salience`** — 1–5. How loudly they press on the story; raises their priority when the metronome picks who gets the director's attention this tick.
- **`states`** — the FSM. Each `node: { to: <next>, when: <guard> }`. Guards the metronome understands: `always`, `clock_full`, or `clock <op> N` (`>=`, `>`, `<=`, `<`, `==`, `!=`). Anything else never fires (fail-safe). One transition fires per tick at most.

## Agenda (prose for the director)
What they actually *want* off-screen, how they pursue it, who they'd move against, what a "win" looks like for them. The FSM is the skeleton; this is the flesh the director reads to decide what they *do*.

## Reflection notes
Higher-level conclusions the director has drawn over past ticks — about the Player, rivals, or their own situation. (The Generative-Agents "reflection" step: synthesizing events into beliefs keeps a long-running character coherent instead of drifting.) Start empty; the director appends here.
