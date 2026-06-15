#!/usr/bin/env python3
"""Deterministic world-scribe for the living world (model-free templater).

After `world_tick.py` selects which agents moved, this tool records the ROUTINE
off-screen movement as plain, true facts — **with no language model at all.**

History: this step used to run a local LLM (qwen) that *invented* "the single
most consequential thing each agent did." A small model inventing World-of-
Darkness facts drifts badly (it gave a Toreador a memory-erasure power, a Mind
charm to a vampire with no Mind sphere, etc.), so the generative local tier was
RETIRED. Instead:

    * ROUTINE movers  → a deterministic template, straight from the metronome's
      structured facts (name, FSM state, clock, goal, why-flagged). The body
      states the *true, abstract* fact ("X pressed on toward their goal; clock
      now 4/6") and never fabricates a concrete event or a power. Fabrication is
      structurally impossible because nothing is generated.
    * COLLISIONS, REFLECTION, and PIVOTAL movers → NOT resolved here. They are
      printed as a hand-off manifest for the GM to run a Claude world-director
      (`world-director-lite` on Sonnet for ordinary collisions / faction turns /
      reflection; `world-director` on Opus for anything turning on a secret or a
      planned reveal).

Routine developments are appended to Game/developments.md in the engine's
standard entry format and propagated over the social graph. The literature still
lives on Claude — this tier produces only facts.

Usage:
    python Tools/world_scribe.py             # template the current tick queue
    python Tools/world_scribe.py --dry-run   # show what it WOULD write; write nothing
    python Tools/world_scribe.py --self-test # built-in assertions (no model, no Ollama)
"""

import argparse
import re
import sys
from pathlib import Path

import local_config  # only for enable_utf8_output (no network, no model)

try:
    import social  # information propagation over the relationship graph
except Exception:  # pragma: no cover
    social = None

# Deterministic thresholds (the dial that used to be a local critic's judgment).
ESCALATE_SALIENCE = 5       # a mover this salient is pivotal → hand to a director
SURFACE_SOON_SALIENCE = 4   # this salient (or a filled clock) → surfaces "soon"
HEADLINE_MAX = 70


def current_day(root):
    p = Path(root) / "Game" / "current-scene.md"
    if p.exists():
        m = re.search(r"Day\s+(\d+)", p.read_text(encoding="utf-8"))
        if m:
            return int(m.group(1))
    return None


def parse_queue(text):
    """Parse Game/.world-tick-queue.md into a list of agent dicts."""
    agents, cur = [], None
    for ln in text.splitlines():
        h = re.match(r"^##\s+(.*\S)\s*$", ln)
        if h:
            if cur:
                agents.append(cur)
            cur = None
            # The agent-mover sections always precede these special sections;
            # stop so their `- Source:` lines aren't mistaken for agents.
            if h.group(1).strip() in ("Interactions", "Reflection"):
                break
            cur = {"name": h.group(1).strip(), "source": None, "state": None,
                   "clock": None, "salience": None, "goal": None, "why": None}
            continue
        if cur is None:
            continue
        b = ln.strip()
        if b.startswith("- Source:"):
            m = re.search(r"`([^`]+)`", b)
            cur["source"] = m.group(1) if m else None
        elif b.startswith("- State:"):
            sm = re.search(r"State:\s*`([^`]+)`", b)
            cm = re.search(r"Clock:\s*(\d+/\d+)", b)
            slm = re.search(r"Salience:\s*(\d+)", b)
            cur["state"] = sm.group(1) if sm else None
            cur["clock"] = cm.group(1) if cm else None
            cur["salience"] = slm.group(1) if slm else None
        elif b.startswith("- Goal:"):
            cur["goal"] = b[len("- Goal:"):].strip()
        elif b.startswith("- Why flagged:"):
            cur["why"] = b[len("- Why flagged:"):].strip()
    if cur:
        agents.append(cur)
    return [a for a in agents if a.get("source")]  # real agent sections only


