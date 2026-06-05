#!/usr/bin/env python3
"""Fair, auditable dice roller for the Storyteller Game Master.

Rolls come from random.SystemRandom (OS entropy), not a seedable PRNG, so the
GM cannot bias them and every roll is shown in full.

The roller has two layers:

  * GENERIC — roll any pool of dice (`NdS`, optional +/- modifier, adv/dis).
    This is the whole "generic system": a type and a number of dice, nothing
    else. It backs the engine's default d20-vs-target resolution.

  * SYSTEMS — interpret raw dice the way a specific game does. Pick one by
    naming it as the first argument. Currently:
        m20 / mage  — Mage: The Ascension 20th Anniversary (Storyteller d10 pool)
    Each system is a thin layer over the generic roll, so adding more later
    (dnd, v20, …) is just another entry in SYSTEMS at the bottom of this file.

Generic usage:
    python dice.py 3d6+2
    python dice.py d20 adv           # roll 2d20, keep highest (advantage)
    python dice.py d20 dis           # roll 2d20, keep lowest  (disadvantage)
    python dice.py 1d8 1d6+1         # multiple expressions, shows a combined total

Notation:  [count]d<sides>[+/-modifier]   e.g. d20, 2d6, 3d8+2, 1d4-1
Flags:     adv | advantage | dis | disadvantage   (apply to a single-die roll)

Mage 20e usage:
    python dice.py m20 7             # 7-die pool vs difficulty 6
    python dice.py m20 7 -d 8        # difficulty 8 (standard range 3-9)
    python dice.py m20 7 -s          # specialty: a 10 counts as two successes
    python dice.py m20 7 -w          # spend Willpower: +1 automatic success, no botch
"""

import argparse
import re
import sys
from random import SystemRandom

_rng = SystemRandom()


# ── Generic layer: roll dice, nothing else ───────────────────────────────────

def roll_dice(count, sides):
    """Roll `count` dice with `sides` faces; return the list of results.

    This is the entire generic system — a type and a number of dice. Every
    game-specific system below is built on top of this single primitive.
    """
    if count < 1 or sides < 1:
        raise ValueError("count and sides must each be at least 1.")
    return [_rng.randint(1, sides) for _ in range(count)]


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
        a, b = roll_dice(2, sides)
        kept = max(a, b) if mode == "adv" else min(a, b)
        total = kept + modifier
        label = "advantage" if mode == "adv" else "disadvantage"
        return f"{expr} ({label}): [{a}, {b}] keep {kept}{mod_str} = {total}", total

    rolls = roll_dice(count, sides)
    total = sum(rolls) + modifier
    return f"{expr}: {rolls}{mod_str} = {total}", total


def run_generic(argv):
    """The default (system-less) roller: bare NdS expressions, adv/dis."""
    mode = None
    exprs = []
    for a in argv:
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


# ── Storyteller d10-pool layer (Mage 20e; reusable for V20) ──────────────────
#
# The classic World-of-Darkness "Storyteller System" is shared by Mage 20e and
# Vampire V20, so the resolver below is written for the engine, not the game.
# A future `v20` system can call resolve_storyteller_pool() unchanged.

_DEGREES = {1: "Marginal", 2: "Moderate", 3: "Complete", 4: "Exceptional"}
_PHENOMENAL = "Phenomenal"  # 5+ successes


def resolve_storyteller_pool(rolls, difficulty, specialty=False, willpower=False):
    """Interpret a pool of d10s the World-of-Darkness way.

    Rules (M20 / V20):
      * Each die >= difficulty is one success; a 10 is two successes when the
        character has a relevant Specialty.
      * Each 1 cancels a success.
      * A botch is a roll with at least one 1 and zero successes (before any 1s
        cancel). If you had even one success, canceling down to zero is a plain
        failure, not a botch.
      * Spending a point of Willpower adds one automatic success and rules out a
        botch.

    `rolls` are already-rolled dice, so this is pure and testable. Returns a
    dict describing the outcome.
    """
    successes = 0
    for d in rolls:
        if d >= difficulty:
            successes += 2 if (d == 10 and specialty) else 1
    ones = sum(1 for d in rolls if d == 1)

    auto = 1 if willpower else 0
    botch = (not willpower) and successes == 0 and ones > 0
    net = successes + auto - ones

    if botch:
        outcome, net = "botch", 0
    elif net <= 0:
        outcome, net = "failure", 0
    else:
        outcome = "success"

    return {
        "rolls": rolls,
        "difficulty": difficulty,
        "specialty": specialty,
        "willpower": willpower,
        "successes": successes,
        "ones": ones,
        "net": net,
        "outcome": outcome,
    }


def format_storyteller(r):
    """Render a resolve_storyteller_pool() result as auditable text (ASCII)."""
    diff = r["difficulty"]
    faces = []
    for d in r["rolls"]:
        if d == 1:
            faces.append("1[-]")
        elif d >= diff:
            if d == 10 and r["specialty"]:
                faces.append("10[++]")
            else:
                faces.append(f"{d}[+]")
        else:
            faces.append(str(d))

    flags = []
    if r["specialty"]:
        flags.append("specialty")
    if r["willpower"]:
        flags.append("+1 Willpower")
    flag_str = f"  ({', '.join(flags)})" if flags else ""

    header = (
        f"M20 pool: {len(r['rolls'])}d10 vs difficulty {diff}{flag_str}\n"
        f"  dice: {'  '.join(faces)}\n"
        f"  successes rolled: {r['successes']}   ones: {r['ones']}"
    )

    outcome = r["outcome"]
    if outcome == "botch":
        verdict = "  => BOTCH - dramatic failure"
    elif outcome == "failure":
        why = "the 1s cancelled every success" if r["successes"] else "nothing met the difficulty"
        verdict = f"  => FAILURE - {why}"
    else:
        net = r["net"]
        degree = _DEGREES.get(net, _PHENOMENAL)
        plural = "success" if net == 1 else "successes"
        verdict = f"  => SUCCESS - {net} net {plural} ({degree})"

    return f"{header}\n{verdict}"


def run_m20(argv):
    """Mage: The Ascension 20e — roll and interpret a d10 dice pool."""
    parser = argparse.ArgumentParser(
        prog="dice.py m20",
        description="Mage: The Ascension 20e (Storyteller d10 pool).",
    )
    parser.add_argument(
        "pool", type=int,
        help="number of d10s (Attribute + Ability, Arete, etc.)",
    )
    parser.add_argument(
        "-d", "--difficulty", type=int, default=6,
        help="target number, clamped to 2-10 (default 6; standard range 3-9)",
    )
    parser.add_argument(
        "-s", "--specialty", action="store_true",
        help="a rolled 10 counts as two successes",
    )
    parser.add_argument(
        "-w", "--willpower", action="store_true",
        help="spend Willpower: one automatic success, cannot botch",
    )
    ns = parser.parse_args(argv)

    if ns.pool < 1:
        parser.error("pool must be at least 1 die.")
    difficulty = max(2, min(10, ns.difficulty))

    rolls = roll_dice(ns.pool, 10)
    result = resolve_storyteller_pool(rolls, difficulty, ns.specialty, ns.willpower)
    print(format_storyteller(result))
    return 0


# ── Dispatch ─────────────────────────────────────────────────────────────────
#
# Register a game system here to give it its own subcommand. New systems
# (dnd, v20, …) plug in as one more entry — the generic roller stays the default.

SYSTEMS = {
    "m20": run_m20,
    "mage": run_m20,
}


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 1

    system = SYSTEMS.get(args[0].lower())
    if system:
        return system(args[1:])
    return run_generic(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
