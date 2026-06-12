#!/usr/bin/env python3
"""Deterministic control ledgers for contested entities (the living world).

Ported in spirit from `the_city`'s `CommonsResource` game-master component:
a GM-owned piece of **numeric shared state** whose values are captured and
moved by *fixed rules*, never by an LLM. Where `CommonsResource` tracks a
renewable stock harvested each round, this tracks **who controls a contested
entity** (a council seat, a caern, a domain) as leverage points that shift
deterministically as the rivals press on it tick after tick.

Why it exists: collision *detection* already lives in `world_tick.py`, but the
*outcome* was decided fresh by the local model each time — so a recurring
contest had no memory, and a rival losing for five ticks looked identical to one
who just arrived. The ledger gives every contest a fair, auditable, persistent
number — `dice.py`'s "be seen to be fair" applied to politics. The model only
ever *narrates what the number means*; it never sets it.

The file `Game/ledgers.md` is **entirely tool-owned** (no human prose mixed in),
so this module parses and rewrites it wholesale. It is GM-only — never public,
never handed to an `npc-actor`.

Usage (normally called from world_tick.py, but runnable):
    python Tools/ledger.py --show         # print current ledgers
    python Tools/ledger.py --self-test
"""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_TOTAL = 10
_HISTORY_CAP = 12
_NEUTRAL = "_neutral"

_HEADER = (
    "# Control ledgers — who holds the contested things (GM ONLY)\n\n"
    "> GM-only, and **tool-owned**: `Tools/ledger.py` (via `world_tick.py`) writes\n"
    "> this file. Each contested entity is a pool of control points that shift by\n"
    "> fixed, deterministic rules as rivals press on it — never set by a model.\n"
    "> The number is the fairness; the prose only interprets it. Never quote to\n"
    "> the Player or hand to an `npc-actor`.\n"
)


