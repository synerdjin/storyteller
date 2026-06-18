"""JSON Schemas for the director/architect structured (tool-use) outputs.

These are the machine-applicable contracts that replace the original subagents'
markdown editing: a director returns edits the backend validates and writes to
the DB; the architect returns a whole seeded world. Dict-shaped sub-objects
(resources, mood) are expressed as {key,value} arrays so the schema stays strict
JSON Schema (no arbitrary additionalProperties).
"""

from __future__ import annotations

_KV = {
    "type": "object",
    "properties": {"key": {"type": "string"}, "value": {"type": "integer"}},
    "required": ["key", "value"],
}

_RELATIONSHIP = {
    "type": "object",
    "properties": {
        "target_ref": {"type": "string", "description": "entity id (agent name / faction / location)"},
        "tie": {"type": "string", "description": "ally|rival|debt|grudge|kin|lover|patron|wary|…"},
        "weight": {"type": "integer", "description": "-5..5 (negative = antagonism)"},
        "note": {"type": "string"},
    },
    "required": ["target_ref", "tie", "weight"],
}

_FSM = {
    "type": "object",
    "properties": {
        "from_state": {"type": "string"},
        "to_state": {"type": "string"},
        "guard": {"type": "string", "description": "always | clock_full | clock>=N etc."},
    },
    "required": ["from_state", "to_state", "guard"],
}

# ── director result ──────────────────────────────────────────────────────────

DIRECTOR_RESULT = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "1-3 sentence GM-facing recap"},
        "developments": {
            "type": "array",
            "description": "player-facing world moves to stage in developments.md",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "headline": {"type": "string"},
                    "body": {"type": "string"},
                    "surface": {"type": "string", "enum": ["now", "soon", "hidden"]},
                    "escalate": {"type": "boolean"},
                    "arc": {"type": "string"},
                },
                "required": ["headline", "body", "surface"],
            },
        },
        "drive_edits": {
            "type": "array",
            "description": "re-plan: retarget goal, resize/reset clock, move state, flip relationships",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "goal_pursue": {"type": "string"},
                    "goal_target": {"type": "string"},
                    "goal_success": {"type": "string"},
                    "state": {"type": "string"},
                    "clock_filled": {"type": "integer"},
                    "clock_total": {"type": "integer"},
                    "salience": {"type": "integer"},
                    "relationship_changes": {"type": "array", "items": _RELATIONSHIP},
                },
                "required": ["agent"],
            },
        },
        "beliefs": {
            "type": "array",
            "description": "reflection: 1-2 synthesised beliefs appended to drives prose",
            "items": {
                "type": "object",
                "properties": {"agent": {"type": "string"}, "belief": {"type": "string"}},
                "required": ["agent", "belief"],
            },
        },
        "memory_entries": {
            "type": "array",
            "description": "actor-safe, day-stamped memory from the character's own POV",
            "items": {
                "type": "object",
                "properties": {"agent": {"type": "string"}, "text": {"type": "string"}},
                "required": ["agent", "text"],
            },
        },
        "plot_promotions": {
            "type": "array",
            "description": "collisions that hardened into standing conflicts",
            "items": {
                "type": "object",
                "properties": {
                    "plot_key": {"type": "string"},
                    "title": {"type": "string"},
                    "participants": {"type": "string"},
                    "stakes": {"type": "string"},
                    "state": {"type": "string", "enum": ["forming", "rising", "climax", "resolved"]},
                    "surface": {"type": "string", "enum": ["now", "soon", "hidden"]},
                    "arc": {"type": "string"},
                    "body_md": {"type": "string"},
                },
                "required": ["plot_key", "title", "state"],
            },
        },
        "escalate_to_opus": {
            "type": "array",
            "description": "beats the lite director deliberately left for the Opus pivot director",
            "items": {"type": "string"},
        },
    },
    "required": ["summary"],
}

# ── architect (new-world seed) ───────────────────────────────────────────────

_AGENT_SEED = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "stable lowercase id, e.g. 'mara-vex'"},
        "display_name": {"type": "string"},
        "kind": {"type": "string", "enum": ["npc", "faction"]},
        "state": {"type": "string"},
        "clock_filled": {"type": "integer"},
        "clock_total": {"type": "integer"},
        "advances_when": {"type": "string", "enum": ["always", "dawdle", "on_fail", "manual"]},
        "salience": {"type": "integer", "description": "1-5"},
        "group_id": {"type": "string"},
        "goal_pursue": {"type": "string", "description": "control|protect|destroy|seize|expose|court|undermine"},
        "goal_target": {"type": "string", "description": "another agent name, a faction, a location, never 'player'"},
        "goal_success": {"type": "string"},
        "location": {"type": "string", "description": "a location name from the locations list"},
        "profile_md": {"type": "string", "description": "ACTOR-SAFE: who they are, how they talk, what they openly know"},
        "secrets_md": {"type": "string", "description": "GM-ONLY hidden agenda/twist"},
        "sheet_md": {"type": "string", "description": "GM-ONLY mechanical stats (optional)"},
        "drives_prose_md": {"type": "string", "description": "GM-ONLY Agenda prose for the director"},
        "resources": {"type": "array", "items": _KV},
        "mood": {"type": "array", "items": _KV},
        "relationships": {"type": "array", "items": _RELATIONSHIP},
        "states": {"type": "array", "items": _FSM},
    },
    "required": ["name", "kind", "state", "salience", "profile_md"],
}

ARCHITECT_RESULT = {
    "type": "object",
    "properties": {
        "world": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "game": {"type": "string", "enum": ["m20", "v20", "w20"]},
                "edition": {"type": "string"},
                "play_mode": {"type": "string"},
                "tone": {"type": "string"},
                "premise": {"type": "string"},
                "lethality": {"type": "string"},
                "calendar": {"type": "string"},
                "gm_secrets_md": {"type": "string", "description": "GM-only master secrets"},
            },
            "required": ["name", "game"],
        },
        "locations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "x": {"type": "number", "description": "0..1 schematic map x"},
                    "y": {"type": "number", "description": "0..1 schematic map y"},
                },
                "required": ["name"],
            },
        },
        "agents": {"type": "array", "items": _AGENT_SEED},
        "plots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "plot_key": {"type": "string"},
                    "title": {"type": "string"},
                    "participants": {"type": "string"},
                    "stakes": {"type": "string"},
                    "state": {"type": "string"},
                    "surface": {"type": "string"},
                    "arc": {"type": "string"},
                    "body_md": {"type": "string"},
                },
                "required": ["plot_key", "title"],
            },
        },
        "spoiler_free_summary": {"type": "string"},
    },
    "required": ["world", "agents"],
}
