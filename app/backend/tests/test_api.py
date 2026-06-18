"""API integration test via FastAPI TestClient (no API key required).

Exercises the full read/observe/god-hand surface against a demo world, and
asserts the curtain genuinely gates secrets at the HTTP layer.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# isolate the DB to a temp file before importing the app
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["ANTFARM_DB"] = _tmp.name

from fastapi.testclient import TestClient        # noqa: E402
from app.backend.api.main import app             # noqa: E402

client = TestClient(app)


def _demo():
    return client.post("/api/worlds/demo").json()["world_id"]


def test_status_and_seed():
    s = client.get("/api/status").json()
    assert s["ok"] is True
    wid = _demo()
    snap = client.get(f"/api/worlds/{wid}").json()
    assert snap["game"] == "v20" and snap["agent_count"] == 4
    # gm_secrets hidden by default, visible behind curtain
    assert "gm_secrets_md" not in snap
    cur = client.get(f"/api/worlds/{wid}?curtain=true").json()
    assert "torpor" in cur["gm_secrets_md"]


def test_curtain_gates_agent_secrets():
    wid = _demo()
    agents = client.get(f"/api/worlds/{wid}/agents").json()
    mara = next(a for a in agents if a["name"] == "mara")
    # public view: profile yes, secrets/goal no
    pub = client.get(f"/api/agents/{mara['id']}").json()
    assert "Salt Quarter" in pub["profile_md"]
    assert pub["curtained"] is True
    assert "goal" not in pub and "secrets_md" not in pub
    # behind the curtain: the whole mind
    priv = client.get(f"/api/agents/{mara['id']}?curtain=true").json()
    assert priv["curtained"] is False
    assert priv["goal"]["target"] == "council-seat"
    assert "murdered" in priv["secrets_md"]
    assert any(r["target_ref"] == "vance" for r in priv["relationships"])


def test_map_and_tick_and_ledger():
    wid = _demo()
    mp = client.get(f"/api/worlds/{wid}/map").json()
    assert len(mp["locations"]) == 4 and len(mp["agents"]) == 4

    # tick via SSE (directors skipped without a key) — collect the stream text
    with client.stream("POST", f"/api/worlds/{wid}/tick",
                       json={"elapsed": 1}) as r:
        body = "".join(chunk for chunk in r.iter_text())
    assert "event: deterministic" in body
    # mara & vance both advance (always) and collide over council-seat
    assert "council-seat" in body
    assert "directors_unavailable" in body or "director" in body

    # the campaign day advanced
    snap = client.get(f"/api/worlds/{wid}").json()
    assert snap["current_day"] == 6

    # ledger opened, GM-only: empty without curtain, populated with it
    assert client.get(f"/api/worlds/{wid}/ledgers").json()["ledgers"] == []
    led = client.get(f"/api/worlds/{wid}/ledgers?curtain=true").json()["ledgers"]
    assert any(l["entity"] == "council-seat" for l in led)

    # developments surfaced (public tier) — and no secret leaked into them
    devs = client.get(f"/api/worlds/{wid}/developments").json()
    assert all(d["tier"] in ("public", "emerging") for d in devs)
    assert all("swing vote" not in d["body"] for d in devs)


def test_godhand():
    wid = _demo()
    # inject an event naming mara → propagates an actor-safe rumor to her ally
    r = client.post(f"/api/worlds/{wid}/intervene", json={
        "action": "inject_event", "agent": "mara",
        "headline": "A fire broke out in the Salt Quarter",
        "body": "Smoke over the brokers' row at dusk."}).json()
    assert r["ok"] is True
    devs = client.get(f"/api/worlds/{wid}/developments").json()
    assert any("fire broke out" in d["headline"] for d in devs)

    # whisper a new goal, then confirm it behind the curtain
    agents = client.get(f"/api/worlds/{wid}/agents").json()
    vance = next(a for a in agents if a["name"] == "vance")
    client.post(f"/api/worlds/{wid}/intervene", json={
        "action": "whisper_goal", "agent": "vance",
        "pursue": "destroy", "target": "mara"})
    priv = client.get(f"/api/agents/{vance['id']}?curtain=true").json()
    assert priv["goal"]["pursue"] == "destroy" and priv["goal"]["target"] == "mara"

    # kill an agent (god-hand), confirm it's no longer living
    client.post(f"/api/worlds/{wid}/intervene", json={"action": "nudge",
                                                      "agent": "calla", "kill": True})
    agents2 = client.get(f"/api/worlds/{wid}/agents").json()
    calla = next(a for a in agents2 if a["name"] == "calla")
    assert calla["living"] is False


if __name__ == "__main__":
    test_status_and_seed()
    test_curtain_gates_agent_secrets()
    test_map_and_tick_and_ledger()
    test_godhand()
    print("api self-test: OK")
