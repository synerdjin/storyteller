"""The Agent adapter — the shared shape every deterministic engine module reads.

The proven algorithms in `Tools/world_tick.py`, `ledger.py`, and `social.py`
operate on lightweight objects exposing `.name` and a `.fields` dict (the parsed
`drives.md` front-matter). The Ant Farm keeps state in SQLite instead of
markdown, so this module defines that same shape plus the small field-accessor
helpers the ported functions need. `db/loader.py` builds `Agent`s from DB rows;
the engine functions are then byte-for-byte equivalent to the originals.

Keeping `.fields` as the single source of truth (rather than typed columns the
functions would have to learn) is what lets the port stay faithful: the parity
test feeds identical `.fields` to both the legacy `Tools/` code and this engine
and asserts identical output.
"""

from __future__ import annotations

# Tie vocabularies — identical to Tools/world_tick.py.
ALLY_TIES = {"ally", "kin", "lover", "patron", "friend", "mentor"}
HOSTILE_TIES = {"rival", "grudge", "enemy", "nemesis"}


class Agent:
    """One living NPC or faction: its parsed fields, plus per-tick results.

    Mirrors `Tools/world_tick.Agent` but drops the file path/span (state lives in
    SQLite now). `id` is the DB primary key so the writer can persist changes.
    """

    def __init__(self, name, fields, agent_id=None):
        self.name = name
        self.fields = fields
        self.id = agent_id
        # tick results, filled in by tick():
        self.advanced = 0
        self.transitioned = False
        self.became_full = False
        self.old_state = fields.get("state")
        self.old_filled = clock_of(fields).get("filled", 0)


def clock_of(fields):
    c = fields.get("clock")
    return c if isinstance(c, dict) else {}


# ── field accessors (ported verbatim from world_tick.py) ─────────────────────

def goal_field(agent, key):
    g = agent.fields.get("goal")
    return g.get(key) if isinstance(g, dict) else None


def goal_target(agent):
    """The entity id this agent is reaching for, or None (legacy string goals)."""
    t = goal_field(agent, "target")
    return str(t).strip() if t not in (None, "") else None


def rels(agent):
    r = agent.fields.get("relationships")
    return r if isinstance(r, dict) else {}


def weight(edge):
    w = edge.get("weight") if isinstance(edge, dict) else None
    return w if isinstance(w, int) else 0


def group(agent):
    g = agent.fields.get("group")
    return str(g).strip() if g not in (None, "") else None


def salience(agent):
    s = agent.fields.get("salience")
    return s if isinstance(s, int) else 1


def resource_total(agent):
    r = agent.fields.get("resources")
    if not isinstance(r, dict):
        return 0, None
    nums = {k: v for k, v in r.items() if isinstance(v, int)}
    if not nums:
        return 0, None
    return sum(nums.values()), max(nums, key=nums.get)


def mood_total(agent):
    m = agent.fields.get("mood")
    return sum(v for v in m.values() if isinstance(v, int)) if isinstance(m, dict) else 0


def pressure(agent):
    """How hard an agent can press a contest: resources + mood + salience.

    Deterministic and auditable — the ledger uses this to decide who *gains*
    control, never a model.
    """
    res, _ = resource_total(agent)
    return float(res + mood_total(agent) + salience(agent))
