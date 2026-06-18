"""Apply structured director/architect output to SQLite.

Bridges the JSON the model returns (directors/schemas.py) to the DB tables. This
is where the generative tier's *judgment* becomes durable world state — and where
we keep ids stable and the secrecy split intact (developments carry an honest
`surface`; the GM-only prose stays out of actor-safe columns).
"""

from __future__ import annotations

from ..db import writer


def apply_director_result(conn, world_id, result, day):
    """Apply a DIRECTOR_RESULT dict; return a counts summary."""
    ids = writer.name_to_id(conn, world_id)
    counts = {"developments": 0, "drive_edits": 0, "beliefs": 0,
              "memory": 0, "plots": 0}

    for dev in result.get("developments", []):
        writer.add_development(conn, world_id, {
            "day": day, "agent": dev.get("agent"), "headline": dev["headline"],
            "body": dev.get("body", ""), "surface": dev.get("surface", "soon"),
            "escalate": dev.get("escalate", False), "arc": dev.get("arc"),
            "source": "director", "drained": False,
        })
        counts["developments"] += 1

    for edit in result.get("drive_edits", []):
        aid = ids.get(edit.get("agent"))
        if aid is None:
            continue
        sets, vals = [], []
        for col, key in (("goal_pursue", "goal_pursue"), ("goal_target", "goal_target"),
                         ("goal_success", "goal_success"), ("state", "state"),
                         ("clock_filled", "clock_filled"), ("clock_total", "clock_total"),
                         ("salience", "salience")):
            if key in edit and edit[key] is not None:
                sets.append(f"{col}=?")
                vals.append(edit[key])
        if sets:
            vals.append(aid)
            conn.execute(f"UPDATE agents SET {', '.join(sets)} WHERE id=?", vals)
        for rc in edit.get("relationship_changes", []):
            conn.execute(
                "INSERT INTO relationships (agent_id, target_ref, tie, weight, note) "
                "VALUES (?,?,?,?,?) ON CONFLICT(agent_id, target_ref) "
                "DO UPDATE SET tie=excluded.tie, weight=excluded.weight, note=excluded.note",
                (aid, rc["target_ref"], rc["tie"], rc.get("weight", 0), rc.get("note")))
        counts["drive_edits"] += 1

    for b in result.get("beliefs", []):
        aid = ids.get(b.get("agent"))
        if aid is None:
            continue
        row = conn.execute("SELECT drives_prose_md FROM agents WHERE id=?", (aid,)).fetchone()
        prose = (row["drives_prose_md"] or "")
        line = f"\n- *[Day {day}]* belief: {b['belief']}"
        if "## Reflection notes" not in prose:
            prose += "\n\n## Reflection notes"
        conn.execute("UPDATE agents SET drives_prose_md=? WHERE id=?",
                     (prose + line, aid))
        counts["beliefs"] += 1

    for m in result.get("memory_entries", []):
        aid = ids.get(m.get("agent"))
        if aid is not None:
            writer.append_memory(conn, aid, day, m["text"])
            counts["memory"] += 1

    for p in result.get("plot_promotions", []):
        conn.execute(
            "INSERT INTO plots (world_id, plot_key, title, participants, stakes, "
            "state, surface, arc, body_md, opened_day) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(world_id, plot_key) DO UPDATE SET title=excluded.title, "
            "participants=excluded.participants, stakes=excluded.stakes, "
            "state=excluded.state, surface=excluded.surface, body_md=excluded.body_md",
            (world_id, p["plot_key"], p["title"], p.get("participants", ""),
             p.get("stakes", ""), p.get("state", "forming"),
             p.get("surface", "hidden"), p.get("arc"), p.get("body_md", ""), day))
        counts["plots"] += 1

    conn.commit()
    return counts


def seed_world(conn, result):
    """Create a whole world from an ARCHITECT_RESULT dict; return world_id."""
    w = result["world"]
    crossover = w.get("crossover")
    cur = conn.execute(
        "INSERT INTO worlds (name, game, edition, crossover, play_mode, tone, "
        "premise, lethality, calendar, current_day, gm_secrets_md) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (w["name"], w.get("game", "v20"), w.get("edition", "20th Anniversary"),
         crossover, w.get("play_mode", "dramatist"), w.get("tone", ""),
         w.get("premise", ""), w.get("lethality", "medium"), w.get("calendar", ""),
         1, w.get("gm_secrets_md", "")))
    wid = cur.lastrowid

    loc_ids = {}
    for loc in result.get("locations", []):
        lid = conn.execute(
            "INSERT INTO locations (world_id, name, description, x, y) VALUES (?,?,?,?,?)",
            (wid, loc["name"], loc.get("description", ""),
             loc.get("x", 0.5), loc.get("y", 0.5))).lastrowid
        loc_ids[loc["name"]] = lid

    for ag in result.get("agents", []):
        aid = conn.execute(
            "INSERT INTO agents (world_id, name, display_name, kind, living, state, "
            "clock_filled, clock_total, advances_when, salience, group_id, goal_pursue, "
            "goal_target, goal_success, location_id, profile_md, secrets_md, sheet_md, "
            "drives_prose_md) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wid, ag["name"], ag.get("display_name", ag["name"]),
             ag.get("kind", "npc"), 1, ag.get("state", "scheming"),
             ag.get("clock_filled", 0), ag.get("clock_total", 6),
             ag.get("advances_when", "dawdle"), ag.get("salience", 3),
             ag.get("group_id"), ag.get("goal_pursue"), ag.get("goal_target"),
             ag.get("goal_success"), loc_ids.get(ag.get("location")),
             ag.get("profile_md", ""), ag.get("secrets_md", ""),
             ag.get("sheet_md", ""), ag.get("drives_prose_md", ""))).lastrowid
        for kv in ag.get("resources", []):
            conn.execute("INSERT INTO agent_resources (agent_id, key, value) VALUES (?,?,?)",
                         (aid, kv["key"], kv["value"]))
        for kv in ag.get("mood", []):
            conn.execute("INSERT INTO agent_mood (agent_id, key, value) VALUES (?,?,?)",
                         (aid, kv["key"], kv["value"]))
        for r in ag.get("relationships", []):
            conn.execute(
                "INSERT OR IGNORE INTO relationships (agent_id, target_ref, tie, weight, note) "
                "VALUES (?,?,?,?,?)",
                (aid, r["target_ref"], r["tie"], r.get("weight", 0), r.get("note")))
        for s in ag.get("states", []):
            conn.execute(
                "INSERT OR IGNORE INTO fsm_transitions (agent_id, from_state, to_state, guard) "
                "VALUES (?,?,?,?)",
                (aid, s["from_state"], s["to_state"], s.get("guard", "always")))

    for p in result.get("plots", []):
        conn.execute(
            "INSERT INTO plots (world_id, plot_key, title, participants, stakes, "
            "state, surface, arc, body_md, opened_day) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (wid, p["plot_key"], p["title"], p.get("participants", ""),
             p.get("stakes", ""), p.get("state", "forming"),
             p.get("surface", "hidden"), p.get("arc"), p.get("body_md", ""), 1))

    conn.commit()
    return wid
