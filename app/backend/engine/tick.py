"""The living-world metronome — ported from Tools/world_tick.py.

Deterministic, auditable, invents nothing. It advances each living agent's clock
by fixed rules, fires at most one FSM transition whose guard is met, and detects
structural *collisions* (two agents reaching for the same target; a rivalry
boiling over). It finds the contention; it never decides who wins — that stays
in the director tier.

Faithful to the original with one ant-farm change: **collision rule (c),
"player-pressure", is removed** — an ant farm has no player protagonist whose
threads the metronome biases toward. Rules (a) contested-goal and (b) rivalry
are kept verbatim, including all their guards and tie-break ordering.
"""

from __future__ import annotations

import re

from . import agent as A
from .agent import Agent

_GUARD_RE = re.compile(r"^clock\s*(>=|<=|==|!=|>|<)\s*(\d+)$")


# ── the tick rules (verbatim from world_tick.py) ─────────────────────────────

def eval_guard(guard, filled, total):
    """Evaluate an FSM transition guard against the current clock."""
    if guard is None:
        return False
    g = str(guard).strip()
    if g == "always":
        return True
    if g == "clock_full":
        return filled >= total
    m = _GUARD_RE.match(g)
    if not m:
        return False  # unknown guard never fires — fail safe
    op, num = m.group(1), int(m.group(2))
    return {
        ">=": filled >= num, "<=": filled <= num, "==": filled == num,
        "!=": filled != num, ">": filled > num, "<": filled < num,
    }[op]


def advance_amount(advances_when, elapsed, dawdle, fail):
    aw = (advances_when or "manual")
    if aw == "always":
        return elapsed
    if aw == "dawdle":
        return 1 if dawdle else 0
    if aw in ("on_fail", "fail"):
        return 1 if fail else 0
    return 0  # manual: only the director moves it


def tick(agent, elapsed, dawdle, fail):
    """Advance one agent's clock and fire at most one FSM transition."""
    clock = A.clock_of(agent.fields)
    filled = int(clock.get("filled", 0))
    total = int(clock.get("total", 0))
    state = agent.fields.get("state")
    states = agent.fields.get("states") or {}

    adv = advance_amount(agent.fields.get("advances_when"), elapsed, dawdle, fail)
    new_filled = min(total, filled + adv) if total else filled + adv
    agent.advanced = new_filled - filled
    agent.became_full = total > 0 and new_filled >= total and filled < total

    transition = states.get(state) if isinstance(states, dict) else None
    if isinstance(transition, dict):
        guard, target = transition.get("when"), transition.get("to")
        if target and eval_guard(guard, new_filled, total):
            state = target
            agent.transitioned = True

    clock["filled"] = new_filled
    agent.fields["clock"] = clock
    agent.fields["state"] = state


def priority(agent):
    """Deterministic selection score: who most deserves a director's attention."""
    sal = agent.fields.get("salience")
    sal = sal if isinstance(sal, int) else 1
    return (
        sal
        + (3 if agent.transitioned else 0)
        + (2 if agent.became_full else 0)
        + (1 if agent.advanced else 0)
    )


def changed(agent):
    return bool(agent.advanced) or agent.transitioned


# ── interaction detection — the emergence layer ──────────────────────────────

def _allied(a, b):
    ga, gb = A.group(a), A.group(b)
    if ga is not None and ga == gb:
        return True
    for x, y in ((a, b), (b, a)):
        e = A.rels(x).get(y.name)
        if isinstance(e, dict) and e.get("tie") in A.ALLY_TIES and A.weight(e) > 0:
            return True
    return False


def _hostile_edge(a, b):
    for x, y in ((a, b), (b, a)):
        e = A.rels(x).get(y.name)
        if isinstance(e, dict):
            tie, w = e.get("tie"), A.weight(e)
            if tie in A.HOSTILE_TIES or w <= -3:
                return (tie or "hostile", w)
    return None


def _advantage_hint(a, b):
    ta, topa = A.resource_total(a)
    tb, topb = A.resource_total(b)
    if ta == tb:
        return f"even on resources ({a.name} {ta} vs {b.name} {tb}) — resolve honestly"
    lead, lt, lp = (a, ta, topa) if ta > tb else (b, tb, topb)
    edge = f" ({lp})" if lp else ""
    return (f"{lead.name} better-resourced{edge}: {a.name} {ta} vs {b.name} {tb}"
            f" — a hint, not a verdict")


class Interaction:
    """A detected, unresolved point of contention between two agents."""

    def __init__(self, kind, a, b, over, why, hint):
        self.kind = kind      # contested-goal | rivalry
        self.a = a
        self.b = b
        self.over = over      # the contested entity id, or None
        self.why = why
        self.hint = hint
        self.standing = None  # filled by the ledger pass (contested-goal only)
        self.phase = None

    def key(self):
        names = tuple(sorted([self.a.name, self.b.name if self.b else "?"]))
        return (self.kind, names, self.over)

    def heat(self):
        moved = changed(self.a) + (changed(self.b) if self.b else 0)
        sal = A.salience(self.a) + (A.salience(self.b) if self.b else 0)
        return (moved, sal)


def detect_interactions(agents, max_n=0):
    """Find structural collisions among the living agents this tick.

    Ant-farm variant: rules (a) contested-goal and (b) rivalry only — the
    original rule (c) player-pressure is intentionally dropped (no player).
    """
    living = list(agents)
    found = {}

    # Rule (a): two non-allied agents reaching for the SAME target, ≥1 moved.
    by_target = {}
    for a in living:
        t = A.goal_target(a)
        if t and t != "player":
            by_target.setdefault(t, []).append(a)
    for t, grp in by_target.items():
        for i in range(len(grp)):
            for j in range(i + 1, len(grp)):
                a, b = grp[i], grp[j]
                if _allied(a, b) or not (changed(a) or changed(b)):
                    continue
                why = f"both reach for `{t}`"
                he = _hostile_edge(a, b)
                if he:
                    why += f"; they are {he[0]} ({he[1]})"
                it = Interaction("contested-goal", a, b, t, why, _advantage_hint(a, b))
                found[it.key()] = it

    # Rule (b): a hostile edge, BOTH advancing this tick (skip contested pairs).
    contesting_pairs = {tuple(sorted((it.a.name, it.b.name)))
                        for it in found.values() if it.b}
    for i in range(len(living)):
        for j in range(i + 1, len(living)):
            a, b = living[i], living[j]
            if not (changed(a) and changed(b)):
                continue
            if tuple(sorted((a.name, b.name))) in contesting_pairs:
                continue
            he = _hostile_edge(a, b)
            if not he:
                continue
            it = Interaction(
                "rivalry", a, b, None,
                f"{a.name} and {b.name} are {he[0]} ({he[1]}) and both moved this tick",
                _advantage_hint(a, b))
            found.setdefault(it.key(), it)

    out = sorted(found.values(),
                 key=lambda it: (-it.heat()[0], -it.heat()[1], it.a.name,
                                 it.b.name if it.b else ""))
    return out[:max_n] if max_n else out
