# World state — the living world (GM ONLY)

> ⚠️ GM-only register of the **living world**: the factions and world-level clocks that `Tools/world_tick.py` advances off-screen, plus a roster of which NPCs are currently "living." Read and acted on by the GM and the `world-director` subagent; **never** quoted to the Player or handed to an `npc-actor`.
>
> This file is inert until you fill it in. A campaign with no living agents plays exactly as a normal Storyteller game — the world moves only when you say so. See `CLAUDE.md` → "The living world."

## How this works
- **Living NPCs** are discovered automatically: any `Cast/<name>/drives.md` with `living: true` is in the simulation. You don't need to list them here, but a quick roster helps you keep track.
- **Factions and world-level clocks** live *in this file*, as fenced ```yaml blocks under a `##` heading (one block per faction). The metronome parses each block exactly like a `drives.md` front-matter block, and updates `state:` / `clock:` in place.
- To bring something to life, copy a template block below, fill it in, and set `living: true`. To mothball it, set `living: false`.

## Living-NPC roster
*(For your reference — the script reads the `drives.md` files directly.)*
- _none yet — promote an NPC by adding a `drives.md` (copy `Cast/_template/drives.md`)._

## Factions & world clocks

<!-- Copy this block per faction. Flip living to true to activate it. The block
     shape is identical to Cast/_template/drives.md — see that file for the full
     field reference (states, guards, advances_when, salience). -->

```yaml
living: false
state: gathering
goal: "What this faction is driving toward across the region"
clock: { filled: 0, total: 8 }
advances_when: always
salience: 2
states:
  gathering: { to: pressing,   when: "clock>=4" }
  pressing:  { to: breaking,   when: "clock>=8" }
  breaking:  { to: gathering,  when: "always" }
```

### Notes (prose for the director)
What each faction is really doing, who leads it, how its moves should land. The director reads this alongside the block above.
