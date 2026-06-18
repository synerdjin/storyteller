"""Load agents from SQLite into the engine's `Agent`/`.fields` shape.

This is the adapter that lets the ported deterministic functions run unchanged:
it reassembles the structured child tables (resources, mood, relationships, FSM)
plus the agent columns into exactly the `.fields` dict that `drives.md`
front-matter produced in the original `Tools/` code.
"""

from __future__ import annotations

from ..engine.agent import Agent


def _fields_for(row, resources, mood, relationships, states):
    """Build the `.fields` dict mirroring parsed drives.md front-matter."""
    fields = {
        "living": bool(row["living"]),
        "state": row["state"],
        "clock": {"filled": row["clock_filled"], "total": row["clock_total"]},
        "advances_when": row["advances_when"],
        "salience": row["salience"],
    }
    if row["group_id"]:
        fields["group"] = row["group_id"]

    # goal: only include the keys that are set, matching the inline-map shape.
    goal = {}
    if row["goal_pursue"]:
        goal["pursue"] = row["goal_pursue"]
    if row["goal_target"]:
        goal["target"] = row["goal_target"]
    if row["goal_success"]:
        goal["success"] = row["goal_success"]
    if goal:
        fields["goal"] = goal

    if resources:
        fields["resources"] = resources
    if mood:
        fields["mood"] = mood
    if relationships:
        fields["relationships"] = relationships
    if states:
        fields["states"] = states
    return fields


def load_agents(conn, world_id, living_only=True):
    """Return [Agent] for a world, hydrated from all child tables."""
    q = "SELECT * FROM agents WHERE world_id = ?"
    if living_only:
        q += " AND living = 1"
    q += " ORDER BY name"
    rows = conn.execute(q, (world_id,)).fetchall()

    agents = []
    for row in rows:
        aid = row["id"]
        resources = {r["key"]: r["value"]
                     for r in conn.execute(
                         "SELECT key, value FROM agent_resources WHERE agent_id=?", (aid,))}
        mood = {r["key"]: r["value"]
                for r in conn.execute(
                    "SELECT key, value FROM agent_mood WHERE agent_id=?", (aid,))}
        relationships = {
            r["target_ref"]: {"tie": r["tie"], "weight": r["weight"],
                              **({"note": r["note"]} if r["note"] else {})}
            for r in conn.execute(
                "SELECT target_ref, tie, weight, note FROM relationships WHERE agent_id=?",
                (aid,))}
        states = {
            r["from_state"]: {"to": r["to_state"], "when": r["guard"]}
            for r in conn.execute(
                "SELECT from_state, to_state, guard FROM fsm_transitions WHERE agent_id=?",
                (aid,))}
        fields = _fields_for(row, resources, mood, relationships, states)
        agents.append(Agent(row["name"], fields, agent_id=aid))
    return agents
