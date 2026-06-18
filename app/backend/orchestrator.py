"""tick_world — the deterministic per-tick orchestrator.

Mirrors `Tools/world_tick.run` end to end, but reads/writes SQLite via the
loader/writer instead of markdown, and stops at the hand-off manifest (the
generative director tier in directors/ is invoked separately by the API so it
can stream progress). The metronome's selection is binding: this returns exactly
the movers/collisions/reflection the fixed rules picked, no more, no less.
"""

from __future__ import annotations

from .db import loader, writer
from .engine import ledger as ledger_mod
from .engine import scribe, social
from .engine import agent as A
from .engine.tick import (changed, detect_interactions, priority, tick)


def _apply_ledgers(conn, world_id, agents, interactions, day):
    """Advance the deterministic control ledger for each contested entity.

    Verbatim port of world_tick.apply_ledgers: gather pressures for every
    contested-goal collision (plus any third-party claimant on the same target),
    shift control by the fixed rule, annotate the interactions, and persist.
    """
    contested = {}
    for it in interactions:
        if it.kind == "contested-goal" and it.over:
            contested.setdefault(it.over, {})
            for p in (it.a, it.b):
                if p is not None:
                    contested[it.over][p.name] = A.pressure(p)
    for entity in list(contested):
        for a in agents:
            if A.goal_target(a) == entity:
                contested[entity].setdefault(a.name, A.pressure(a))
    if not contested:
        return

    ledgers = writer.load_ledgers(conn, world_id)
    results = {}
    for entity, pressures in contested.items():
        led = ledger_mod.get_or_create(ledgers, entity)
        results[entity] = ledger_mod.apply_pressure(led, pressures, day)
        writer.save_ledger(conn, world_id, led)
    for it in interactions:
        if it.kind == "contested-goal" and it.over in results:
            r = results[it.over]
            it.standing = r["standing"]
            it.phase = r["phase"]


def tick_world(conn, world_id, elapsed=1, dawdle=False, fail=False, max_n=3):
    """Run one deterministic beat; return a structured result + hand-off manifest."""
    world = conn.execute("SELECT current_day FROM worlds WHERE id=?",
                         (world_id,)).fetchone()
    if world is None:
        raise ValueError(f"no world {world_id}")
    day = world["current_day"]

    agents = loader.load_agents(conn, world_id, living_only=True)
    for a in agents:
        tick(a, elapsed, dawdle, fail)

    candidates = sorted((a for a in agents if changed(a)),
                        key=lambda a: (-priority(a), a.name))
    selected = candidates[:max_n]
    interactions = detect_interactions(agents, max_n)
    _apply_ledgers(conn, world_id, agents, interactions, day)
    reflectors = [a for a in agents if a.transitioned or a.became_full][:max_n]

    writer.persist_tick(conn, agents)

    # scribe: template routine movers → developments + observation events
    developments, observation_events, escalated = scribe.scribe_movers(day, selected)
    dev_ids = []
    for dev in developments:
        dev_ids.append(writer.add_development(conn, world_id, dev))

    propagated = 0
    if observation_events:
        observations, rejected = social.propagate(agents, observation_events)
        propagated = writer.add_observations(conn, world_id, observations)

    # advance the campaign clock to match the elapsed time
    if elapsed:
        conn.execute("UPDATE worlds SET current_day = current_day + ? WHERE id=?",
                     (elapsed, world_id))
        conn.commit()

    manifest = scribe.manifest(interactions, reflectors, escalated)
    writer.add_cost(conn, world_id, day, templated=len(developments),
                    notes="deterministic tick + scribe (no model)")

    return {
        "day": day,
        "new_day": day + elapsed,
        "living": len(agents),
        "moved": sum(changed(a) for a in agents),
        "selected": [a.name for a in selected],
        "developments": [{**d, "id": i} for d, i in zip(developments, dev_ids)],
        "propagated": propagated,
        "interactions": manifest["collisions"],
        "reflection": manifest["reflection"],
        "pivotal_movers": manifest["pivotal_movers"],
        "manifest": manifest,
    }
