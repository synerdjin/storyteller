#!/usr/bin/env python3
"""Local plot-scribe + critic for the living world (token-saving tier).

After `world_tick.py` selects which agents moved, the EXPENSIVE step today is
the Opus `world-director` deciding what they do and writing it up. For routine
ticks that frontier reasoning is overkill. This tool runs that bookkeeping on a
LOCAL model instead:

    1. PLOT SCRIBE — for each queued agent, retrieves relevant campaign context
       (via memory_search, gm scope) and writes a terse, structured account of
       what they did off-screen.
    2. CRITIC — triages each development: salience, whether it's prose-worthy
       (default: all are eligible), and whether it's a PIVOTAL beat that should
       ESCALATE to Claude's world-director instead of being handled locally.

The result is appended to Game/developments.md in the engine's standard entry
format, with the critic's verdict attached. Pivotal beats are flagged
`Escalate: claude` and left for the GM to run the real world-director — the
local model never fabricates a planned reveal or a secret's payoff.

Usage:
    python Tools/world_scribe.py             # scribe the current tick queue (needs Ollama)
    python Tools/world_scribe.py --dry-run   # print the prompts it WOULD send; no model
    python Tools/world_scribe.py --self-test # assertions with a stub model (no Ollama)
"""

import argparse
import json
import re
import sys
from pathlib import Path

import local_config
import memory_search

try:
    import local_client
except Exception:  # pragma: no cover
    local_client = None

# Default system prompts. Overridable by editing the matching files in
# Tools/local-agents/ — those win if present.
DEFAULT_PLOT_SYS = (
    "You are the WORLD SCRIBE for a solo World of Darkness game. You record what "
    "an off-screen agent (an NPC or faction) actually does between scenes — "
    "concrete facts, never purple prose. You stay strictly consistent with the "
    "agent's goal and the retrieved context, and you never invent a secret's "
    "payoff or a reveal — only the move that the agent visibly makes. You answer "
    "with one JSON object and nothing else."
)
DEFAULT_CRITIC_SYS = (
    "You are the CRITIC for a solo World of Darkness game. You triage off-screen "
    "developments: how much they press on the story, whether they are worth "
    "turning into prose (by default, all of them are eligible), and whether they "
    "are PIVOTAL enough — a planned reveal, a major faction move, anything that "
    "turns on a hidden secret — to need a frontier model rather than local "
    "handling. You answer with one JSON object and nothing else."
)


def _load_sys(name, default):
    p = Path(__file__).resolve().parent / "local-agents" / name
    if p.exists():
        txt = p.read_text(encoding="utf-8").strip()
        if txt:
            return txt
    return default


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


def plot_prompt(agent, context):
    return (
        f"An off-screen agent just moved. Write what they actually did.\n\n"
        f"AGENT: {agent['name']}\n"
        f"GOAL: {agent['goal']}\n"
        f"STATE: {agent['state']}   CLOCK: {agent['clock']}   "
        f"SALIENCE: {agent['salience']}\n"
        f"WHY FLAGGED THIS TICK: {agent['why']}\n\n"
        f"RELEVANT CAMPAIGN CONTEXT (retrieved — do not contradict it):\n"
        f"{context or '(none retrieved)'}\n\n"
        f"Decide the single most consequential thing this agent does off-screen "
        f"now, consistent with their goal and the context. Return ONLY this JSON:\n"
        f'{{"headline": "<=8 words", "what_happened": "2-3 sentences, concrete, '
        f'past tense", "surface": "now|soon|hidden", "trigger": "<if soon: what '
        f'reveals it, else empty>", "arc": "<short arc id, or the agent name>"}}'
    )


def critic_prompt(agent, plot):
    return (
        f"Triage this off-screen development. Score it.\n\n"
        f"AGENT: {agent['name']} (salience {agent['salience']})\n"
        f"DEVELOPMENT: {plot.get('headline')} — {plot.get('what_happened')}\n"
        f"PROPOSED SURFACE TIMING: {plot.get('surface')}\n\n"
        f"Default: every development is eligible to become prose. Reserve "
        f"needs_claude for PIVOTAL beats (a planned reveal, a major faction move, "
        f"anything turning on a hidden secret). Return ONLY this JSON:\n"
        f'{{"salience": 1-5, "prose_worthy": true|false, '
        f'"needs_claude": true|false, "reason": "<one short clause>"}}'
    )


