"""Persist engine results back to SQLite — the counterpart to loader.py.

Where the original `Tools/` code rewrote markdown surgically, this writes the
same state changes to the DB: advanced clocks/FSM, contested-control ledgers,
templated developments, propagated observations, and the structured edits a
director returns (re-plan, beliefs, memory, plot promotion).
"""

from __future__ import annotations

from ..engine.ledger import Ledger, NEUTRAL


def name_to_id(conn, world_id):
    return {r["name"]: r["id"]
            for r in conn.execute("SELECT id, name FROM agents WHERE world_id=?",
                                  (world_id,))}


# ── tick results ─────────────────────────────────────────────────────────────

def persist_tick(conn, agents):
    """Write advanced clock + FSM state for agents that changed this tick."""
    from ..engine.tick import changed
    for a in agents:
        if changed(a) and a.id is not None:
            clock = a.fields.get("clock", {})
            conn.execute(
                "UPDATE agents SET clock_filled=?, state=? WHERE id=?",
                (clock.get("filled", 0), a.fields.get("state"), a.id))
    conn.commit()


# ── ledgers ──────────────────────────────────────────────────────────────────

def load_ledgers(conn, world_id):
    """Return {entity: Ledger} for a world."""
    out = {}
    for row in conn.execute("SELECT * FROM ledgers WHERE world_id=?", (world_id,)):
        control = {r["claimant"]: r["points"]
                   for r in conn.execute(
                       "SELECT claimant, points FROM ledger_control WHERE ledger_id=?",
                       (row["id"],))}
        history = [r["text"] for r in conn.execute(
            "SELECT text FROM ledger_history WHERE ledger_id=? ORDER BY id", (row["id"],))]
        out[row["entity"]] = Ledger(row["entity"], total=row["total"],
                                    control=control, holder=row["holder"],
                                    history=history)
    return out


def save_ledger(conn, world_id, led):
    """Upsert one Ledger (entity row + control rows + full history)."""
    row = conn.execute("SELECT id FROM ledgers WHERE world_id=? AND entity=?",
                       (world_id, led.entity)).fetchone()
    if row:
        lid = row["id"]
        conn.execute("UPDATE ledgers SET total=?, holder=?, phase=? WHERE id=?",
                     (led.total, led.holder, led.phase(), lid))
        conn.execute("DELETE FROM ledger_control WHERE ledger_id=?", (lid,))
        conn.execute("DELETE FROM ledger_history WHERE ledger_id=?", (lid,))
    else:
        cur = conn.execute(
            "INSERT INTO ledgers (world_id, entity, total, holder, phase) "
            "VALUES (?,?,?,?,?)",
            (world_id, led.entity, led.total, led.holder, led.phase()))
        lid = cur.lastrowid
    for claimant, points in led.control.items():
        conn.execute(
            "INSERT INTO ledger_control (ledger_id, claimant, points) VALUES (?,?,?)",
            (lid, claimant, points))
    for text in led.history:
        conn.execute("INSERT INTO ledger_history (ledger_id, text) VALUES (?,?)",
                     (lid, text))
    conn.commit()


# ── developments + propagation ───────────────────────────────────────────────

def add_development(conn, world_id, dev):
    """Insert one development record (a dict from scribe or a director)."""
    cur = conn.execute(
        "INSERT INTO developments "
        "(world_id, day, agent, headline, body, surface, escalate, drained, source, arc)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (world_id, dev.get("day"), dev.get("agent"), dev["headline"],
         dev.get("body", ""), dev.get("surface", "hidden"),
         int(bool(dev.get("escalate"))), int(bool(dev.get("drained"))),
         dev.get("source", ""), dev.get("arc")))
    conn.commit()
    return cur.lastrowid


def add_observations(conn, world_id, observations):
    """Persist actor-safe observations (idempotent via UNIQUE(agent_id, text))."""
    ids = name_to_id(conn, world_id)
    written = 0
    for obs in observations:
        aid = ids.get(obs["learner"])
        if aid is None:
            continue
        try:
            conn.execute(
                "INSERT INTO memory_observations (agent_id, day, about, text, hops) "
                "VALUES (?,?,?,?,?)",
                (aid, obs.get("day"), obs.get("about"), obs["text"], obs.get("hops")))
            written += 1
        except Exception:
            pass  # UNIQUE violation → already recorded; idempotent
    conn.commit()
    return written


def append_memory(conn, agent_id, day, text):
    conn.execute("INSERT INTO memory_log (agent_id, day, text) VALUES (?,?,?)",
                 (agent_id, day, text))
    conn.commit()


def add_timeline(conn, world_id, day, text):
    conn.execute("INSERT INTO timeline (world_id, day, text) VALUES (?,?,?)",
                 (world_id, day, text))
    conn.commit()


def add_cost(conn, world_id, day, templated=0, sonnet=0, opus=0, notes=""):
    conn.execute(
        "INSERT INTO cost_ledger (world_id, day, templated, sonnet_beats, opus_beats, notes)"
        " VALUES (?,?,?,?,?,?)",
        (world_id, day, templated, sonnet, opus, notes))
    conn.commit()