def parse_interactions(text):
    """Parse the '## Interactions' section of the queue into interaction dicts.

    Agent sections use '## name'; interaction entries use '### a vs b' nested under
    a single '## Interactions' heading, so they never collide with `parse_queue`.
    """
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+Interactions\s*$", ln):
            start = i + 1
            break
    if start is None:
        return []
    end = len(lines)
    for i in range(start, len(lines)):
        # the section ends at the next level-2 heading ('## ', not '### ')
        if re.match(r"^##\s+\S", lines[i]) and not lines[i].startswith("###"):
            end = i
            break
    items, cur = [], None
    for ln in lines[start:end]:
        h = re.match(r"^###\s+(.*\S)\s*$", ln)
        if h:
            if cur:
                items.append(cur)
            cur = {"title": h.group(1).strip(), "kind": None, "over": None,
                   "participants": [], "why": None, "hint": None, "ledger": None}
            m = re.search(r"over\s+`([^`]+)`", cur["title"])
            if m:
                cur["over"] = m.group(1)
            continue
        if cur is None:
            continue
        b = ln.strip()
        if b.startswith("- Kind:"):
            cur["kind"] = b[len("- Kind:"):].strip()
        elif b.startswith("- Participants:"):
            cur["participants"] = re.findall(r"([A-Za-z0-9_\-]+)\s*\(`([^`]+)`\)", b)
        elif b.startswith("- Why:"):
            cur["why"] = b[len("- Why:"):].strip()
        elif b.startswith("- Advantage hint:"):
            cur["hint"] = b[len("- Advantage hint:"):].strip()
        elif b.startswith("- Control ledger:"):
            cur["ledger"] = b[len("- Control ledger:"):].strip()
    if cur:
        items.append(cur)
    for it in items:
        if it.get("kind") == "player-pressure" and not it.get("over"):
            it["over"] = "player"
    return [it for it in items if it.get("kind")]