class Ledger:
    """One contested entity's control standing."""

    def __init__(self, entity, total=DEFAULT_TOTAL, control=None, holder=None,
                 history=None):
        self.entity = entity
        self.total = int(total)
        self.control = dict(control or {})
        self.holder = holder
        self.history = list(history or [])

    # — derived views —
    def claimants(self):
        return {k: v for k, v in self.control.items() if k != _NEUTRAL}

    def standing(self):
        cl = sorted(self.claimants().items(), key=lambda kv: (-kv[1], kv[0]))
        bits = [f"{n} {v}" for n, v in cl]
        if self.control.get(_NEUTRAL):
            bits.append(f"{_NEUTRAL} {self.control[_NEUTRAL]}")
        return f"{', '.join(bits)} (holder: {self.holder or 'contested'})"

    def phase(self):
        """Map the standing onto a plot phase the tick/scribe can read."""
        cl = sorted(self.claimants().values(), reverse=True)
        top = cl[0] if cl else 0
        if top <= 0:
            return "forming"
        if top >= -(-self.total * 6 // 10):    # ceil(0.6 * total): near a win
            return "climax"
        return "rising"


def _ensure_keys(led, names):
    """Make sure every claimant exists, and _neutral starts at the remainder."""
    if _NEUTRAL not in led.control:
        led.control[_NEUTRAL] = max(0, led.total - sum(led.control.values()))
    for n in names:
        led.control.setdefault(n, 0)


def apply_pressure(led, pressures, day):
    """Shift control toward the highest-pressure claimant by a fixed rule.

    `pressures` maps claimant name -> a numeric pressure (the tick computes it
    from resources + mood + salience). Deterministic: the leader gains 1 point
    (2 if they dominate), drawn from the neutral pool first, then from the
    weakest opponent. Returns a small result dict for the queue.
    """
    _ensure_keys(led, pressures)
    ranked = sorted(pressures.items(), key=lambda kv: (-kv[1], kv[0]))
    leader, lp = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0.0
    gain = 2 if lp >= 1.5 * max(runner, 1.0) else 1

    moved = 0
    take = min(gain, led.control.get(_NEUTRAL, 0))
    led.control[_NEUTRAL] = led.control.get(_NEUTRAL, 0) - take
    moved += take
    rem = gain - take
    # remainder comes from the weakest opponent who still has points
    opps = sorted((n for n in led.control if n not in (_NEUTRAL, leader)),
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


# --------------------------------------------------------------------------- #
# File I/O — the whole file is tool-owned, parsed and rewritten wholesale.
# --------------------------------------------------------------------------- #

def _parse_control(s):
    out = {}
    for part in s.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, _, v = part.partition("=")
        try:
            out[k.strip()] = int(v.strip())
        except ValueError:
            pass
    return out


def parse_ledgers(text):
    ledgers = {}
    cur = None
    in_history = False
    for raw in text.splitlines():
        h = re.match(r"^##\s+(\S.*?)\s*$", raw)
        if h:
            cur = Ledger(h.group(1).strip())
            ledgers[cur.entity] = cur
            in_history = False
            continue
        if cur is None:
            continue
        line = raw.strip()
        if line.startswith("- Total:"):
            try:
                cur.total = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("- Holder:"):
            h = line.split(":", 1)[1].strip()
            cur.holder = None if h in ("", "contested") else h
        elif line.startswith("- Control:"):
            cur.control = _parse_control(line.split(":", 1)[1])
        elif line.startswith("- History:"):
            in_history = True
        elif in_history and line.startswith("-"):
            cur.history.append(line[1:].strip())
    return ledgers


def format_ledgers(ledgers):
    out = [_HEADER]
    if not ledgers:
        out.append("\n*(no contested ledgers yet — they open when a collision over "
                   "a shared target is first detected.)*\n")
        return "".join(out)
    for entity in sorted(ledgers):
        led = ledgers[entity]
        ctrl = ", ".join(
            f"{k}={led.control[k]}"
            for k in sorted(led.control, key=lambda k: (k == _NEUTRAL, k)))
        out.append(f"\n## {entity}\n")
        out.append(f"- Total: {led.total}\n")
        out.append(f"- Holder: {led.holder or 'contested'}\n")
        out.append(f"- Control: {ctrl}\n")
        out.append(f"- Phase: {led.phase()}\n")
        if led.history:
            out.append("- History:\n")
            for h in led.history:
                out.append(f"  - {h}\n")
    return "".join(out)


def load_ledgers(root):
    p = Path(root) / "Game" / "ledgers.md"
    if not p.exists():
        return {}
    return parse_ledgers(p.read_text(encoding="utf-8"))


def save_ledgers(root, ledgers):
    p = Path(root) / "Game" / "ledgers.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(format_ledgers(ledgers), encoding="utf-8")


def get_or_create(ledgers, entity, total=DEFAULT_TOTAL):
    if entity not in ledgers:
        ledgers[entity] = Ledger(entity, total=total)
    return ledgers[entity]


def _self_test():
    import tempfile

    # Fresh ledger: leader gains from the neutral pool, holder updates.
    led = Ledger("harbor-council", total=10)
    r = apply_pressure(led, {"mara": 5.0, "vance": 3.0}, day=3)
    assert r["winner"] == "mara" and r["delta"] >= 1
    assert led.control["mara"] >= 1 and led.control[_NEUTRAL] <= 10
    assert led.holder == "mara"

    # Dominant pressure (>=1.5x) gains 2.
    led2 = Ledger("caern", total=10)
    r2 = apply_pressure(led2, {"a": 9.0, "b": 1.0}, day=1)
    assert r2["delta"] == 2, r2

    # Once neutral is exhausted, points come off the weakest opponent (zero-sum).
    led3 = Ledger("seat", total=4, control={"a": 0, "b": 4, _NEUTRAL: 0})
    before = led3.control["b"]
    apply_pressure(led3, {"a": 10.0, "b": 1.0}, day=2)
    assert led3.control["a"] >= 1 and led3.control["b"] < before, led3.control

    # Phase thresholds.
    assert Ledger("x", total=10, control={"a": 0, _NEUTRAL: 10}).phase() == "forming"
    assert Ledger("x", total=10, control={"a": 6, "b": 2}).phase() == "climax"
    assert Ledger("x", total=10, control={"a": 3, "b": 2}).phase() == "rising"

    # Round-trip: format then parse must preserve the standing.
    text = format_ledgers({"harbor-council": led})
    back = parse_ledgers(text)["harbor-council"]
    assert back.control == led.control and back.holder == led.holder
    assert back.total == led.total and back.history == led.history

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        save_ledgers(root, {"harbor-council": led})
        again = load_ledgers(root)
        assert again["harbor-council"].control == led.control

    print("ledger self-test: OK")
    return 0


def main(argv):
    p = argparse.ArgumentParser(description="Deterministic control ledgers.")
    p.add_argument("--show", action="store_true", help="print current ledgers")
    p.add_argument("--self-test", action="store_true", help="run assertions and exit")
    args = p.parse_args(argv[1:])
    if args.self_test:
        return _self_test()
    root = Path.cwd()
    for cand in [root, *root.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            root = cand
            break
    led = load_ledgers(root)
    sys.stdout.write(format_ledgers(led))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
