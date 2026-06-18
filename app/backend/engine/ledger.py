"""Deterministic control ledgers — ported from Tools/ledger.py.

Tracks **who controls a contested entity** as leverage points that shift by a
fixed rule as rivals press on it tick after tick. `dice.py`'s "be seen to be
fair" applied to politics: a model never sets the number, only narrates what it
means. The markdown file I/O of the original is dropped (SQLite persists the
`Ledger` objects now); the `Ledger` class and `apply_pressure` math are verbatim.
"""

from __future__ import annotations

DEFAULT_TOTAL = 10
_HISTORY_CAP = 12
NEUTRAL = "_neutral"


class Ledger:
    """One contested entity's control standing."""

    def __init__(self, entity, total=DEFAULT_TOTAL, control=None, holder=None,
                 history=None):
        self.entity = entity
        self.total = int(total)
        self.control = dict(control or {})
        self.holder = holder
        self.history = list(history or [])

    def claimants(self):
        return {k: v for k, v in self.control.items() if k != NEUTRAL}

    def standing(self):
        cl = sorted(self.claimants().items(), key=lambda kv: (-kv[1], kv[0]))
        bits = [f"{n} {v}" for n, v in cl]
        if self.control.get(NEUTRAL):
            bits.append(f"{NEUTRAL} {self.control[NEUTRAL]}")
        return f"{', '.join(bits)} (holder: {self.holder or 'contested'})"

    def phase(self):
        cl = sorted(self.claimants().values(), reverse=True)
        top = cl[0] if cl else 0
        if top <= 0:
            return "forming"
        if top >= -(-self.total * 6 // 10):    # ceil(0.6 * total): near a win
            return "climax"
        return "rising"


def _ensure_keys(led, names):
    if NEUTRAL not in led.control:
        led.control[NEUTRAL] = max(0, led.total - sum(led.control.values()))
    for n in names:
        led.control.setdefault(n, 0)


def apply_pressure(led, pressures, day):
    """Shift control toward the highest-pressure claimant by a fixed rule.

    The leader gains 1 point (2 if they dominate, pressure ≥ 1.5× the runner-up),
    drawn from the neutral pool first, then from the weakest opponent. Returns a
    small result dict for the queue/director.
    """
    _ensure_keys(led, pressures)
    ranked = sorted(pressures.items(), key=lambda kv: (-kv[1], kv[0]))
    leader, lp = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0.0
    gain = 2 if lp >= 1.5 * max(runner, 1.0) else 1

    moved = 0
    take = min(gain, led.control.get(NEUTRAL, 0))
    led.control[NEUTRAL] = led.control.get(NEUTRAL, 0) - take
    moved += take
    rem = gain - take
    opps = sorted((n for n in led.control if n not in (NEUTRAL, leader)),
                  key=lambda n: led.control[n], reverse=True)
    while rem > 0 and opps:
        n = opps[-1]
        if led.control[n] > 0:
            led.control[n] -= 1
            rem -= 1
            moved += 1
        else:
            opps.pop()
    led.control[leader] = led.control.get(leader, 0) + moved

    claim = led.claimants()
    top = max(claim.values()) if claim else 0
    leaders = [n for n, v in claim.items() if v == top and v > 0]
    led.holder = leaders[0] if len(leaders) == 1 else "contested"

    dl = f"Day {day}" if day is not None else "Day ?"
    led.history.append(
        f"[{dl}] {leader} +{moved} -> {led.control[leader]}/{led.total} "
        f"(holder: {led.holder})")
    led.history = led.history[-_HISTORY_CAP:]
    return {"winner": leader, "delta": moved, "holder": led.holder,
            "standing": led.standing(), "phase": led.phase()}


def get_or_create(ledgers, entity, total=DEFAULT_TOTAL):
    if entity not in ledgers:
        ledgers[entity] = Ledger(entity, total=total)
    return ledgers[entity]
