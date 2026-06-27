#!/usr/bin/env python3
"""Turn a numeric value profile into the worldview text an NPC reasons from.

Ported and adapted from the sibling project `the_city`
(github.com/synerdjin/the_city), which grounds agent culture in two widely used
cross-cultural frameworks so a worldview is *calibratable*, not invented:

  * Hofstede dimensions (0..100 each)
  * World Values Survey primary axes (-1..1 each)

Why it's here: a cast is only as coherent as the NPCs' *motivations*. A Camarilla
elder, a Sabbat templar, and a Glass Walker should reason from genuinely different
values — not just different voices. This is a pure function of the numbers (no
model call, no dependencies), so the campaign-architect can seed a cast whose
worldviews actually differ, and you can calibrate them rather than hand-wave "he's
the traditional one."

It produces *worldview text*, which the architect folds into an NPC's
`profile.md` (actor-safe — values are openly expressed). It's a
Session-Zero / NPC-build aid.

Usage:
    python Tools/cultural_profile.py --list             # the named presets
    python Tools/cultural_profile.py camarilla          # worldview text for a preset
    python Tools/cultural_profile.py camarilla --name "Prince Helena"
    python Tools/cultural_profile.py --self-test
"""

import argparse
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CulturalProfile:
    """A value profile for an NPC, faction, or sub-population.

    Hofstede dimensions run 0..100; WVS axes run -1..1. Defaults sit at the
    neutral midpoint so a sparsely specified profile still renders sensibly.
    """

    name: str
    individualism: float = 50.0          # Hofstede IDV (high = individualist)
    power_distance: float = 50.0         # Hofstede PDI (high = accepts hierarchy)
    uncertainty_avoidance: float = 50.0  # Hofstede UAI (high = prefers rules)
    long_term_orientation: float = 50.0  # Hofstede LTO (high = future-oriented)
    traditional_vs_secular: float = 0.0  # WVS (-1 traditional .. +1 secular)
    survival_vs_self_expression: float = 0.0  # WVS (-1 survival .. +1 self-expr.)
    norms: tuple = ()                    # prescriptive norms they tend to follow
    taboos: tuple = ()                   # behaviours they treat as off-limits


def _band(value, low, mid, high):
    """Map a 0..100 Hofstede dimension onto a qualitative phrase."""
    if value < 33:
        return low
    if value > 66:
        return high
    return mid


def _axis(value, negative, positive):
    """Map a -1..1 WVS axis onto a qualitative phrase."""
    if value < -0.33:
        return negative
    if value > 0.33:
        return positive
    return "balanced between the two"


def describe_profile(p):
    """A compact, human-readable description of a profile's values."""
    parts = [
        _band(p.individualism,
              "strongly group-oriented and loyal to their own",
              "balancing personal and collective interests",
              "strongly individualistic and self-reliant"),
        _band(p.power_distance,
              "expecting flat, earned relationships and chafing at rank",
              "accepting hierarchy where it's warranted",
              "comfortable with steep hierarchy and deference to elders/rank"),
        _band(p.uncertainty_avoidance,
              "at ease with ambiguity, improvisation, and broken rules",
              "moderately rule-following",
              "craving clear rules, doctrine, and predictability"),
        _band(p.long_term_orientation,
              "fixed on the present and immediate results",
              "weighing present against future",
              "patient and long-game, willing to defer gratification for generations"),
    ]
    wvs = [
        _axis(p.traditional_vs_secular,
              "guided by tradition, lineage, and established authority",
              "guided by secular-rational calculation"),
        _axis(p.survival_vs_self_expression,
              "prioritising security, loyalty, and survival above all",
              "prioritising autonomy, self-expression, and trust"),
    ]
    return "; ".join(parts + wvs)


def profile_to_persona(name, profile):
    """A worldview paragraph for `name`. None → a neutral, unmarked outlook."""
    if profile is None:
        return f"{name} holds no especially marked worldview."
    s = f"{name} sees the world through the {profile.name} outlook, and is " \
        + describe_profile(profile)
    if profile.norms:
        s += ". They generally hold to: " + "; ".join(profile.norms)
    if profile.taboos:
        s += ". They treat as off-limits: " + "; ".join(profile.taboos)
    return s + "."


