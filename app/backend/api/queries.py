"""Read helpers for the API — with the curtain enforced at the data layer.

`curtain=False` (the default) returns only the world-status / actor-safe view: an
agent's profile but not its secrets/drives, developments that have surfaced but
not hidden ones, no ledger internals. `curtain=True` is the observer's
omniscient peek. Enforcing the split here (not just in the UI) means the default
responses can never accidentally leak a secret.
"""

from __future__ import annotations

from ..db import writer


def _agent_public(row):
    return {
        "id": row["id"], "name": row["name"],
        "display_name": row["display_name"] or row["name"],
        "kind": row["kind"], "living": bool(row["living"]),
        "state": row["state"], "salience": row["salience"],
        "location_id": row["location_id"],
        "profile_md": row["profile_md"],
    }


def list_agents(conn, world_id):
    rows = conn.execute("SELECT * FROM agents WHERE world_id=? ORDER BY name",
                        (world_id,)).fetchall()
    return [_agent_public(r) for r in rows]


def agent_detail(conn, agent_id, curtain=False):
    row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if row is None:
        return None
    out = _agent_public(row)
    aid = row["id"]
    out["observations"] = [r["text"] for r in conn.execute(
        "SELECT text FROM memory_observations WHERE agent_id=? ORDER BY id DESC LIMIT 20", (aid,))]
    out["memory"] = [r["text"] for r in conn.execute(
        "SELECT text FROM memory_log WHERE agent_id=? ORDER BY id DESC LIMIT 20", (aid,))]

    if not curtain:
        out["curtained"] = True   # there is more behind the curtain
        return out

    # ── behind the curtain: the agent's whole mind ──
    out["curtained"] = False
    out["goal"] = {"pursue": row["goal_pursue"], "target": row["goal_target"],
                   "success": row["goal_success"]}
    out["clock"] = {"filled": row["clock_filled"], "total": row["clock_total"]}
    out["advances_when"] = row["advances_when"]
    out["group"] = row["group_id"]
    out["resources"] = {r["key"]: r["value"] for r in conn.execute(
        "SELECT key, value FROM agent_resources WHERE agent_id=?", (aid,))}
    out["mood"] = {r["key"]: r["value"] for r in conn.execute(
        "SELECT key, value FROM agent_mood WHERE agent_id=?", (aid,))}
    out["relationships"] = [dict(r) for r in conn.execute(
        "SELECT target_ref, tie, weight, note FROM relationships WHERE agent_id=?", (aid,))]
    out["states"] = [dict(r) for r in conn.execute(
        "SELECT from_state, to_state, guard FROM fsm_transitions WHERE agent_id=?", (aid,))]
    out["secrets_md"] = row["secrets_md"]
    out["sheet_md"] = row["sheet_md"]
    out["drives_prose_md"] = row["drives_prose_md"]
    return out


def world_snapshot(conn, world_id, curtain=False):
    w = conn.execute("SELECT * FROM worlds WHERE id=?", (world_id,)).fetchone()
    if w is None:
        return None
    out = {"id": w["id"], "name": w["name"], "game": w["game"],
           "edition": w["edition"], "play_mode": w["play_mode"],
           "tone": w["tone"], "premise": w["premise"], "lethality": w["lethality"],
           "current_day": w["current_day"],
           "agent_count": conn.execute(
               "SELECT COUNT(*) c FROM agents WHERE world_id=?", (world_id,)).fetchone()["c"]}
    if curtain:
        out["gm_secrets_md"] = w["gm_secrets_md"]
    return out


def list_worlds(conn):
    return [{"id": r["id"], "name": r["name"], "game": r["game"],
             "current_day": r["current_day"],
             "agents": conn.execute("SELECT COUNT(*) c FROM agents WHERE world_id=?",
                                    (r["id"],)).fetchone()["c"]}
            for r in conn.execute("SELECT * FROM worlds ORDER BY id DESC")]


def map_data(conn, world_id):
    locs = [dict(r) for r in conn.execute(
        "SELECT id, name, description, x, y FROM locations WHERE world_id=?", (world_id,))]
    tokens = [{"id": r["id"], "name": r["name"],
               "display_name": r["display_name"] or r["name"],
               "living": bool(r["living"]), "salience": r["salience"],
               "location_id": r["location_id"], "kind": r["kind"]}
              for r in conn.execute("SELECT * FROM agents WHERE world_id=?", (world_id,))]
    return {"locations": locs, "agents": tokens}


def developments(conn, world_id, curtain=False, limit=80):
    q = "SELECT * FROM developments WHERE world_id=?"
    args = [world_id]
    if not curtain:
        q += " AND surface IN ('now','soon')"
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(q, args).fetchall()
    out = []
    for r in rows:
        tier = {"now": "public", "soon": "emerging", "hidden": "hidden"}.get(
            r["surface"], "hidden")
        out.append({"id": r["id"], "day": r["day"], "agent": r["agent"],
                    "headline": r["headline"], "body": r["body"],
                    "surface": r["surface"], "tier": tier,
                    "escalate": bool(r["escalate"]), "drained": bool(r["drained"]),
                    "source": r["source"], "arc": r["arc"]})
    return out


def ledgers(conn, world_id):
    """Control ledgers are GM-only — only ever returned behind the curtain."""
    leds = writer.load_ledgers(conn, world_id)
    return [{"entity": e, "total": l.total, "holder": l.holder,
             "phase": l.phase(), "standing": l.standing(),
             "control": l.control, "history": l.history[-6:]}
            for e, l in sorted(leds.items())]


def plots(conn, world_id, curtain=False):
    q = "SELECT * FROM plots WHERE world_id=?"
    if not curtain:
        q += " AND surface IN ('now','soon')"
    q += " ORDER BY id"
    return [dict(r) for r in conn.execute(q, (world_id,))]


def timeline(conn, world_id):
    return [dict(r) for r in conn.execute(
        "SELECT day, text FROM timeline WHERE world_id=? ORDER BY id DESC LIMIT 50",
        (world_id,))]


def cost_ledger(conn, world_id):
    return [dict(r) for r in conn.execute(
        "SELECT day, templated, sonnet_beats, opus_beats, notes, created_at "
        "FROM cost_ledger WHERE world_id=? ORDER BY id DESC LIMIT 50", (world_id,))]