def parse_json(text):
    """Extract the first balanced {...} object from model output."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced JSON in model output")


def format_entry(day, agent, plot, verdict):
    dl = f"Day {day}" if day is not None else "Day ?"
    headline = plot.get("headline") or "(off-screen move)"
    lines = [
        f"## [{dl}] — {agent['name']}: {headline}",
        f"- {(plot.get('what_happened') or '').strip()}",
    ]
    surface = plot.get("surface") or "hidden"
    if surface == "soon" and plot.get("trigger"):
        lines.append(f"- Surface: soon (trigger: {plot['trigger']})")
    else:
        lines.append(f"- Surface: {surface}")
    if plot.get("arc"):
        lines.append(f"- Arc: {plot['arc']}")
    lines.append(
        f"- Critic: salience {verdict.get('salience')}, "
        f"prose-worthy {verdict.get('prose_worthy')}, "
        f"needs-Claude {verdict.get('needs_claude')} — {verdict.get('reason', '')}")
    if verdict.get("needs_claude"):
        lines.append("- Escalate: claude (run the world-director on this beat)")
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


def run(root, dry_run=False, gen_fn=None, verbose=True):
    root = Path(root)
    qpath = root / "Game" / ".world-tick-queue.md"
    if not qpath.exists():
        print("No world-tick queue. Run Tools/world_tick.py first.")
        return 1
    agents = parse_queue(qpath.read_text(encoding="utf-8"))
    if not agents:
        print("Queue is empty — nothing to scribe.")
        return 0

    sys_plot = _load_sys("plot-scribe.md", DEFAULT_PLOT_SYS)
    sys_critic = _load_sys("critic.md", DEFAULT_CRITIC_SYS)
    day = current_day(root)
    cfg = local_config.load_config(root)
    if gen_fn is None and not dry_run:
        if local_client is None:
            raise RuntimeError("local_client unavailable; cannot call local model")
        gen_fn = lambda system, prompt: local_client.generate(
            prompt, system=system, cfg=cfg, options={"temperature": 0.7})

    entries, escalations = [], []
    for a in agents:
        context = ""
        if not dry_run:
            try:
                scored = memory_search.search_text(
                    root, f"{a['name']}: {a['goal']}", scope="gm", k=6, cfg=cfg)
                context = memory_search.format_results(scored, snippet=200)
            except Exception as e:
                context = f"(retrieval unavailable: {e})"
        pprompt = plot_prompt(a, context)
        if dry_run:
            print(f"\n=== {a['name']} — PLOT SCRIBE ===")
            print(f"[system]\n{sys_plot}\n[user]\n{pprompt}")
            print(f"\n=== {a['name']} — CRITIC (after plot) ===")
            print(f"[system]\n{sys_critic}\n[user]\n"
                  f"{critic_prompt(a, {'headline': '<plot headline>', 'what_happened': '<plot body>', 'surface': '<surface>'})}")
            continue
        plot = parse_json(gen_fn(sys_plot, pprompt))
        verdict = parse_json(gen_fn(sys_critic, critic_prompt(a, plot)))
        entries.append(format_entry(day, a, plot, verdict))
        if verdict.get("needs_claude"):
            escalations.append(a["name"])

    if dry_run:
        print(f"\n(--dry-run: {len(agents)} agent(s); prompts above, nothing written.)")
        return 0

    append_developments(root, entries)
    if verbose:
        print(f"Scribed {len(entries)} development(s) into Game/developments.md.")
        if escalations:
            print("Escalate to Claude's world-director for pivotal beats: "
                  + ", ".join(escalations))
    return 0


def _find_root(start):
    cur = Path(start).resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return Path(start)


def main(argv):
    p = argparse.ArgumentParser(
        description="Local plot-scribe + critic for the living world.")
    p.add_argument("--dry-run", action="store_true",
                   help="print the prompts it would send; call no model, write nothing")
    p.add_argument("--self-test", action="store_true",
                   help="run built-in assertions with a stub model (no Ollama)")
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

    # JSON extraction tolerates fences and preamble.
    assert parse_json('Sure! ```json\n{"a": 1, "b": "x}y"}\n```')["b"] == "x}y"

    q = (
        "# World-tick queue (for the world-director subagent)\n\n"
        "## vance\n"
        "- Source: `Cast/vance/drives.md`\n"
        "- State: `moving`  |  Clock: 4/4  |  Salience: 4\n"
        "- Goal: Seize the harbor council seat before the festival\n"
        "- Why flagged: entered **moving** (was scheming), **clock filled**\n"
    )
    agents = parse_queue(q)
    assert len(agents) == 1 and agents[0]["name"] == "vance"
    assert agents[0]["clock"] == "4/4" and agents[0]["salience"] == "4"

    def stub(system, prompt):
        if "Triage this" in prompt:  # critic
            return ('{"salience": 5, "prose_worthy": true, '
                    '"needs_claude": true, "reason": "a planned reveal"}')
        return ('here you go {"headline": "Vance seizes the docks", '
                '"what_happened": "Vance bribed two clerks and took the customs '
                'house overnight, then called an emergency council vote.", '
                '"surface": "now", "trigger": "", "arc": "harbor-war"}')

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "CLAUDE.md").write_text("x", encoding="utf-8")
        (root / "Game").mkdir()
        (root / "Game" / ".world-tick-queue.md").write_text(q, encoding="utf-8")
        (root / "Game" / "current-scene.md").write_text(
            "**Day 14 — evening.** The Salt Quarter.\n", encoding="utf-8")
        (root / "Game" / "developments.md").write_text(
            "# Developments\n\n## Pending\n\n*(none yet)*\n", encoding="utf-8")

        rc = run(root, gen_fn=stub, verbose=False)
        assert rc == 0
        dev = (root / "Game" / "developments.md").read_text(encoding="utf-8")
        assert "## [Day 14] — vance: Vance seizes the docks" in dev, dev
        assert "Surface: now" in dev
        assert "Arc: harbor-war" in dev
        assert "Escalate: claude" in dev          # critic flagged it pivotal
        assert "Drained: no" in dev
        assert "*(none yet)*" not in dev          # placeholder removed

    print("world_scribe self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
