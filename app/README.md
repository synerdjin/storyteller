# Ant Farm — an observation sandbox for the living World of Darkness world

A standalone app that lifts the `storyteller` engine's **living-world substrate**
out of the GM loop and turns it into something you *watch* rather than play. No
player character: you observe a flat ensemble of living NPCs pursue goals and
collide on a map, advance time on demand, peek behind a curtain at their secrets,
and reach in with a "god hand" to perturb the world.

## Architecture

```
web/ (React + Vite)  ──HTTP/SSE──>  backend/ (FastAPI)
                                        ├── engine/        deterministic core (ported from Tools/)
                                        ├── directors/     generative tier (Anthropic SDK)
                                        ├── db/            SQLite runtime store
                                        └── orchestrator   tick_world: one deterministic beat
```

- **engine/** — the metronome, control ledger, social propagation, scribe, and
  dice/oracle, ported verbatim from `Tools/` onto a SQLite store. Proven
  byte-for-byte identical to the originals by `tests/test_parity.py`.
- **directors/** — the four subagents as Anthropic API calls returning *structured*
  edits (forced tool-use): Opus 4.8 pivot director + architect; Sonnet 4.6
  everyday director + blind npc-actor. The secrecy firewall is enforced at
  prompt-assembly: the actor is structurally blind.
- **db/** — SQLite schema, loader (rows → engine `Agent`), writer, demo seeder.

## Run the backend

```sh
pip install -r app/backend/requirements.txt
# from the repo root:
uvicorn app.backend.api.main:app --reload --port 8000
```

Seed a world with no API key (deterministic demo):

```sh
curl -X POST localhost:8000/api/worlds/demo
```

With `ANTHROPIC_API_KEY` set, `POST /api/worlds` runs the architect to generate a
fresh world, and ticks invoke the directors to narrate collisions/reflection.
Without a key the deterministic world still advances every tick — collisions are
detected and ledgers move; they just aren't narrated.

## Run the frontend

```sh
cd app/web
npm install
npm run dev            # proxies /api to localhost:8000
```

## Tests

```sh
python -m pytest app/backend/tests/ -q
```

The keystone is `test_parity.py`: it feeds identical agent state to both the
legacy `Tools/` code and the ported `engine/` and asserts identical output, so
the SQLite port provably preserved the engine's auditable fairness.

## The curtain

Default API responses are the **world-status / actor-safe** view: profiles but
not secrets, surfaced developments but not hidden causes, no ledger internals.
`?curtain=true` is the observer's omniscient peek. The split is enforced in
`api/queries.py`, not just the UI, so defaults can't leak. The curtain makes the
*observer* omniscient; the npc-actor stays blind regardless.
