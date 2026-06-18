"""Fair dice + oracle for the directors — ported from Tools/dice.py.

Rolls come from `random.SystemRandom` (OS entropy), not a seedable PRNG. The
directors call these for *genuine* world-uncertainty (does the contact show? who
wins a knife-edge clash?) rather than picking the convenient answer — the same
"be seen to be fair" discipline the metronome and ledger enforce. The Storyteller
d10 pool resolver is verbatim; the d6 oracle (CLAUDE.md → "The oracle") is added
here for the directors' world-fact questions.
"""

from __future__ import annotations

from random import SystemRandom

_rng = SystemRandom()

_DEGREES = {1: "Marginal", 2: "Moderate", 3: "Complete", 4: "Exceptional"}
_PHENOMENAL = "Phenomenal"


def roll_dice(count, sides):
    if count < 1 or sides < 1:
        raise ValueError("count and sides must each be at least 1.")
    return [_rng.randint(1, sides) for _ in range(count)]


def resolve_storyteller_pool(rolls, difficulty, specialty=False, willpower=False):
    """Interpret a pool of d10s the World-of-Darkness way (M20 / V20 / W20)."""
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
        "rolls": rolls, "difficulty": difficulty, "specialty": specialty,
        "willpower": willpower, "successes": successes, "ones": ones,
        "net": net, "outcome": outcome,
        "degree": (_DEGREES.get(net, _PHENOMENAL) if outcome == "success" else None),
    }


def storyteller_pool(pool, difficulty=6, rage=0, specialty=False, willpower=False):
    """Roll and resolve a Storyteller pool in one call (for the directors)."""
    difficulty = max(2, min(10, difficulty))
    rolls = roll_dice(max(1, pool) + max(0, rage), 10)
    return resolve_storyteller_pool(rolls, difficulty, specialty, willpower)


# ── the oracle — ask the world a yes/no question (CLAUDE.md) ──────────────────

_ORACLE = {
    1: ("No, and", "No — and things lean worse."),
    2: ("No, and", "No — and things lean worse."),
    3: ("Yes, but", "Yes, but — with a catch, cost, or complication."),
    4: ("Yes, but", "Yes, but — with a catch, cost, or complication."),
    5: ("Yes", "Yes — clean."),
    6: ("Yes", "Yes — clean."),
}


def oracle(likelihood="even"):
    """Roll a d6 oracle for a world fact. `likelihood` ∈ likely|even|unlikely:
    likely rolls twice keeps the better, unlikely keeps the worse."""
    if likelihood == "likely":
        die = max(roll_dice(2, 6))
    elif likelihood == "unlikely":
        die = min(roll_dice(2, 6))
    else:
        die = roll_dice(1, 6)[0]
    verdict, gloss = _ORACLE[die]
    return {"die": die, "verdict": verdict, "gloss": gloss, "likelihood": likelihood}
