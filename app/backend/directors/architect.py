"""The campaign-architect — seeds a whole living, colliding world from a brief.

Given the wizard's parameters (game/tone/premise + the tunable counts: NPCs,
collisions, locations, factions, loud starters), it returns a complete world —
cast with full agent models pointed at shared targets, locations with map
coordinates, plots, and GM secrets — which seed_world() writes to SQLite.
"""

from __future__ import annotations

from . import client, prompts, apply
from .schemas import ARCHITECT_RESULT


def _brief(params):
    return {
        "game": params.get("game", "v20"),
        "edition": params.get("edition", "20th Anniversary"),
        "crossover": params.get("crossover"),
        "tone": params.get("tone", ""),
        "premise": params.get("premise", ""),
        "lethality": params.get("lethality", "medium"),
        "play_mode": params.get("play_mode", "dramatist"),
        "counts": {
            "npcs": int(params.get("npc_count", 6)),
            "latent_collisions": int(params.get("collision_count", 3)),
            "locations": int(params.get("location_count", 5)),
            "factions": int(params.get("faction_count", 2)),
            "loud_starters": int(params.get("loud_count", 2)),
        },
    }


def seed(conn, params):
    """Generate and persist a new world; return {world_id, summary}."""
    brief = _brief(params)
    user = ("Seed a complete living World of Darkness ant-farm world to these "
            "parameters. Hit the requested counts exactly; point at least "
            f"{brief['counts']['latent_collisions']} agent pairs at shared targets "
            "with opposed aims so plots emerge immediately.\n\n"
            + client.dumps(brief))
    result = client.structured_call(
        prompts.ARCHITECT, user, "seed_world", ARCHITECT_RESULT,
        model=client.MODEL_OPUS, max_tokens=16000,
        tool_description="The complete seeded world to create.")
    world_id = apply.seed_world(conn, result)
    return {
        "world_id": world_id,
        "summary": result.get("spoiler_free_summary", ""),
        "agents": len(result.get("agents", [])),
        "locations": len(result.get("locations", [])),
        "plots": len(result.get("plots", [])),
    }
