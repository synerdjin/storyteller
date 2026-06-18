"""Deterministic world-scribe — ported from Tools/world_scribe.py.

Records ROUTINE off-screen movement as plain, true facts **with no model at
all** — the drift-proof tier. For each routine mover it emits one development
record straight from the metronome's structured facts (name, FSM state, clock,
goal, why-flagged); it never fabricates a concrete event or a power. Collisions,
reflection, and pivotal movers are *not* resolved here — they're returned as a
manifest for a Claude director.

Difference from the original: it operates on `Agent` objects and returns
structured records (dicts) for the DB layer, instead of parsing/writing markdown.
The thresholds, the firewall constant, and the surface/pivotal logic are verbatim.
"""

from __future__ import annotations

from . import agent as A
from .tick import changed

ESCALATE_SALIENCE = 5       # a mover this salient is pivotal → hand to a director
SURFACE_SOON_SALIENCE = 4   # this salient (or a filled clock) → surfaces "soon"
HEADLINE_MAX = 70

# FIREWALL: the headline propagated into actor-safe memory is a fixed, goal-free
# line — NEVER the agent's goal/success text (which carries the secrets). The
# development record below may name the goal because it is GM-only.
OBSERVABLE_HEADLINE = "has been quietly pursuing aims of their own lately"


def _short(s, n=HEADLINE_MAX):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n].rstrip() + "…"


def fmt_goal(agent):
    """Render a goal: targeted map → 'pursue target (success)'; legacy string."""
    g = agent.fields.get("goal")
    if isinstance(g, dict):
        bits = " ".join(str(g[k]) for k in ("pursue", "target") if g.get(k))
        succ = g.get("success")
        return f"{bits}" + (f" ({succ})" if succ else "")
    return str(g) if g is not None else "(unstated aim)"


def fmt_goal_public(agent):
    """Goal label WITHOUT the secret `success` line — safe to surface at any tier.

    `pursue` (a generic verb) and `target` (a public entity id) are observable;
    the `success` clause is the flavorful secret and stays behind the curtain.
    A legacy free-string goal is treated as opaque (the whole thing could be a
    spoiler), so it's reduced to a neutral phrase.
    """
    g = agent.fields.get("goal")
    if isinstance(g, dict):
        bits = " ".join(str(g[k]) for k in ("pursue", "target") if g.get(k))
        return bits or "an aim of their own"
    return "an aim of their own"


def why_flagged(agent):
    """Reconstruct the queue's 'why' line from the agent's tick results."""
    bits = []
    if agent.transitioned:
        bits.append(f"entered {agent.fields.get('state')} (was {agent.old_state})")
    if agent.became_full:
        bits.append("clock filled")
    elif agent.advanced:
        c = A.clock_of(agent.fields)
        bits.append(f"clock advanced to {c.get('filled')}/{c.get('total')}")
    return ", ".join(bits) or "advanced this tick"


def is_pivotal(agent):
    """A routine mover a director should own: highly salient, or clock just filled."""
    return A.salience(agent) >= ESCALATE_SALIENCE or agent.became_full


def surface_for(agent, pivotal):
    """Deterministic Surface timing for a routine mover (never 'now')."""
    if pivotal or agent.became_full or A.salience(agent) >= SURFACE_SOON_SALIENCE:
        return "soon"
    return "hidden"


def format_development(day, agent):
    """Render one routine mover as a development record (dict) — purely facts.

    The headline/body are goal-PUBLIC (no secret `success` line), because a
    templated development can surface to a non-curtain observer. The full goal,
    including `success`, stays behind the curtain on the agent itself.
    """
    name = agent.name
    goal = fmt_goal_public(agent)
    why = why_flagged(agent)
    c = A.clock_of(agent.fields)
    clock = f"{c.get('filled')}/{c.get('total')}" if c else "?"
    pivotal = is_pivotal(agent)
    surface = surface_for(agent, pivotal)

    headline = _short(f"{name} advances — {goal}")
    clock_tail = "" if "clock" in why.lower() else f"; clock now {clock}"
    body = (f"{name[:1].upper() + name[1:]} pressed on toward their aim "
            f"({goal}) this tick — {why}{clock_tail}.")
    return {
        "day": day, "agent": name, "headline": headline, "body": body,
        "surface": surface, "escalate": pivotal, "arc": name,
        "source": "templated (world_scribe — deterministic, no model)",
        "drained": False,
    }


def scribe_movers(day, movers):
    """Template routine movers into development records + observation events.

    Returns (developments, observation_events, escalated_names). Each observation
    event carries the fixed goal-free `OBSERVABLE_HEADLINE` — the firewall begins
    here, at the source; `social.propagate` re-checks it.
    """
    developments, observations, escalated = [], [], []
    for a in movers:
        developments.append(format_development(day, a))
        pivotal = is_pivotal(a)
        if pivotal:
            escalated.append(a.name)
        if surface_for(a, pivotal) != "hidden":   # observable → propagates
            observations.append({"participants": [a.name],
                                 "headline": OBSERVABLE_HEADLINE, "day": day})
    return developments, observations, escalated


def manifest(interactions, reflectors, escalated_movers):
    """The hand-off describing what a Claude director must do this tick."""
    return {
        "collisions": [
            {"kind": it.kind,
             "a": it.a.name, "b": it.b.name if it.b else None,
             "over": it.over, "why": it.why, "hint": it.hint,
             "standing": it.standing, "phase": it.phase}
            for it in interactions
        ],
        "reflection": [r.name for r in reflectors],
        "pivotal_movers": list(escalated_movers),
    }