# A library of value archetypes. The four generic ones are the source presets;
# the World-of-Darkness archetypes below are *illustrative* faction outlooks —
# calibrate the numbers (or write your own) for the chronicle you're running.
# These describe value-systems, not splats: a Camarilla Brujah can hold an
# 'anarch' outlook, a corporate Glass Walker a 'technocratic' one.
PRESET_PROFILES = {
    # — generic anchors (from the_city) —
    "individualist": CulturalProfile(
        "individualist", individualism=85, power_distance=30,
        uncertainty_avoidance=40, traditional_vs_secular=0.4,
        survival_vs_self_expression=0.6,
        norms=("keep your word", "respect others' choices")),
    "collectivist": CulturalProfile(
        "collectivist", individualism=20, power_distance=60,
        uncertainty_avoidance=55, long_term_orientation=70,
        traditional_vs_secular=-0.3, survival_vs_self_expression=-0.2,
        norms=("the group comes first", "honour your elders and oaths")),
    "egalitarian": CulturalProfile(
        "egalitarian", individualism=60, power_distance=15,
        uncertainty_avoidance=35, traditional_vs_secular=0.5,
        survival_vs_self_expression=0.7,
        norms=("treat everyone as an equal", "decide by open argument")),
    "hierarchical": CulturalProfile(
        "hierarchical", individualism=35, power_distance=85,
        uncertainty_avoidance=65, long_term_orientation=60,
        traditional_vs_secular=-0.4, survival_vs_self_expression=-0.3,
        norms=("defer to rank", "keep order and proper roles")),
    # — World of Darkness faction outlooks (illustrative, calibratable) —
    "camarilla": CulturalProfile(
        "Camarilla", individualism=40, power_distance=88,
        uncertainty_avoidance=70, long_term_orientation=85,
        traditional_vs_secular=-0.4, survival_vs_self_expression=-0.4,
        norms=("uphold the Masquerade", "respect the elders and the Traditions"),
        taboos=("diablerie of one's betters", "breaching the Masquerade")),
    "sabbat": CulturalProfile(
        "Sabbat", individualism=30, power_distance=45,
        uncertainty_avoidance=25, long_term_orientation=40,
        traditional_vs_secular=-0.2, survival_vs_self_expression=-0.5,
        norms=("loyalty to the pack above the self", "embrace the monster, refuse the leash"),
        taboos=("bowing to Antediluvian masters", "cowardice before the pack")),
    "anarch": CulturalProfile(
        "Anarch", individualism=80, power_distance=18,
        uncertainty_avoidance=30, traditional_vs_secular=0.5,
        survival_vs_self_expression=0.7,
        norms=("no one rules another by birthright", "freedom is taken, not granted")),
    "technocratic": CulturalProfile(
        "Technocratic", individualism=45, power_distance=75,
        uncertainty_avoidance=92, long_term_orientation=80,
        traditional_vs_secular=0.9, survival_vs_self_expression=-0.3,
        norms=("consensus reality must be managed", "progress through control and method"),
        taboos=("reckless Reality Deviance", "unmeasured belief")),
    "tradition-mage": CulturalProfile(
        "Tradition mystic", individualism=70, power_distance=35,
        uncertainty_avoidance=30, traditional_vs_secular=0.0,
        survival_vs_self_expression=0.8,
        norms=("will shapes reality", "your paradigm is your truth")),
    "garou-tribal": CulturalProfile(
        "Garou tribal", individualism=25, power_distance=80,
        uncertainty_avoidance=55, long_term_orientation=75,
        traditional_vs_secular=-0.6, survival_vs_self_expression=-0.4,
        norms=("honour, glory, wisdom", "the sept and Gaia before the self"),
        taboos=("suffering the Wyrm to live", "shaming one's auspice or totem")),
}


def _self_test():
    # Banding maps the extremes the way the persona depends on.
    assert _band(10, "lo", "mid", "hi") == "lo"
    assert _band(50, "lo", "mid", "hi") == "mid"
    assert _band(90, "lo", "mid", "hi") == "hi"
    assert _axis(-0.9, "neg", "pos") == "neg"
    assert _axis(0.0, "neg", "pos") == "balanced between the two"
    assert _axis(0.9, "neg", "pos") == "pos"

    cam = PRESET_PROFILES["camarilla"]
    d = describe_profile(cam)
    assert "steep hierarchy" in d and "tradition" in d, d
    persona = profile_to_persona("Prince Helena", cam)
    assert persona.startswith("Prince Helena sees the world through the Camarilla outlook")
    assert "Masquerade" in persona  # norms folded in
    assert profile_to_persona("X", None) == "X holds no especially marked worldview."

    # Contrasting presets must actually read differently (the whole point).
    assert describe_profile(PRESET_PROFILES["anarch"]) != \
        describe_profile(PRESET_PROFILES["camarilla"])

    print("cultural_profile self-test: OK")
    return 0


def main(argv):
    p = argparse.ArgumentParser(
        description="Render an NPC/faction value profile into worldview text.")
    p.add_argument("preset", nargs="?", help="a named preset (see --list)")
    p.add_argument("--name", default="This character",
                   help="who the worldview belongs to (for the persona sentence)")
    p.add_argument("--list", action="store_true", help="list the named presets")
    p.add_argument("--self-test", action="store_true", help="run assertions and exit")
    args = p.parse_args(argv[1:])

    if args.self_test:
        return _self_test()
    if args.list or not args.preset:
        print("Presets (illustrative — calibrate or write your own):")
        for k, v in PRESET_PROFILES.items():
            print(f"  {k:16} — {describe_profile(v).split(';')[0].strip()}")
        return 0
    prof = PRESET_PROFILES.get(args.preset.lower())
    if prof is None:
        print(f"Unknown preset '{args.preset}'. Try --list.")
        return 1
    print(profile_to_persona(args.name, prof))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
