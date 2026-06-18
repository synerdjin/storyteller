"""FastAPI app for the Ant Farm — observe + god-hand over a living world.

Reads go through queries.py (curtain enforced at the data layer). The tick
endpoint streams its work over SSE: the deterministic beat first, then each
director pass, so the observer watches Opus think instead of staring at a spinner.
The god-hand lets the observer perturb the world; the next tick carries the
ripples. The npc-actor voicing stays structurally blind.
"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..db.database import get_db
from ..db import seed as seed_mod
from ..db import loader
from ..engine import social
from .. import orchestrator
from ..directors import client as dclient
from . import queries

app = FastAPI(title="Ant Farm", version="0.1")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def db():
    return get_db()


# ── world lifecycle ──────────────────────────────────────────────────────────

class SeedParams(BaseModel):
    game: str = "v20"
    edition: str = "20th Anniversary"
    tone: str = ""
    premise: str = ""
    lethality: str = "medium"
    play_mode: str = "dramatist"
    crossover: str | None = None
    npc_count: int = 6
    collision_count: int = 3
    location_count: int = 5
    faction_count: int = 2
    loud_count: int = 2


@app.get("/api/status")
def status():
    return {"ok": True, "directors_available": dclient.available()}


@app.get("/api/worlds")
def worlds():
    return queries.list_worlds(db())


@app.post("/api/worlds/demo")
def create_demo():
    conn = db()
    wid = seed_mod.seed_demo_world(conn)
    return {"world_id": wid, "snapshot": queries.world_snapshot(conn, wid)}


@app.post("/api/worlds")
def create_world(params: SeedParams):
    if not dclient.available():
        raise HTTPException(
            503, "The architect needs an ANTHROPIC_API_KEY. Use POST /api/worlds/demo "
                 "to seed a deterministic demo world without one.")
    from ..directors import architect
    conn = db()
    try:
        out = architect.seed(conn, params.model_dump())
    except dclient.DirectorError as e:
        raise HTTPException(503, str(e))
    out["snapshot"] = queries.world_snapshot(conn, out["world_id"])
    return out


@app.get("/api/worlds/{world_id}")
def world(world_id: int, curtain: bool = Query(False)):
    snap = queries.world_snapshot(db(), world_id, curtain)
    if snap is None:
        raise HTTPException(404, "no such world")
    return snap


@app.get("/api/worlds/{world_id}/agents")
def world_agents(world_id: int):
    return queries.list_agents(db(), world_id)


@app.get("/api/worlds/{world_id}/map")
def world_map(world_id: int):
    return queries.map_data(db(), world_id)


@app.get("/api/agents/{agent_id}")
def agent(agent_id: int, curtain: bool = Query(False)):
    out = queries.agent_detail(db(), agent_id, curtain)
    if out is None:
        raise HTTPException(404, "no such agent")
    return out


@app.get("/api/worlds/{world_id}/developments")
def world_developments(world_id: int, curtain: bool = Query(False)):
    return queries.developments(db(), world_id, curtain)


@app.get("/api/worlds/{world_id}/ledgers")
def world_ledgers(world_id: int, curtain: bool = Query(False)):
    if not curtain:
        # ledgers are entirely GM-only; only visible behind the curtain
        return {"curtained": True, "ledgers": []}
    return {"curtained": False, "ledgers": queries.ledgers(db(), world_id)}


@app.get("/api/worlds/{world_id}/plots")
def world_plots(world_id: int, curtain: bool = Query(False)):
    return queries.plots(db(), world_id, curtain)


@app.get("/api/worlds/{world_id}/timeline")
def world_timeline(world_id: int):
    return queries.timeline(db(), world_id)


@app.get("/api/worlds/{world_id}/cost")
def world_cost(world_id: int):
    return queries.cost_ledger(db(), world_id)


# ── the tick (SSE) ───────────────────────────────────────────────────────────

class TickParams(BaseModel):
    elapsed: int = 1
    dawdle: bool = False
    fail: bool = False
    max_n: int = 3
    run_directors: bool = True


def _sse(event, payload):
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@app.post("/api/worlds/{world_id}/tick")
def tick(world_id: int, params: TickParams):
    def gen():
        conn = db()
        try:
            result = orchestrator.tick_world(
                conn, world_id, elapsed=params.elapsed, dawdle=params.dawdle,
                fail=params.fail, max_n=params.max_n)
        except ValueError as e:
            yield _sse("error", {"message": str(e)})
            return
        yield _sse("deterministic", result)

        manifest = result["manifest"]
        has_work = (manifest.get("collisions") or manifest.get("reflection")
                    or manifest.get("pivotal_movers"))
        if not (params.run_directors and has_work):
            yield _sse("done", {"directors": "skipped (nothing to deliberate)"})
            return
        if not dclient.available():
            yield _sse("directors_unavailable",
                       {"message": "No ANTHROPIC_API_KEY — collisions and reflection "
                                   "were detected but not narrated. The deterministic "
                                   "world still advanced.",
                        "pending": manifest})
            yield _sse("done", {"directors": "unavailable"})
            return

        yield _sse("director_start", {"collisions": len(manifest["collisions"]),
                                      "reflection": len(manifest["reflection"])})
        from ..directors import director
        from ..db import writer
        try:
            report = director.run_world_directors(conn, world_id, manifest, result["day"])
            writer.add_cost(conn, world_id, result["day"],
                            sonnet=report["sonnet_beats"], opus=report["opus_beats"],
                            notes="director passes")
            yield _sse("director_done", report)
            yield _sse("surfaced", queries.developments(conn, world_id, curtain=False, limit=20))
        except dclient.DirectorError as e:
            yield _sse("error", {"message": str(e)})
        yield _sse("done", {"ok": True})

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── god-hand ─────────────────────────────────────────────────────────────────

class Intervention(BaseModel):
    action: str                         # inject_event | nudge | whisper_goal | move
    agent: str | None = None
    location_id: int | None = None
    headline: str | None = None
    body: str | None = None
    mood_delta: dict | None = None      # {key: +/-N}
    clock_delta: int | None = None
    salience: int | None = None
    kill: bool | None = None
    pursue: str | None = None
    target: str | None = None
    success: str | None = None


@app.post("/api/worlds/{world_id}/intervene")
def intervene(world_id: int, iv: Intervention):
    conn = db()
    day = conn.execute("SELECT current_day FROM worlds WHERE id=?",
                       (world_id,)).fetchone()
    if day is None:
        raise HTTPException(404, "no such world")
    day = day["current_day"]

    if iv.action == "inject_event":
        if not iv.headline:
            raise HTTPException(400, "inject_event needs a headline")
        from ..db import writer
        writer.add_development(conn, world_id, {
            "day": day, "agent": iv.agent, "headline": iv.headline,
            "body": iv.body or "", "surface": "now", "escalate": False,
            "source": "god-hand", "drained": False, "arc": iv.agent})
        # propagate an actor-safe rumor (firewalled) if it names a participant
        propagated = 0
        if iv.agent:
            agents = loader.load_agents(conn, world_id, living_only=True)
            obs, _ = social.propagate(
                agents, [{"participants": [iv.agent], "headline": iv.headline, "day": day}])
            propagated = writer.add_observations(conn, world_id, obs)
        return {"ok": True, "propagated": propagated}

    if iv.action in ("nudge", "whisper_goal", "move"):
        if not iv.agent:
            raise HTTPException(400, f"{iv.action} needs an agent")
        row = conn.execute("SELECT id FROM agents WHERE world_id=? AND name=?",
                           (world_id, iv.agent)).fetchone()
        if row is None:
            raise HTTPException(404, f"no agent {iv.agent}")
        aid = row["id"]

        if iv.action == "nudge":
            if iv.kill:
                conn.execute("UPDATE agents SET living=0 WHERE id=?", (aid,))
            if iv.salience is not None:
                conn.execute("UPDATE agents SET salience=? WHERE id=?", (iv.salience, aid))
            if iv.clock_delta:
                conn.execute(
                    "UPDATE agents SET clock_filled=MAX(0, MIN(clock_total, "
                    "clock_filled + ?)) WHERE id=?", (iv.clock_delta, aid))
            for k, dv in (iv.mood_delta or {}).items():
                conn.execute(
                    "INSERT INTO agent_mood (agent_id, key, value) VALUES (?,?,?) "
                    "ON CONFLICT(agent_id, key) DO UPDATE SET "
                    "value = MAX(0, MIN(5, value + ?))", (aid, k, max(0, min(5, dv)), dv))
        elif iv.action == "whisper_goal":
            sets, vals = [], []
            for col, v in (("goal_pursue", iv.pursue), ("goal_target", iv.target),
                           ("goal_success", iv.success)):
                if v is not None:
                    sets.append(f"{col}=?")
                    vals.append(v)
            if sets:
                vals.append(aid)
                conn.execute(f"UPDATE agents SET {', '.join(sets)} WHERE id=?", vals)
        elif iv.action == "move":
            conn.execute("UPDATE agents SET location_id=? WHERE id=?",
                         (iv.location_id, aid))
        conn.commit()
        return {"ok": True}

    raise HTTPException(400, f"unknown action {iv.action!r}")


# ── voice an NPC (blind actor) ───────────────────────────────────────────────

class VoiceRequest(BaseModel):
    scene: str = ""
    says: str = ""


@app.post("/api/worlds/{world_id}/agents/{name}/voice")
def voice(world_id: int, name: str, req: VoiceRequest):
    if not dclient.available():
        raise HTTPException(503, "Voicing needs an ANTHROPIC_API_KEY.")
    from ..directors import actor
    conn = db()
    day = conn.execute("SELECT current_day FROM worlds WHERE id=?",
                       (world_id,)).fetchone()
    if day is None:
        raise HTTPException(404, "no such world")
    try:
        line = actor.voice_npc(conn, world_id, name, req.scene, req.says,
                               day["current_day"])
    except (ValueError, dclient.DirectorError) as e:
        raise HTTPException(400, str(e))
    return {"name": name, "line": line}
