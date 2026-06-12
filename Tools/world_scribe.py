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

try:
    import social  # information propagation over the relationship graph
except Exception:  # pragma: no cover
    social = None

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
DEFAULT_REFLECT_SYS = (
    "You are the REFLECTION step for a living NPC in a solo World of Darkness "
    "game (the generative-agents 'reflect' stage). Given a character's recent "
    "memories, synthesise ONE or TWO concise, higher-level BELIEFS they would now "
    "hold — about a rival, the Player, their own situation, or their odds. "
    "Beliefs, not events: 'Vance will never yield the docks without blood', not "
    "'Vance hired thugs'. Stay strictly inside what this character could know. "
    "Answer with one JSON object and nothing else."
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


def reflection_prompt(name, trigger, context):
    return (
        f"Reflect as the living NPC '{name}'. They just {trigger or 'reached a beat'}.\n\n"
        f"THEIR RECENT MEMORY (what they know — do not go beyond it):\n"
        f"{context or '(little on record yet)'}\n\n"
        f"Synthesise 1-2 higher-level beliefs this character now holds. Return ONLY "
        f'this JSON:\n{{"beliefs": ["<a belief, one sentence>", "<optional second>"]}}'
    )


def append_reflection(root, source, beliefs, day):
    """Append synthesised beliefs to an agent's drives.md Reflection notes."""
    p = Path(root) / source
    if not p.exists() or not beliefs:
        return False
    text = p.read_text(encoding="utf-8")
    dl = f"Day {day}" if day is not None else "Day ?"
    block = "".join(f"- *[{dl}]* {b.strip()}\n" for b in beliefs if b and b.strip())
    if not block:
        return False
    heading = "## Reflection notes"
    if heading in text:
        idx = text.index(heading)
        nl = text.index("\n", idx)
        text = text[:nl + 1] + block + text[nl + 1:]
    else:
        text = text.rstrip() + f"\n\n{heading}\n{block}"
    p.write_text(text, encoding="utf-8")
    return True


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


def interaction_prompt(ix, context):
    names = ", ".join(n for n, _ in ix["participants"]) or ix["title"]
    over = ix.get("over") or "their aims"
    over = "the Player" if over == "player" else over
    return (
        f"Two forces in the living world just collided off-screen. Resolve what "
        f"actually happens between them this tick — honestly, in character, with no "
        f"fabricated dice and NO predetermined winner.\n\n"
        f"PARTIES: {names}\n"
        f"KIND: {ix['kind']}\n"
        f"CONTESTED: {over}\n"
        f"WHY THEY COLLIDED: {ix.get('why')}\n"
        f"ADVANTAGE HINT (a hint from resources, NOT a verdict): {ix.get('hint') or 'none'}\n"
        f"CONTROL LEDGER (deterministic standing — the score is already decided; "
        f"narrate what it *means*, do NOT contradict or change it): "
        f"{ix.get('ledger') or 'none'}\n\n"
        f"RELEVANT CAMPAIGN CONTEXT (retrieved — do not contradict it):\n"
        f"{context or '(none retrieved)'}\n\n"
        f"Decide the single most consequential thing that happens between them now, "
        f"consistent with the context and each party's nature. Do not resolve a planned "
        f"reveal or a secret's payoff — only the visible move. Return ONLY this JSON:\n"
        f'{{"headline": "<=8 words", "what_happened": "2-3 sentences, concrete, past '
        f'tense", "surface": "now|soon|hidden", "trigger": "<if soon: what reveals it, '
        f'else empty>", "stakes": "<one line: what each side stands to win or lose>", '
        f'"state": "forming|rising|climax"}}'
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


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "plot"


def interaction_plot_id(ix):
    """A stable id for the plot a collision belongs to, so it isn't re-created each tick."""
    names = sorted(n for n, _ in ix.get("participants", []))
    base = "-".join(names) if names else _slug(ix.get("title", "plot"))
    over = ix.get("over")
    if over and over != "player":
        base += "-" + _slug(over)
    return _slug(base)


def existing_plot_ids(root):
    p = Path(root) / "Game" / "plots.md"
    if not p.exists():
        return set()
    return set(re.findall(r"^###\s+(\S+)\s+—", p.read_text(encoding="utf-8"), re.M))


def format_interaction_entry(day, ix, plot, verdict, arc):
    dl = f"Day {day}" if day is not None else "Day ?"
    headline = plot.get("headline") or "(off-screen clash)"
    lines = [
        f"## [{dl}] — {ix['title']}: {headline}",
        f"- {(plot.get('what_happened') or '').strip()}",
    ]
    surface = plot.get("surface") or "hidden"
    if surface == "soon" and plot.get("trigger"):
        lines.append(f"- Surface: soon (trigger: {plot['trigger']})")
    else:
        lines.append(f"- Surface: {surface}")
    lines.append(f"- Arc: {arc}")
    lines.append(
        f"- Critic: salience {verdict.get('salience')}, "
        f"prose-worthy {verdict.get('prose_worthy')}, "
        f"needs-Claude {verdict.get('needs_claude')} — {verdict.get('reason', '')}")
    if verdict.get("needs_claude"):
        lines.append("- Escalate: claude (run the world-director on this clash)")
    lines.append("- Drained: no")
    return "\n".join(lines)


def build_plot_entry(ix, plot, arc, day):
    title = plot.get("headline") or ix["title"]
    parts = ", ".join(n for n, _ in ix.get("participants", [])) or ix["title"]
    surface = plot.get("surface") or "hidden"
    involvement = ("aware" if ix.get("kind") == "player-pressure" and surface == "now"
                   else "unaware")
    surf = (f"soon (trigger: {plot['trigger']})"
            if surface == "soon" and plot.get("trigger") else surface)
    dl = f"Day {day}" if day is not None else "Day ?"
    return "\n".join([
        f"### {arc} — {title}",
        f"- Participants: {parts}",
        f"- Stakes: {plot.get('stakes', '(emerging)')}",
        f"- State: {plot.get('state', 'forming')}",
        "- Clock: 0/4",
        f"- Player involvement: {involvement}",
        f"- Surface: {surf}",
        f"- Arc: {arc}",
        f"- Opened: {dl}",
    ])


def append_plots(root, plot_entries):
    """Insert new '### ' plot entries under the '## World plots' heading."""
    p = Path(root) / "Game" / "plots.md"
    if not p.exists() or not plot_entries:
        return
    text = p.read_text(encoding="utf-8")
    if "## World plots" not in text:
        return
    idx = text.index("## World plots")
    nl = text.index("\n", idx)
    head, rest = text[:nl + 1], text[nl + 1:]
    # the placeholder bullet may carry an italic '*(...)*' note across the line
    rest = re.sub(r"^\s*-\s*\*\(none yet.*?\)\*\s*\n", "", rest, count=1, flags=re.S)
    block = "\n\n".join(plot_entries).strip()
    text = head + "\n" + block + "\n\n" + rest.lstrip("\n")
    p.write_text(text, encoding="utf-8")


def run(root, dry_run=False, gen_fn=None, verbose=True):
    root = Path(root)
    qpath = root / "Game" / ".world-tick-queue.md"
    if not qpath.exists():
        print("No world-tick queue. Run Tools/world_tick.py first.")
        return 1
    qtext = qpath.read_text(encoding="utf-8")
    agents = parse_queue(qtext)
    interactions = parse_interactions(qtext)
    if not agents and not interactions:
        print("Queue is empty — nothing to scribe.")
        return 0

    sys_plot = _load_sys("plot-scribe.md", DEFAULT_PLOT_SYS)
    sys_critic = _load_sys("critic.md", DEFAULT_CRITIC_SYS)
    sys_reflect = _load_sys("reflector.md", DEFAULT_REFLECT_SYS)
    reflectors = parse_reflection(qtext)
    day = current_day(root)
    cfg = local_config.load_config(root)
    if gen_fn is None and not dry_run:
        if local_client is None:
            raise RuntimeError("local_client unavailable; cannot call local model")
        gen_fn = lambda system, prompt: local_client.generate(
            prompt, system=system, cfg=cfg, options={"temperature": 0.7})

    entries, escalations, failed = [], [], []
    observations = []   # observable beats to propagate to the social graph
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
        # Isolate each agent: a single malformed local-model completion must not
        # discard the developments already scribed for the others this tick.
        try:
            plot = parse_json(gen_fn(sys_plot, pprompt))
            verdict = parse_json(gen_fn(sys_critic, critic_prompt(a, plot)))
        except Exception as e:
            failed.append((a["name"], str(e)))
            continue
        entries.append(format_entry(day, a, plot, verdict))
        if verdict.get("needs_claude"):
            escalations.append(a["name"])
        if (plot.get("surface") or "hidden") != "hidden":   # observable → propagates
            observations.append({"participants": [a["name"]],
                                 "headline": plot.get("headline", "something stirred"),
                                 "day": day})

    # Resolve each detected collision, and promote new ones to the plot registry.
    plot_entries, promoted = [], []
    known_ids = existing_plot_ids(root)
    for ix in interactions:
        arc = interaction_plot_id(ix)
        context = ""
        if not dry_run:
            try:
                scored = memory_search.search_text(
                    root, f"{ix['title']}: {ix.get('why') or ''}",
                    scope="gm", k=6, cfg=cfg)
                context = memory_search.format_results(scored, snippet=200)
            except Exception as e:
                context = f"(retrieval unavailable: {e})"
        iprompt = interaction_prompt(ix, context)
        if dry_run:
            print(f"\n=== {ix['title']} — INTERACTION RESOLVER ===")
            print(f"[system]\n{sys_plot}\n[user]\n{iprompt}")
            continue
        try:
            plot = parse_json(gen_fn(sys_plot, iprompt))
            cdict = {"name": ix["title"], "salience": "3"}
            verdict = parse_json(gen_fn(sys_critic, critic_prompt(cdict, plot)))
        except Exception as e:
            failed.append((ix["title"], str(e)))
            continue
        entries.append(format_interaction_entry(day, ix, plot, verdict, arc))
        if verdict.get("needs_claude"):
            escalations.append(ix["title"])
        if (plot.get("surface") or "hidden") != "hidden":
            observations.append({
                "participants": [n for n, _ in ix.get("participants", [])],
                "headline": plot.get("headline", "a clash broke out"),
                "day": day})
        if arc not in known_ids:                       # one plot per collision, ever
            known_ids.add(arc)
            plot_entries.append(build_plot_entry(ix, plot, arc, day))
            promoted.append(arc)

    # Reflection pass — synthesise beliefs for agents who completed a phase.
    reflected = 0
    for rf in reflectors:
        context = ""
        if not dry_run:
            try:
                scored = memory_search.search_text(
                    root, f"{rf['name']}", scope="gm", owner=rf["name"], k=8, cfg=cfg)
                context = memory_search.format_results(scored, snippet=200)
            except Exception:
                context = ""
        rprompt = reflection_prompt(rf["name"], rf.get("trigger"), context)
        if dry_run:
            print(f"\n=== {rf['name']} — REFLECTION ===")
            print(f"[system]\n{sys_reflect}\n[user]\n{rprompt}")
            continue
        try:
            out = parse_json(gen_fn(sys_reflect, rprompt))
            beliefs = out.get("beliefs") or []
        except Exception as e:
            failed.append((f"{rf['name']} (reflection)", str(e)))
            continue
        if append_reflection(root, rf["source"], beliefs, day):
            reflected += 1

    if dry_run:
        print(f"\n(--dry-run: {len(agents)} agent(s), {len(interactions)} "
              f"interaction(s), {len(reflectors)} reflection(s); prompts above, "
              f"nothing written.)")
        return 0

    if entries:
        append_developments(root, entries)
    if plot_entries:
        append_plots(root, plot_entries)
    propagated = 0
    if social is not None and observations:
        try:
            propagated = social.propagate(root, observations)
        except Exception as e:
            if verbose:
                print(f"(social propagation skipped: {e})")
    if verbose:
        print(f"Scribed {len(entries)} development(s) into Game/developments.md.")
        if propagated:
            print(f"Propagated {propagated} observation(s) into NPC memories "
                  f"(who'd plausibly hear).")
        if reflected:
            print(f"Reflected {reflected} agent(s): new beliefs in their drives.md.")
        if promoted:
            print(f"Promoted {len(promoted)} new plot(s) into Game/plots.md: "
                  + ", ".join(promoted))
        if escalations:
            print("Escalate to Claude's world-director for pivotal beats: "
                  + ", ".join(escalations))
        for name, err in failed:
            print(f"Skipped {name}: local model output unusable ({err}). "
                  f"Re-run the tick or scribe this beat via the world-director.")
    return 1 if failed and not entries else 0


def _find_root(start):
    cur = Path(start).resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return Path(start)


def main(argv):
    local_config.enable_utf8_output()
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

    # Durability: one agent's unusable completion must not discard the other's.
    q2 = (
        "## good\n- Source: `Cast/good/drives.md`\n"
        "- State: `moving`  |  Clock: 2/4  |  Salience: 3\n- Goal: open a shop\n"
        "## bad\n- Source: `Cast/bad/drives.md`\n"
        "- State: `moving`  |  Clock: 2/4  |  Salience: 3\n- Goal: burn it down\n"
    )

    def flaky(system, prompt):
        if "AGENT: bad" in prompt:
            return "the model rambled and produced no json at all"
        if "Triage this" in prompt:
            return ('{"salience": 2, "prose_worthy": true, '
                    '"needs_claude": false, "reason": "routine"}')
        return ('{"headline": "Good opens a shop", "what_happened": "Done.", '
                '"surface": "hidden", "trigger": "", "arc": "good"}')

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Game").mkdir()
        (root / "Game" / ".world-tick-queue.md").write_text(q2, encoding="utf-8")
        rc = run(root, gen_fn=flaky, verbose=False)
        assert rc == 0, rc                         # some succeeded → success
        dev = (root / "Game" / "developments.md").read_text(encoding="utf-8")
        assert "Good opens a shop" in dev          # good agent survived
        assert "bad:" not in dev                    # bad agent skipped, not written

    # --- interactions: parse the section, resolve a clash, promote a plot ---
    q3 = (
        "## mara\n- Source: `Cast/mara/drives.md`\n"
        "- State: `scheming`  |  Clock: 1/6  |  Salience: 4\n- Goal: control harbor-council\n"
        "- Why flagged: clock advanced to 1/6\n\n"
        "## Interactions\n\n"
        "### mara vs vance over `harbor-council`\n"
        "- Kind: contested-goal\n"
        "- Participants: mara (`Cast/mara/drives.md`), vance (`Cast/vance/drives.md`)\n"
        "- Why: both reach for `harbor-council`; they are rival (-4)\n"
        "- Advantage hint: mara better-resourced (secrets): mara 6 vs vance 3\n"
        "- Control ledger: mara 6, vance 0, _neutral 4 (holder: mara)  |  phase: climax\n"
        "- Resolver: decide what happens; promote to plots.md.\n"
    )
    ix = parse_interactions(q3)
    assert len(ix) == 1, ix
    assert ix[0]["kind"] == "contested-goal" and ix[0]["over"] == "harbor-council"
    assert [n for n, _ in ix[0]["participants"]] == ["mara", "vance"]
    assert ix[0]["ledger"] and "holder: mara" in ix[0]["ledger"]
    assert "CONTROL LEDGER" in interaction_prompt(ix[0], "")     # fed to the resolver
    assert interaction_plot_id(ix[0]) == "mara-vance-harbor-council"

    def stub3(system, prompt):
        if "Triage this" in prompt:
            return ('{"salience": 4, "prose_worthy": true, '
                    '"needs_claude": true, "reason": "major faction move"}')
        if "collided off-screen" in prompt:        # interaction resolver
            return ('{"headline": "Mara outflanks Vance", "what_happened": "Mara '
                    'leaked a ledger to two councillors and Vance lost the votes he '
                    'was counting on.", "surface": "now", "trigger": "", '
                    '"stakes": "the swing vote on the harbor council", "state": "rising"}')
        return ('{"headline": "Mara works the docks", "what_happened": "x.", '
                '"surface": "hidden", "trigger": "", "arc": "mara"}')

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Game").mkdir()
        (root / "Game" / ".world-tick-queue.md").write_text(q3, encoding="utf-8")
        (root / "Game" / "current-scene.md").write_text(
            "**Day 14 — evening.** The Salt Quarter.\n", encoding="utf-8")
        (root / "Game" / "developments.md").write_text(
            "# Developments\n\n## Pending\n\n*(none yet)*\n", encoding="utf-8")
        (root / "Game" / "plots.md").write_text(
            "# Plots\n\n## World plots\n\n- *(none yet — seeded later.)*\n\n"
            "## Resolved\n\n- *(none yet)*\n", encoding="utf-8")

        rc = run(root, gen_fn=stub3, verbose=False)
        assert rc == 0, rc
        dev = (root / "Game" / "developments.md").read_text(encoding="utf-8")
        assert "Mara outflanks Vance" in dev, dev          # clash scribed
        assert "Escalate: claude" in dev                   # critic flagged pivotal
        plots = (root / "Game" / "plots.md").read_text(encoding="utf-8")
        assert "### mara-vance-harbor-council — Mara outflanks Vance" in plots, plots
        assert "State: rising" in plots
        assert "Participants: mara, vance" in plots
        assert "*(none yet" not in plots.split("## Resolved")[0]  # placeholder gone

        # Idempotent: the same collision next tick must NOT create a second plot.
        (root / "Game" / ".world-tick-queue.md").write_text(q3, encoding="utf-8")
        run(root, gen_fn=stub3, verbose=False)
        plots2 = (root / "Game" / "plots.md").read_text(encoding="utf-8")
        assert plots2.count("### mara-vance-harbor-council") == 1, "no duplicate plot"

    # --- reflection: the agent loop's reflect step ---
    qr = (
        "## mara\n- Source: `Cast/mara/drives.md`\n"
        "- State: `moving`  |  Clock: 3/3  |  Salience: 4\n- Goal: control x\n\n"
        "## Reflection\n\n"
        "### mara\n- Source: `Cast/mara/drives.md`\n- Trigger: entered moving\n")
    # the Reflection section must NOT be mistaken for an agent mover
    assert [a["name"] for a in parse_queue(qr)] == ["mara"], "Reflection isn't an agent"
    rf = parse_reflection(qr)
    assert len(rf) == 1 and rf[0]["name"] == "mara"
    assert rf[0]["source"] == "Cast/mara/drives.md" and rf[0]["trigger"] == "entered moving"
    assert "REFLECTION" in DEFAULT_REFLECT_SYS or "reflect" in DEFAULT_REFLECT_SYS.lower()

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        mp = root / "Cast" / "mara"
        mp.mkdir(parents=True)
        (mp / "drives.md").write_text(
            "---\nliving: true\nstate: moving\n---\n\n## Reflection notes\n",
            encoding="utf-8")
        ok = append_reflection(root, "Cast/mara/drives.md",
                               ["Vance will not yield the docks without blood."], 9)
        drv = (mp / "drives.md").read_text(encoding="utf-8")
        assert ok and "Vance will not yield" in drv and "[Day 9]" in drv, drv
        # creates the heading if missing
        (mp / "drives.md").write_text("---\nliving: true\n---\n", encoding="utf-8")
        append_reflection(root, "Cast/mara/drives.md", ["A new fear took root."], 9)
        assert "## Reflection notes" in (mp / "drives.md").read_text(encoding="utf-8")

    print("world_scribe self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