def parse_reflection(text):
    """Parse the '## Reflection' section into [{name, source, trigger}]."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+Reflection\s*$", ln):
            start = i + 1
            break
    if start is None:
        return []
    end = len(lines)
    for i in range(start, len(lines)):
        if re.match(r"^##\s+\S", lines[i]) and not lines[i].startswith("###"):
            end = i
            break
    items, cur = [], None
    for ln in lines[start:end]:
        h = re.match(r"^###\s+(.*\S)\s*$", ln)
        if h:
            if cur:
                items.append(cur)
            cur = {"name": h.group(1).strip(), "source": None, "trigger": None}
            continue
        if cur is None:
            continue
        b = ln.strip()
        if b.startswith("- Source:"):
            m = re.search(r"`([^`]+)`", b)
            cur["source"] = m.group(1) if m else None
        elif b.startswith("- Trigger:"):
            cur["trigger"] = b[len("- Trigger:"):].strip()
    if cur:
        items.append(cur)
    return [it for it in items if it.get("source")]


# --------------------------------------------------------------------------- #
# Deterministic templating — the heart of the model-free scribe.
# --------------------------------------------------------------------------- #


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _short(s, n=HEADLINE_MAX):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n].rstrip() + "…"


def is_pivotal(a):
    """A routine mover that the local tier should NOT own: highly salient, or a
    clock just filled (a threat arriving). These get handed to a Claude director."""
    sal = _to_int(a.get("salience"))
    why = (a.get("why") or "").lower()
    return (sal is not None and sal >= ESCALATE_SALIENCE) or "clock filled" in why


def surface_for(a, pivotal):
    """Deterministic Surface timing for a routine mover (never 'now' — that is
    for collisions / player-pressure, which a director stages)."""
    sal = _to_int(a.get("salience"))
    clock_filled = "clock filled" in (a.get("why") or "").lower()
    if pivotal or clock_filled or (sal is not None and sal >= SURFACE_SOON_SALIENCE):
        return "soon"
    return "hidden"


def format_entry(day, a):
    """Render one routine mover as a developments.md entry — purely from facts."""
    dl = f"Day {day}" if day is not None else "Day ?"
    name = a["name"]
    goal = a.get("goal") or "(unstated aim)"
    why = a.get("why") or "advanced this tick"
    clock = a.get("clock") or "?"
    pivotal = is_pivotal(a)
    surface = surface_for(a, pivotal)

    headline = _short(f"{name} advances — {goal}")
    # Don't echo the clock twice when the why-line already names it.
    clock_tail = "" if "clock" in why.lower() else f"; clock now {clock}"
    body = (f"{name[:1].upper() + name[1:]} pressed on toward their goal "
            f"({goal}) this tick — {why}{clock_tail}.")
    lines = [
        f"## [{dl}] — {name}: {headline}",
        f"- {body}",
    ]
    if surface == "soon":
        lines.append("- Surface: soon (trigger: when the Player next crosses "
                     "this thread)")
    else:
        lines.append("- Surface: hidden")
    lines.append(f"- Arc: {name}")
    lines.append("- Source: templated (world_scribe — deterministic, no model)")
    if pivotal:
        lines.append("- Escalate: claude (run a world-director to give this "
                     "beat real prose)")
    lines.append("- Drained: no")
    return "\n".join(lines)


def append_developments(root, entries):
    p = Path(root) / "Game" / "developments.md"
    if p.exists():
        text = p.read_text(encoding="utf-8")
    else:
        text = "# Developments\n\n## Pending\n\n*(none yet)*\n"
    block = "\n\n".join(entries).strip()
    if "## Pending" in text:
        idx = text.index("## Pending")
        nl = text.index("\n", idx)
        head, rest = text[:nl + 1], text[nl + 1:]
        rest = re.sub(r"^\s*\*\(none yet\)\*\s*\n", "", rest, count=1)
        text = head + "\n" + block + "\n\n" + rest.lstrip("\n")
    else:
        text = text.rstrip() + "\n\n## Pending\n\n" + block + "\n"
    p.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# The hand-off manifest — what the GM must run a Claude director for.
# --------------------------------------------------------------------------- #


def manifest_lines(interactions, reflectors, escalated_movers):
    """Build the stdout hand-off manifest (the generative work is Claude's now)."""
    out = ["", "— Hand-off to Claude (the local generative tier is retired) —"]
    if interactions:
        out.append(f"  Collisions to resolve ({len(interactions)}): "
                   + "; ".join(it["title"] for it in interactions))
        out.append("    → invoke `world-director-lite` (Sonnet). Use "
                   "`world-director` (Opus) for any beat turning on a secret or "
                   "a planned reveal.")
    if reflectors:
        out.append(f"  Reflect / re-plan ({len(reflectors)}): "
                   + ", ".join(rf["name"] for rf in reflectors))
        out.append("    → invoke `world-director-lite` to synthesise beliefs and "
                   "re-plan their drives.md.")
    if escalated_movers:
        out.append(f"  Pivotal movers ({len(escalated_movers)}): "
                   + ", ".join(escalated_movers))
        out.append("    → escalate to a world-director for proper staging.")
    if not (interactions or reflectors or escalated_movers):
        out.append("  (nothing to escalate — every move was templated locally.)")
    return out


def run(root, dry_run=False, verbose=True):
    root = Path(root)
    qpath = root / "Game" / ".world-tick-queue.md"
    if not qpath.exists():
        print("No world-tick queue. Run Tools/world_tick.py first.")
        return 1
    qtext = qpath.read_text(encoding="utf-8")
    agents = parse_queue(qtext)
    interactions = parse_interactions(qtext)
    reflectors = parse_reflection(qtext)
    if not agents and not interactions and not reflectors:
        print("Queue is empty — nothing to scribe.")
        return 0

    day = current_day(root)
    entries, observations, escalated_movers = [], [], []
    for a in agents:
        entries.append(format_entry(day, a))
        pivotal = is_pivotal(a)
        if pivotal:
            escalated_movers.append(a["name"])
        if surface_for(a, pivotal) != "hidden":   # observable → propagates
            observations.append({"participants": [a["name"]],
                                 "headline": _short(a.get("goal") or "something stirred"),
                                 "day": day})

    if dry_run:
        print("=== would template these routine developments ===\n")
        print("\n\n".join(entries) if entries else "(no routine movers)")
        for ln in manifest_lines(interactions, reflectors, escalated_movers):
            print(ln)
        print(f"\n(--dry-run: {len(agents)} mover(s), {len(interactions)} "
              f"interaction(s), {len(reflectors)} reflection(s); nothing written.)")
        return 0

    if entries:
        append_developments(root, entries)
    propagated = 0
    if social is not None and observations:
        try:
            propagated = social.propagate(root, observations)
        except Exception as e:
            if verbose:
                print(f"(social propagation skipped: {e})")

    if verbose:
        print(f"Templated {len(entries)} routine development(s) into "
              f"Game/developments.md (deterministic, no model).")
        if propagated:
            print(f"Propagated {propagated} observation(s) into NPC memories "
                  f"(who'd plausibly hear).")
        for ln in manifest_lines(interactions, reflectors, escalated_movers):
            print(ln)
    return 0


def _find_root(start):
    cur = Path(start).resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return Path(start)


def main(argv):
    local_config.enable_utf8_output()
    p = argparse.ArgumentParser(
        description="Deterministic, model-free world-scribe for the living world.")
    p.add_argument("--dry-run", action="store_true",
                   help="show what it would template; write nothing")
    p.add_argument("--self-test", action="store_true",
                   help="run built-in assertions (no model, no Ollama)")
    args = p.parse_args(argv[1:])

    if args.self_test:
        return _self_test()
    root = _find_root(Path.cwd())
    try:
        return run(root, dry_run=args.dry_run)
    except Exception as e:
        print(f"world_scribe error: {e}")
        return 1


def _self_test():
    import tempfile

    # --- queue parsing (unchanged behavior) ---
    q = (
        "# World-tick queue (for the world-director subagent)\n\n"
        "## vance\n"
        "- Source: `Cast/vance/drives.md`\n"
        "- State: `moving`  |  Clock: 4/4  |  Salience: 4\n"
        "- Goal: pursue control of `harbor-council` (seat before the festival)\n"
        "- Why flagged: entered **moving** (was scheming), **clock filled**\n"
    )
    agents = parse_queue(q)
    assert len(agents) == 1 and agents[0]["name"] == "vance"
    assert agents[0]["clock"] == "4/4" and agents[0]["salience"] == "4"

    # --- deterministic templating: no model, true/abstract facts only ---
    routine = {"name": "mara", "goal": "pursue influence over the docks",
               "why": "clock advanced to 2/6", "clock": "2/6", "salience": "2"}
    e = format_entry(9, routine)
    assert "## [Day 9] — mara:" in e
    assert "templated (world_scribe" in e          # transparently machine-made
    assert "Surface: hidden" in e                   # low salience → hidden
    assert "Escalate: claude" not in e              # not pivotal
    assert "Drained: no" in e

    # A filled clock is pivotal → escalated, and surfaces soon.
    e2 = format_entry(9, agents[0])
    assert "Escalate: claude" in e2 and "Surface: soon" in e2
    assert is_pivotal(agents[0]) and surface_for(agents[0], True) == "soon"

    # Salience 5 alone is pivotal even without a filled clock.
    assert is_pivotal({"salience": "5", "why": "clock advanced to 1/6"})
    assert not is_pivotal({"salience": "3", "why": "clock advanced to 1/6"})

    # --- end-to-end run: templates a routine mover, writes developments ---
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "CLAUDE.md").write_text("x", encoding="utf-8")
        (root / "Game").mkdir()
        (root / "Game" / ".world-tick-queue.md").write_text(
            "## mara\n- Source: `Cast/mara/drives.md`\n"
            "- State: `scheming`  |  Clock: 2/6  |  Salience: 2\n"
            "- Goal: pursue influence over the docks\n"
            "- Why flagged: clock advanced to 2/6\n", encoding="utf-8")
        (root / "Game" / "current-scene.md").write_text(
            "**Day 14 — evening.** The Salt Quarter.\n", encoding="utf-8")
        (root / "Game" / "developments.md").write_text(
            "# Developments\n\n## Pending\n\n*(none yet)*\n", encoding="utf-8")

        rc = run(root, verbose=False)
        assert rc == 0
        dev = (root / "Game" / "developments.md").read_text(encoding="utf-8")
        assert "## [Day 14] — mara: mara advances" in dev, dev
        assert "templated (world_scribe" in dev
        assert "*(none yet)*" not in dev            # placeholder removed
        assert "Escalate: claude" not in dev        # routine, not pivotal

    # --- interactions + reflection are NOT resolved here; they go to the manifest ---
    qi = (
        "## Interactions\n\n"
        "### mara vs vance over `harbor-council`\n"
        "- Kind: contested-goal\n"
        "- Participants: mara (`Cast/mara/drives.md`), vance (`Cast/vance/drives.md`)\n"
        "- Why: both reach for `harbor-council`; they are rival (-4)\n\n"
        "## Reflection\n\n"
        "### vance\n- Source: `Cast/vance/drives.md`\n- Trigger: entered moving\n")
    ix = parse_interactions(qi)
    rf = parse_reflection(qi)
    assert len(ix) == 1 and ix[0]["over"] == "harbor-council"
    assert len(rf) == 1 and rf[0]["name"] == "vance"
    man = "\n".join(manifest_lines(ix, rf, ["vance"]))
    assert "Collisions to resolve (1)" in man and "world-director-lite" in man
    assert "Reflect / re-plan (1)" in man
    assert "Pivotal movers (1)" in man
    # empty queue → an explicit "nothing to escalate" line, never a crash
    assert "nothing to escalate" in "\n".join(manifest_lines([], [], []))

    # No reference to a local LLM remains in this module. (Needles built by
    # concatenation so this very assertion doesn't match itself in the source.)
    src = Path(__file__).read_text(encoding="utf-8")
    no_llm_client = "local_" + "client"
    no_gen_hook = "gen_" + "fn"
    assert no_llm_client not in src, "world_scribe must not import a local LLM client"
    assert no_gen_hook not in src, "world_scribe must not call a generation hook"

    print("world_scribe self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
