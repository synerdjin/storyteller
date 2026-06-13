#!/usr/bin/env python3
"""Fair, auditable dice roller for the Storyteller Game Master.

Rolls come from random.SystemRandom (OS entropy), not a seedable PRNG, so the
GM cannot bias them and every roll is shown in full.

The roller has two layers:

  * GENERIC — roll any pool of dice (`NdS`, optional +/- modifier, adv/dis).
    This is the whole "generic system": a type and a number of dice, nothing
    else. It backs the engine's default d20-vs-target resolution.

  * SYSTEMS — interpret raw dice the way a specific game does. Pick one by
    naming it as the first argument. This engine runs the World of Darkness on
    the Storyteller System (d10 success pools); all three supported games share
    one resolver and differ only in their splat trappings:
        m20 / mage     — Mage: The Ascension 20th Anniversary
        v20 / vampire  — Vampire: The Masquerade 20th Anniversary
        w20 / werewolf — Werewolf: The Apocalypse 20th Anniversary
    Each system is a thin layer over the generic roll. The generic roller below
    stays available as a low-level utility (for any odd die a scene needs).

Generic usage (utility rolls):
    python dice.py 3d6+2
    python dice.py d10 adv           # roll 2d10, keep highest (advantage)
    python dice.py d10 dis           # roll 2d10, keep lowest  (disadvantage)
    python dice.py 1d8 1d6+1         # multiple expressions, shows a combined total

Notation:  [count]d<sides>[+/-modifier]   e.g. d10, 2d6, 3d8+2, 1d4-1
Flags:     adv | advantage | dis | disadvantage   (apply to a single-die roll)

Storyteller pool usage (the default game resolution):
    python dice.py m20 7             # 7-die pool vs difficulty 6
    python dice.py v20 5 -d 7        # Vampire pool, difficulty 7
    python dice.py w20 6 -r 2        # Werewolf pool + 2 Rage dice
    python dice.py m20 7 -s          # specialty: a 10 counts as two successes
    python dice.py v20 5 -w          # spend Willpower: +1 automatic success, no botch
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


# ── Storyteller d10-pool layer (M20 / V20 / W20) ─────────────────────────────
#
# The classic World-of-Darkness "Storyteller System" is shared by all three
# supported games, so the resolver below is written for the system, not any one
# game: Mage, Vampire, and Werewolf all call resolve_storyteller_pool() through
# the shared _run_storyteller() driver, differing only in their splat trappings.

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


def format_storyteller(r, label="Storyteller"):
    """Render a resolve_storyteller_pool() result as auditable text (ASCII).

    `label` names the game in the header (M20 / V20 / W20) so the output is
    unambiguous about which system's pool was rolled.
    """
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
        f"{label} pool: {len(r['rolls'])}d10 vs difficulty {diff}{flag_str}\n"
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


def format_storyteller_quiet(r, label="Storyteller"):
    """One terse GM-only line for the roll log (resolve-then-narrate mode).

    The full `format_storyteller` block is the auditable form shown when the
    Player asks "what did I roll?"; this compact line is what the GM keeps in a
    GM-only log while the *prose* carries only the result. Mechanics off the
    page, fairness on the record.
    """
    o = r["outcome"]
    if o == "botch":
        verdict = "BOTCH"
    elif o == "failure":
        verdict = "fail"
    else:
        verdict = f"{r['net']} net ({_DEGREES.get(r['net'], _PHENOMENAL)})"
    flags = ""
    if r["specialty"]:
        flags += " spec"
    if r["willpower"]:
        flags += " +WP"
    dice = " ".join(str(d) for d in r["rolls"])
    return (f"{label} {len(r['rolls'])}d10 vs {r['difficulty']}{flags} -> "
            f"{verdict} [{dice} | 1s:{r['ones']}]")


def _run_storyteller(argv, prog, label, pool_help, with_rage=False):
    """Shared driver for every Storyteller-System game (M20 / V20 / W20).

    The three games roll an identical d10 success pool, so they all funnel
    through resolve_storyteller_pool(). `with_rage` adds Werewolf's option to
    fold extra Rage dice into the pool. Garou nuances beyond that (extra
    actions, frenzy) live in the player's sourcebook digest, not here.
    """
    parser = argparse.ArgumentParser(
        prog=f"dice.py {prog}",
        description=f"{label} (Storyteller d10 pool).",
    )
    parser.add_argument("pool", type=int, help=pool_help)
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
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="terse one-line GM-only result (resolve-then-narrate: mechanics stay "
             "off the prose page; show the full block only if the Player asks)",
    )
    if with_rage:
        parser.add_argument(
            "-r", "--rage", type=int, default=0,
            help="Rage dice added to the pool (Garou spend; default 0)",
        )
    ns = parser.parse_args(argv)

    if ns.pool < 1:
        parser.error("pool must be at least 1 die.")
    rage = getattr(ns, "rage", 0)
    if rage < 0:
        parser.error("rage dice cannot be negative.")
    difficulty = max(2, min(10, ns.difficulty))

    rolls = roll_dice(ns.pool + rage, 10)
    result = resolve_storyteller_pool(rolls, difficulty, ns.specialty, ns.willpower)
    if ns.quiet:
        print(format_storyteller_quiet(result, label))
    else:
        print(format_storyteller(result, label))
    return 0


def run_m20(argv):
    """Mage: The Ascension 20e — roll and interpret a d10 dice pool."""
    return _run_storyteller(
        argv, "m20", "M20",
        "number of d10s (Attribute + Ability, Arete, etc.)",
    )


def run_v20(argv):
    """Vampire: The Masquerade 20e — roll and interpret a d10 dice pool."""
    return _run_storyteller(
        argv, "v20", "V20",
        "number of d10s (Attribute + Ability, Discipline, etc.)",
    )


def run_w20(argv):
    """Werewolf: The Apocalypse 20e — roll and interpret a d10 dice pool."""
    return _run_storyteller(
        argv, "w20", "W20",
        "number of d10s (Attribute + Ability, Gift, etc.)",
        with_rage=True,
    )


# ── Dispatch ─────────────────────────────────────────────────────────────────
#
# Register a game system here to give it its own subcommand. The three World of
# Darkness games share the Storyteller resolver; the generic NdS roller below
# stays available as a low-level utility when no system name is given.

SYSTEMS = {
    "m20": run_m20,
    "mage": run_m20,
    "v20": run_v20,
    "vampire": run_v20,
    "w20": run_w20,
    "werewolf": run_w20,
}


def _self_test():
    """Pin the rules-load-bearing logic: the Storyteller resolver and parsing.

    Uses fixed dice (resolve_storyteller_pool is pure) so the rules — successes
    vs. difficulty, 1s cancelling, botch detection, the willpower and specialty
    exceptions — are asserted deterministically, not left to a live roll.
    """
    R = resolve_storyteller_pool

    # Successes vs difficulty; no 1s.
    r = R([8, 5, 9, 2], 6)
    assert r["successes"] == 2 and r["ones"] == 0 and r["net"] == 2
    assert r["outcome"] == "success"

    # A 1 cancels a success.
    r = R([8, 1, 7], 6)
    assert r["successes"] == 2 and r["ones"] == 1 and r["net"] == 1
    assert r["outcome"] == "success"

    # Botch: at least one 1 and zero successes.
    r = R([1, 3, 4], 6)
    assert r["outcome"] == "botch" and r["net"] == 0

    # NOT a botch if a success existed, even when 1s cancel it to zero.
    r = R([7, 1], 6)
    assert r["successes"] == 1 and r["ones"] == 1
    assert r["outcome"] == "failure" and r["net"] == 0

    # Plain failure: nothing meets difficulty, no 1s.
    r = R([2, 3, 4], 6)
    assert r["outcome"] == "failure" and r["net"] == 0

    # Specialty: a rolled 10 counts as two successes (only with the flag).
    assert R([10, 5], 6, specialty=True)["successes"] == 2
    assert R([10, 5], 6, specialty=False)["successes"] == 1

    # Willpower: +1 automatic success and can never botch.
    r = R([1, 2, 3], 6, willpower=True)        # would botch without WP
    assert r["outcome"] == "failure" and r["net"] == 0
    r = R([1, 1, 2], 6, willpower=True)         # +1 auto - 2 ones → still no botch
    assert r["outcome"] == "failure"
    r = R([7, 8], 6, willpower=True)            # 2 successes + 1 auto = 3 net
    assert r["net"] == 3 and r["outcome"] == "success"

    # Quiet (resolve-then-narrate) formatter: terse, but carries the verdict + dice.
    q = format_storyteller_quiet(R([8, 5, 9, 2], 6), "M20")
    assert "M20 4d10 vs 6" in q and "2 net (Moderate)" in q and "1s:0" in q
    assert "BOTCH" in format_storyteller_quiet(R([1, 3, 4], 6), "V20")

    # Generic expression: parsing + modifier within bounds.
    line, total = roll_expression("3d6+2")
    assert 5 <= total <= 20 and "+2" in line
    try:
        roll_expression("banana")
        assert False, "expected a ValueError on a bad expression"
    except ValueError:
        pass

    print("dice self-test: OK")
    return 0


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--self-test":
        return _self_test()

    system = SYSTEMS.get(args[0].lower())
    if system:
        return system(args[1:])
    return run_generic(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
