"""Director-tier tests that need no API key (stub the model, exercise apply + firewall).

- the npc-actor briefing must never contain secret data (the firewall's sharp end)
- apply_director_result must write developments/edits/beliefs/memory/plots
- seed_world must materialize a whole world from an ARCHITECT_RESULT dict
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.backend.db.database import get_db          # noqa: E402
from app.backend.directors import apply, actor, client  # noqa: E402


def test_actor_firewall_excludes_secrets(monkeypatch):
    conn = get_db(":memory:")
    wid = conn.execute("INSERT INTO worlds (name, gm_secrets_md) VALUES (?,?)",
                       ("W", "GM ONLY: the prince is dead")).lastrowid
    aid = conn.execute(
        "INSERT INTO agents (world_id, name, display_name, state, salience, "
        "profile_md, secrets_md, sheet_md, drives_prose_md) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (wid, "mara", "Mara Vex", "scheming", 4,
         "Mara is a sharp-tongued broker who runs the Salt Quarter.",
         "SECRET: Mara murdered her sire and hid the body in the cistern.",
         "SHEET: Dominate 4, Potence 2.",
         "DRIVES: pursue control of the council; success = the swing vote.")).lastrowid
    conn.execute("INSERT INTO memory_log (agent_id, day, text) VALUES (?,?,?)",
                 (aid, 3, "Met the new arrival at the docks."))
    conn.commit()

    captured = {}

    def fake_text_call(system, user, **kw):
        captured["system"] = system
        captured["user"] = user
        return "I don't know what you're talking about. Move along."

    monkeypatch.setattr(client, "text_call", fake_text_call)
    line = actor.voice_npc(conn, wid, "mara", "The cistern at midnight.",
                           "Where is your sire?", day=5)
    assert "Move along" in line

    blob = captured["system"] + "\n" + captured["user"]
    # the firewall: none of the GM-only material may appear in the actor's prompt
    assert "murdered her sire" not in blob
    assert "cistern in" not in blob.lower() or "cistern at midnight" in blob  # scene ok, secret not
    assert "Dominate 4" not in blob
    assert "swing vote" not in blob
    assert "prince is dead" not in blob
    # but actor-safe material IS present
    assert "Salt Quarter" in blob
    assert "Met the new arrival at the docks" in blob


def test_apply_director_result():
    conn = get_db(":memory:")
    wid = conn.execute("INSERT INTO worlds (name, current_day) VALUES (?,?)",
                       ("W", 7)).lastrowid
    conn.execute(
        "INSERT INTO agents (world_id, name, state, salience, goal_pursue, goal_target) "
        "VALUES (?,?,?,?,?,?)", (wid, "vance", "scheming", 3, "control", "docks"))
    conn.commit()

    result = {
        "summary": "Vance lost the docks and turns vindictive.",
        "developments": [{"agent": "vance", "headline": "Vance routed at the docks",
                          "body": "His muscle scattered before dawn.", "surface": "soon"}],
        "drive_edits": [{"agent": "vance", "goal_pursue": "destroy",
                         "salience": 5,
                         "relationship_changes": [{"target_ref": "mara", "tie": "grudge",
                                                   "weight": -5, "note": "humiliated me"}]}],
        "beliefs": [{"agent": "vance", "belief": "Mara will never yield without blood."}],
        "memory_entries": [{"agent": "vance", "text": "They took the docks from me."}],
        "plot_promotions": [{"plot_key": "docks-war", "title": "The War for the Docks",
                             "state": "rising", "surface": "soon"}],
    }
    counts = apply.apply_director_result(conn, wid, result, day=7)
    assert counts == {"developments": 1, "drive_edits": 1, "beliefs": 1,
                      "memory": 1, "plots": 1}

    v = conn.execute("SELECT goal_pursue, salience FROM agents WHERE name='vance'").fetchone()
    assert v["goal_pursue"] == "destroy" and v["salience"] == 5
    rel = conn.execute("SELECT tie, weight FROM relationships WHERE target_ref='mara'").fetchone()
    assert rel["tie"] == "grudge" and rel["weight"] == -5
    prose = conn.execute("SELECT drives_prose_md FROM agents WHERE name='vance'").fetchone()
    assert "never yield without blood" in prose["drives_prose_md"]
    plot = conn.execute("SELECT state FROM plots WHERE plot_key='docks-war'").fetchone()
    assert plot["state"] == "rising"


def test_seed_world():
    conn = get_db(":memory:")
    result = {
        "world": {"name": "Harbor of Ash", "game": "v20", "tone": "noir",
                  "gm_secrets_md": "The prince is already dead."},
        "locations": [{"name": "The Harbor", "x": 0.3, "y": 0.4},
                      {"name": "The Court", "x": 0.7, "y": 0.6}],
        "agents": [
            {"name": "mara", "kind": "npc", "state": "scheming", "salience": 4,
             "goal_pursue": "control", "goal_target": "court", "location": "The Court",
             "profile_md": "A broker.", "secrets_md": "Killed her sire.",
             "resources": [{"key": "secrets", "value": 4}],
             "mood": [{"key": "confidence", "value": 3}],
             "relationships": [{"target_ref": "vance", "tie": "rival", "weight": -4}],
             "states": [{"from_state": "scheming", "to_state": "moving", "guard": "clock>=3"}]},
            {"name": "vance", "kind": "npc", "state": "scheming", "salience": 3,
             "goal_pursue": "control", "goal_target": "court", "location": "The Harbor",
             "profile_md": "A brute."},
        ],
        "plots": [{"plot_key": "the-seat", "title": "The Empty Seat", "state": "forming"}],
        "spoiler_free_summary": "Two rivals circle a contested court.",
    }
    wid = apply.seed_world(conn, result)
    assert conn.execute("SELECT COUNT(*) c FROM agents WHERE world_id=?", (wid,)).fetchone()["c"] == 2
    assert conn.execute("SELECT COUNT(*) c FROM locations WHERE world_id=?", (wid,)).fetchone()["c"] == 2
    # the shared-target collision is wired: both reach for 'court'
    targets = [r["goal_target"] for r in conn.execute(
        "SELECT goal_target FROM agents WHERE world_id=?", (wid,))]
    assert targets.count("court") == 2
    res = conn.execute("SELECT value FROM agent_resources WHERE key='secrets'").fetchone()
    assert res["value"] == 4


if __name__ == "__main__":
    # minimal monkeypatch shim so this runs without pytest
    class _MP:
        def setattr(self, obj, name, val):
            setattr(obj, name, val)
    test_actor_firewall_excludes_secrets(_MP())
    test_apply_director_result()
    test_seed_world()
    print("directors self-test: OK")
