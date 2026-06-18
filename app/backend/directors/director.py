"""The world directors — resolve the metronome's hand-off manifest with judgment.

Everyday collisions/reflection go to the Sonnet `world-director-lite`; anything
it flags (or a caller marks) as secret-bearing escalates to the Opus
`world-director`. Both are GM-side and secret-aware — their briefings include the
involved agents' secrets/drives/sheet and the world's gm-secrets — because their
whole job is advancing hidden agendas. The output is structured (applied via
apply.py); nothing here is shown to the observer except the curated developments.
"""

from __future__ import annotations

from . import client, prompts, apply
from .schemas import DIRECTOR_RESULT


def _agent_brief(conn, world_id, name):
    """Full GM-side dossier for one agent (secrets included — director is trusted)."""
    row = conn.execute("SELECT * FROM agents WHERE world_id=? AND name=?",
                       (world_id, name)).fetchone()
    if row is None:
        return None
    aid = row["id"]
    res = {r["key"]: r["value"] for r in conn.execute(
        "SELECT key, value FROM agent_resources WHERE agent_id=?", (aid,))}
    mood = {r["key"]: r["value"] for r in conn.execute(
        "SELECT key, value FROM agent_mood WHERE agent_id=?", (aid,))}
    rels = [dict(r) for r in conn.execute(
        "SELECT target_ref, tie, weight, note FROM relationships WHERE agent_id=?", (aid,))]
    mem = [r["text"] for r in conn.execute(
        "SELECT text FROM memory_log WHERE agent_id=? ORDER BY id DESC LIMIT 8", (aid,))]
    obs = [r["text"] for r in conn.execute(
        "SELECT text FROM memory_observations WHERE agent_id=? ORDER BY id DESC LIMIT 8", (aid,))]
    return {
        "name": row["name"], "state": row["state"],
        "clock": f"{row['clock_filled']}/{row['clock_total']}",
        "salience": row["salience"], "group": row["group_id"],
        "goal": {"pursue": row["goal_pursue"], "target": row["goal_target"],
                 "success": row["goal_success"]},
        "resources": res, "mood": mood, "relationships": rels,
        "profile": row["profile_md"], "secrets": row["secrets_md"],
        "sheet": row["sheet_md"], "drives_prose": row["drives_prose_md"],
        "recent_memory": mem, "recent_observations": obs,
    }


def _involved_names(manifest):
    names = set(manifest.get("reflection", [])) | set(manifest.get("pivotal_movers", []))
    for c in manifest.get("collisions", []):
        names.add(c.get("a"))
        if c.get("b"):
            names.add(c.get("b"))
    return {n for n in names if n}


def _briefing(conn, world_id, manifest, day):
    world = conn.execute("SELECT name, game, play_mode, tone, gm_secrets_md "
                         "FROM worlds WHERE id=?", (world_id,)).fetchone()
    agents = {n: _agent_brief(conn, world_id, n) for n in _involved_names(manifest)}
    return {
        "current_day": day,
        "world": {"name": world["name"], "game": world["game"],
                  "play_mode": world["play_mode"], "tone": world["tone"]},
        "gm_secrets": world["gm_secrets_md"],
        "collisions": manifest.get("collisions", []),
        "reflection": manifest.get("reflection", []),
        "pivotal_movers": manifest.get("pivotal_movers", []),
        "agents": {k: v for k, v in agents.items() if v},
    }


def run_director(conn, world_id, manifest, day, *, opus=False):
    """Run one director pass over a manifest; apply edits; return (result, counts)."""
    system = prompts.DIRECTOR_OPUS if opus else prompts.DIRECTOR_LITE
    model = client.MODEL_OPUS if opus else client.MODEL_SONNET
    brief = _briefing(conn, world_id, manifest, day)
    user = ("Resolve this tick's hand-off. Honor the fixed ledger numbers; resolve "
            "uncertainty honestly; keep secrets out of `developments`.\n\n"
            + client.dumps(brief))
    result = client.structured_call(
        system, user, "world_update", DIRECTOR_RESULT,
        model=model, max_tokens=8000,
        tool_description="The structured world update to apply this tick.")
    counts = apply.apply_director_result(conn, world_id, result, day)
    return result, counts


def run_world_directors(conn, world_id, manifest, day):
    """Lite pass, then an Opus pass over anything it escalated. Returns a report."""
    report = {"lite": None, "opus": None, "sonnet_beats": 0, "opus_beats": 0}
    has_work = (manifest.get("collisions") or manifest.get("reflection")
                or manifest.get("pivotal_movers"))
    if not has_work:
        return report

    lite_result, lite_counts = run_director(conn, world_id, manifest, day, opus=False)
    report["lite"] = {"summary": lite_result.get("summary"), "counts": lite_counts}
    report["sonnet_beats"] = 1

    escalated = lite_result.get("escalate_to_opus") or []
    pivots = manifest.get("pivotal_movers") or []
    if escalated or pivots:
        opus_manifest = {
            "collisions": [c for c in manifest.get("collisions", [])
                           if any(e in (c.get("a"), c.get("b"), c.get("over"))
                                  for e in escalated)],
            "reflection": [],
            "pivotal_movers": pivots,
            "escalated_notes": escalated,
        }
        opus_result, opus_counts = run_director(conn, world_id, opus_manifest, day, opus=True)
        report["opus"] = {"summary": opus_result.get("summary"), "counts": opus_counts}
        report["opus_beats"] = 1

    return report
