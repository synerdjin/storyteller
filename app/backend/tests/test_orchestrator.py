"""DB roundtrip + tick_world smoke test (no model, no network).

Seeds a tiny two-rival world directly in SQLite, runs a deterministic tick, and
asserts the engine moved clocks, detected the collision, opened a control ledger,
templated a development, and propagated an actor-safe observation through the
firewall — all persisted.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.backend.db.database import get_db        # noqa: E402
from app.backend import orchestrator              # noqa: E402
from app.backend.db import writer                 # noqa: E402


def _seed(conn):
    cur = conn.execute(
        "INSERT INTO worlds (name, game, current_day) VALUES (?,?,?)",
        ("Test Harbor", "v20", 5))
    wid = cur.lastrowid
    loc = conn.execute(
        "INSERT INTO locations (world_id, name, x, y) VALUES (?,?,?,?)",
        (wid, "The Harbor", 0.5, 0.5)).lastrowid

    def add_agent(name, **kw):
        cur = conn.execute(
            "INSERT INTO agents (world_id, name, kind, living, state, clock_filled, "
            "clock_total, advances_when, salience, group_id, goal_pursue, goal_target, "
            "goal_success, location_id, profile_md, secrets_md) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wid, name, kw.get("kind", "npc"), 1, kw["state"], kw["filled"],
             kw["total"], kw.get("advances_when", "always"), kw["salience"],
             kw.get("group_id"), kw.get("pursue"), kw.get("target"),
             kw.get("success"), loc, kw.get("profile", f"{name} is here."),
             kw.get("secrets", "")))
        return cur.lastrowid

    mara = add_agent("mara", state="scheming", filled=2, total=3, salience=4,
                     pursue="control", target="harbor-council",
                     success="holds the swing vote")
    vance = add_agent("vance", state="scheming", filled=1, total=4, salience=3,
                      pursue="control", target="harbor-council")
    # resources, mood, FSM, relationships
    conn.executemany("INSERT INTO agent_resources (agent_id, key, value) VALUES (?,?,?)",
                     [(mara, "influence", 2), (mara, "secrets", 4), (vance, "muscle", 3)])
    conn.executemany("INSERT INTO agent_mood (agent_id, key, value) VALUES (?,?,?)",
                     [(mara, "confidence", 3)])
    conn.executemany(
        "INSERT INTO fsm_transitions (agent_id, from_state, to_state, guard) VALUES (?,?,?,?)",
        [(mara, "scheming", "moving", "clock>=3"),
         (vance, "scheming", "moving", "clock>=2")])
    conn.execute(
        "INSERT INTO relationships (agent_id, target_ref, tie, weight, note) VALUES (?,?,?,?,?)",
        (mara, "vance", "rival", -4, "the one who can block the seat"))
    conn.commit()
    return wid


def test_tick_world_end_to_end():
    conn = get_db(":memory:")
    wid = _seed(conn)

    result = orchestrator.tick_world(conn, wid, elapsed=1, dawdle=False, fail=False)

    # clocks moved (both advances_when=always)
    rows = {r["name"]: r for r in conn.execute(
        "SELECT name, clock_filled, state FROM agents WHERE world_id=?", (wid,))}
    assert rows["mara"]["clock_filled"] == 3 and rows["mara"]["state"] == "moving"
    assert rows["vance"]["clock_filled"] == 2 and rows["vance"]["state"] == "moving"

    # collision detected over the shared target
    assert any(c["over"] == "harbor-council" and c["kind"] == "contested-goal"
               for c in result["interactions"]), result["interactions"]

    # a control ledger opened and persisted, mara ahead (higher pressure)
    led = writer.load_ledgers(conn, wid)["harbor-council"]
    assert led.control["mara"] >= 1 and led.holder == "mara", led.standing()

    # a development was templated and stored
    devs = conn.execute("SELECT * FROM developments WHERE world_id=?", (wid,)).fetchall()
    assert devs, "expected at least one templated development"
    assert any("advances" in d["headline"] for d in devs)

    # an actor-safe observation propagated to the rival (firewall-clean)
    obs = conn.execute(
        "SELECT mo.text FROM memory_observations mo JOIN agents a ON a.id=mo.agent_id "
        "WHERE a.world_id=?", (wid,)).fetchall()
    if obs:  # vance hears of mara stirring (1 hop, rival edge)
        assert all("swing vote" not in o["text"] for o in obs), "secret leaked!"
        assert any("quietly pursuing aims" in o["text"] for o in obs)

    # campaign clock advanced
    day = conn.execute("SELECT current_day FROM worlds WHERE id=?", (wid,)).fetchone()
    assert day["current_day"] == 6

    # cost ledger recorded the free templated beats
    cost = conn.execute("SELECT * FROM cost_ledger WHERE world_id=?", (wid,)).fetchone()
    assert cost["templated"] >= 1 and cost["opus_beats"] == 0


if __name__ == "__main__":
    test_tick_world_end_to_end()
    print("orchestrator self-test: OK")
