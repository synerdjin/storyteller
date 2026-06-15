# Plots — the master plot registry (GM ONLY)

> ⚠️ GM-only. This is the **single source of truth** for every plot in the living world — the Player's personal plot *and* the emergent world plots that run with or without them, including the ones the Player has never heard of. The per-post loop reads and updates it: a Claude director (`world-director-lite`, or `world-director` for a pivot) **promotes a detected collision into a new entry here** when it matures into a standing conflict.
>
> `Game/threads.md` is the **player-facing view** of this file — only the plots the Player's character actually knows about, written for them to read. Keep `threads.md` strictly derived from the `Player involvement: aware | observing | participating` entries here; the hidden and `unaware` plots live only in this file. Never quote this file to the Player or hand it to an `npc-actor`.

## How an entry works

Each plot is a `###` entry nested under one of the section headings below (`Player plot`, `World plots`, `Resolved`):

```
### <plot-id> — <Title>
- Participants: <entity ids, comma-separated>   # Cast/<name>, faction headings, location ids, player
- Stakes: what is actually being fought over, and what changes if each side wins.
- State: forming | rising | climax | resolved
- Clock: filled/total                            # the plot's own progress clock
- Player involvement: unaware | aware | observing | participating
- Surface: now | soon (trigger: ...) | hidden
- Arc: <arc-id>                                   # links the matching entries in developments.md
- Opened: Day N   |   Closed: Day M (when resolved)
```

- **State** tracks the dramatic arc: `forming` (the collision is latent) → `rising` (the agents are clashing off-screen) → `climax` (it breaks into the open) → `resolved` (settled; leave it, don't delete).
- **Player involvement** is the knob that keeps the ensemble honest. `unaware`: the Player has no idea this exists — it may surface later as rumor, news, or a "meanwhile" chapter. `aware`: their character has heard of it. `observing`: they're watching it unfold. `participating`: they've opted in and are acting on it. The GM raises this as the Player engages — and may let a plot run its whole course at `unaware`, resolving entirely off-screen.
- **Surface** is the timing the GM drains from `developments.md`: `now` (live pressure this scene), `soon` (on the named trigger), `hidden` (brewing, not yet perceptible).
- **Arc** ties a plot to its day-stamped beats in `developments.md`, so the prose "why" and the registry state stay in sync.

## Player plot
*The thread the Player's own character is driving. Always `participating`.*

- *(none yet — the campaign-architect seeds this from the character's backstory at Session Zero.)*

## World plots
*Emergent and seeded plots the world runs. Newest first. The per-post loop appends promoted collisions here.*

- *(none yet — the campaign-architect seeds 2–3 proto-plots from the cast's latent collisions; more emerge in play.)*

## Resolved
*Settled plots, kept for the record (don't delete). Stamp the close day.*

- *(none yet)*
