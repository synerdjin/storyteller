"""The npc-actor — voices one NPC, structurally blind to everything secret.

This is the firewall's sharp end. The actor's prompt is assembled ONLY from
actor-safe columns: the agent's `profile_md`, their own `memory_log`, and the
`memory_observations` propagated to them. It NEVER sees `secrets_md`,
`drives_*`, `sheet_md`, another agent's data, or the world's `gm_secrets_md`.
The curtain may make the *observer* omniscient, but the actor stays blind — so a
voiced line can never leak what the character couldn't know.
"""

from __future__ import annotations

from . import client, prompts


def voice_npc(conn, world_id, name, scene, says, day):
    """Voice `name` replying to `says` in `scene`. Returns the character's words.

    Assembles only actor-safe data. Raises if the agent doesn't exist.
    """
    row = conn.execute(
        "SELECT id, display_name, profile_md FROM agents WHERE world_id=? AND name=?",
        (world_id, name)).fetchone()
    if row is None:
        raise ValueError(f"no agent {name!r} in world {world_id}")
    aid = row["id"]

    memory = [r["text"] for r in conn.execute(
        "SELECT text FROM memory_log WHERE agent_id=? ORDER BY id DESC LIMIT 12", (aid,))]
    observations = [r["text"] for r in conn.execute(
        "SELECT text FROM memory_observations WHERE agent_id=? ORDER BY id DESC LIMIT 12",
        (aid,))]

    # NOTE: deliberately NO secrets_md / drives_prose_md / sheet_md / gm_secrets
    # read here. That omission is the firewall.
    parts = [
        f"It is now Day {day}.",
        f"YOU ARE: {row['display_name'] or name}",
        "",
        "YOUR PROFILE (all you are and openly know):",
        row["profile_md"] or "(a sketch — improvise within it)",
    ]
    if memory:
        parts += ["", "YOUR MEMORY (your own history, most recent first):",
                  *[f"- {m}" for m in memory]]
    if observations:
        parts += ["", "WHAT YOU'VE HEARD ABOUT OTHERS:",
                  *[f"- {o}" for o in observations]]
    parts += ["", "THE SCENE:", scene or "(quiet)",
              "", "SOMEONE SAYS TO YOU:", says or "(they wait for you to speak)",
              "", "Reply as your character, and only your character."]

    return client.text_call(prompts.NPC_ACTOR, "\n".join(parts),
                            model=client.MODEL_SONNET, max_tokens=1200)
