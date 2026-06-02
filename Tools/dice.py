#!/usr/bin/env python3
"""Fair, auditable dice roller for the Storyteller Game Master.

Rolls come from random.SystemRandom (OS entropy), not a seedable PRNG, so the
GM cannot bias them and every roll is shown in full.

Usage:
    python dice.py 3d6+2
    python dice.py d20 adv          # roll 2d20, keep highest (advantage)
    python dice.py d20 dis          # roll 2d20, keep lowest  (disadvantage)
    python dice.py 1d8 1d6+1        # multiple expressions, shows a combined total

Notation:  [count]d<sides>[+/-modifier]   e.g. d20, 2d6, 3d8+2, 1d4-1
Flags:     adv | advantage | dis | disadvantage   (apply to a single-die roll)
"""

import re
import sys
from random import SystemRandom

_rng = SystemRandom()
_DIE = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$", re.IGNORECASE)


def _fmt_mod(modifier):
    if modifier > 0:
        return f" +{modifier}"
    if modifier < 0:
        return f" {modifier}"
    return ""


def roll_expression(expr, mode=None):
    """Roll one dice expression. mode is None, 'adv', or 'dis'.

    Returns (human-readable line, numeric total).
    """
    m = _DIE.match(expr)
    if not m:
        raise ValueError(f"Don't understand '{expr}'. Use forms like d20, 2d6, 3d8+2.")
    count = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    modifier = int(m.group(3)) if m.group(3) else 0
    if count < 1 or sides < 1:
        raise ValueError(f"'{expr}': count and sides must each be at least 1.")

    mod_str = _fmt_mod(modifier)

    if mode and count == 1:
        # Advantage/disadvantage: roll the single die twice, keep highest/lowest.
        a, b = _rng.randint(1, sides), _rng.randint(1, sides)
        kept = max(a, b) if mode == "adv" else min(a, b)
        total = kept + modifier
        label = "advantage" if mode == "adv" else "disadvantage"
        return f"{expr} ({label}): [{a}, {b}] keep {kept}{mod_str} = {total}", total

    rolls = [_rng.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier
    return f"{expr}: {rolls}{mod_str} = {total}", total


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 1

    mode = None
    exprs = []
    for a in args:
        low = a.lower()
        if low in ("adv", "advantage"):
            mode = "adv"
        elif low in ("dis", "disadvantage"):
            mode = "dis"
        else:
            exprs.append(a)

    if not exprs:
        print("No dice to roll. Example: python dice.py 3d6+2")
        return 1

    grand_total = 0
    try:
        for expr in exprs:
            line, total = roll_expression(expr, mode)
            print(line)
            grand_total += total
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    if len(exprs) > 1:
        print(f"Total (sum): {grand_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
