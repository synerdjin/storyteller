#!/usr/bin/env python3
"""The living-world *drift* harness for the Storyteller Game Master.

Where `world_tick.py` MOVES the world one beat, this tool AUDITS it: a periodic,
deterministic health check that asks the three questions the D&D-agents
literature found a generative cast tends to fail on when left unsupervised
(Sancheti et al., "Towards LLM-Agents That Play Dungeons & Dragons Using
Iterative Prompting", CEUR Vol-4097): is the world still *progressing toward
goals*, still *colliding/collaborating*, and still *on-tone*? Those map onto the
paper's three annotated action categories, repurposed here as drift metrics.

It is to the campaign's health what `world_tick.py` is to a single beat: the
deterministic, auditable layer. The structural metrics (frozen agents, stalled
clocks, contested targets, stale threads, an un-drained `Surface: now` backlog)
are computed from the same files the metronome reads, with **no model at all**.
The one non-structural signal — tone/compliance drift — is an *optional* local
pass that degrades gracefully to "skipped" when no Ollama server is running.

It writes nothing to your save data. Its only output is a GM-only report,
`Game/.world-health.md` (and stdout). Run it at a save point or session end.

Usage:
    python Tools/world_health.py              # audit; write the report
    python Tools/world_health.py --dry-run    # compute & print, write nothing
    python Tools/world_health.py --stale 6    # 'untouched' threshold = 6 days
    python Tools/world_health.py --no-model    # skip the optional local tone read
    python Tools/world_health.py --self-test   # built-in assertions, no Ollama
"""

import argparse
import re
import sys
from pathlib import Path

# Sibling modules. We REUSE world_tick's controlled-YAML parser and agent
# discovery rather than re-implement them, so the two tools can never disagree
# about what a living agent is. Both are optional: a malformed import must never
# crash a save-point audit.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import world_tick
except Exception:  # pragma: no cover
    world_tick = None
try:
    import ledger as ledger_mod
except Exception:  # pragma: no cover
    ledger_mod = None
try:
    import local_client
except Exception:  # pragma: no cover
    local_client = None

# A placeholder line in a freshly-seeded file ("*(none yet)*"). We must not
# mistake the templates' own scaffolding for real story state.
_PLACEHOLDER = re.compile(r"^\s*[-*]?\s*\*?\(none", re.IGNORECASE)
_DAY = re.compile(r"Day\s+(\d+)", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Parsing the prose state files (plots / threads / developments). These are
# markdown, not YAML — we scan for the documented entry shapes, leniently.
# --------------------------------------------------------------------------- #


def _strip_fences(text):
    """Drop ```fenced``` code blocks — the state files document their own entry
    formats inside fences, and those examples must not be read as real state."""
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append(line)
    return "\n".join(out)


def _bullet(block, key):
    """Value of a `- Key: value` bullet within a block of lines, or None."""
    pat = re.compile(rf"^\s*[-*]\s*{re.escape(key)}\s*:\s*(.+?)\s*$", re.IGNORECASE)
    for line in block:
        m = pat.match(line)
        if m:
            return m.group(1).strip()
    return None


def parse_plots(text):
    """Each `### <id> — <Title>` entry with its State/involvement/Surface/Opened."""
    lines = _strip_fences(text).splitlines()
    heads = [i for i, l in enumerate(lines) if l.lstrip().startswith("### ")]
    out = []
    for k, start in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        title = lines[start].lstrip()[4:].strip()
        if _PLACEHOLDER.match(title):
            continue
        block = lines[start + 1:end]
        out.append({
            "title": title,
            "state": (_bullet(block, "State") or "").lower(),
            "involvement": (_bullet(block, "Player involvement") or "").lower(),
            "surface": (_bullet(block, "Surface") or "").lower(),
            "opened": _first_day(_bullet(block, "Opened") or ""),
        })
    return out


def parse_threads(text):
    """Open `- [ ]` and resolved `- [x]` thread lines, with their opened day."""
    open_, resolved = [], []
    for line in _strip_fences(text).splitlines():
        s = line.strip()
        if _PLACEHOLDER.search(s):
            continue
        m = re.match(r"-\s*\[( |x|X)\]\s*(.*)$", s)
        if not m:
            continue
        body = m.group(2).strip()
        # Strip the trailing `*(opened Day N…)*` note: what's left is the real
        # thread text. A line that is *only* that note is the blank template row.
        core = re.sub(r"\*?\(opened.*?\)\*?", "", body, flags=re.IGNORECASE).strip()
        if not core or _PLACEHOLDER.match(body):
            continue
        rec = {"text": body, "opened": _first_day(body)}
        (resolved if m.group(1).lower() == "x" else open_).append(rec)
    return {"open": open_, "resolved": resolved}


def parse_developments(text):
    """Each `## [Day N — …] — <agent>: headline` entry with Surface/Drained."""
    lines = _strip_fences(text).splitlines()
    heads = [i for i, l in enumerate(lines)
             if re.match(r"^##\s+\[Day\s+\d+", l, re.IGNORECASE)]
    out = []
    for k, start in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        head = lines[start]
        block = lines[start + 1:end]
        drained = (_bullet(block, "Drained") or "no").lower()
        out.append({
            "day": _first_day(head),
            "headline": head.lstrip("# ").strip(),
            "surface": (_bullet(block, "Surface") or "").lower(),
            # Trust ONLY the explicit `- Drained:` bullet. A loose substring on
            # the headline would mis-read "the drained well" as a drained entry.
            "drained": drained.startswith("y") or drained == "drained",
        })
    return out


def _first_day(s):
    m = _DAY.search(s or "")
    return int(m.group(1)) if m else None


def last_seen_day(name, *texts):
    """The most recent `Day N` on any line that names this agent, or None.

    A heuristic 'when did the world last move this agent' read, from the
    day-stamped logs (developments + timeline). Deterministic and honest: it
    over- rather than under-reports silence, which is the safe direction for a
    drift alarm. NB it keys on the agent's *folder slug* (`name`), so an NPC
    whose prose name diverges from the slug (folder `vance`, prose "Don Vance")
    may read as silent — a false "frozen" flag, never a missed real move.
    """
    nm = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
    best = None
    for text in texts:
        for line in (text or "").splitlines():
            if nm.search(line):
                d = _first_day(line)
                if d is not None and (best is None or d > best):
                    best = d
    return best


# --------------------------------------------------------------------------- #
# The audit. Each check appends (severity, message) findings; severity is
# "warn" (drift the GM should nudge) or "note" (informational).
# --------------------------------------------------------------------------- #


def _read(root, rel):
    p = Path(root) / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _clockvals(agent):
    c = world_tick._clock(agent.fields) if world_tick else {}
    return int(c.get("filled", 0) or 0), int(c.get("total", 0) or 0)


def assess(root, stale_days):
    """Compute every structural metric. Returns a report dict (no model calls)."""
    root = Path(root)
    day = world_tick._current_day(root) if world_tick else None
    agents = world_tick.discover_agents(root) if world_tick else []

    plots = parse_plots(_read(root, "Game/plots.md"))
    threads = parse_threads(_read(root, "Game/threads.md"))
    devs = parse_developments(_read(root, "Game/developments.md"))
    log_text = _read(root, "Game/developments.md") + "\n" + _read(root, "Game/timeline.md")

    seeded = bool(agents) or bool(plots)
    rep = {"day": day, "n_agents": len(agents), "seeded": seeded,
           "progression": [], "collision": [], "threads": [], "backlog": [],
           "tone": None}

    # --- (1) Goal progression: is each living agent actually moving? ---------
    contested_targets = {}
    for a in agents:
        t = world_tick.goal_target(a)
        if t and t != "player":
            contested_targets.setdefault(t, []).append(a)
        filled, total = _clockvals(a)
        seen = last_seen_day(a.name, log_text)
        if total and filled >= total:
            rep["progression"].append(
                ("warn", f"{a.name}: clock full ({filled}/{total}) and unresolved "
                         f"— state `{a.fields.get('state')}` is waiting on the director."))
        elif day is not None and seen is not None and day - seen >= stale_days:
            rep["progression"].append(
                ("warn", f"{a.name}: no logged move since Day {seen} "
                         f"({day - seen} days) — clock {filled}/{total}."))
        elif day is not None and seen is None and day > 1:
            rep["progression"].append(
                ("note", f"{a.name}: living but never appears in the logs "
                         f"— has the world used them yet?"))

    # --- (2) Collision/collaboration: is the ensemble actually interacting? --
    live_contests = {t: g for t, g in contested_targets.items()
                     if len(g) >= 2 and not _all_allied(g)}
    open_plots = [p for p in plots if p["state"] in ("forming", "rising", "climax")]
    if agents and not live_contests and not open_plots:
        # A NOTE, not a warning: a quiet stretch is legitimate — WoD's horror
        # lives in dread and slow scenes, and the engine forbids "fixing" quiet
        # with manufactured bustle (CLAUDE.md, Progress clocks). We only observe
        # the standing fact; if it *persists* the GM can choose to seed tension.
        rep["collision"].append(
            ("note", "Quiet: no two living agents contest the same target and no "
                     "plot is forming/rising. Fine for a slow beat — but if it "
                     "holds, the cast has little of their own to pursue."))
    for t, g in live_contests.items():
        rep["collision"].append(
            ("note", f"contested: `{t}` — {', '.join(x.name for x in g)} all reach for it."))
    isolated = [a.name for a in agents if _is_isolated(a, agents)]
    if isolated and len(agents) > 1:
        rep["collision"].append(
            ("note", f"isolated (no ties, no shared target, no group): {', '.join(isolated)} "
                     "— they can't collide, so they can't generate plot."))
    rep["collision"].append(
        ("note", f"plots: {len(open_plots)} active, "
                 f"{sum(1 for p in plots if p['state'] == 'resolved')} resolved."))
    rep["ledgers"] = _ledger_phases(root)

    # --- (3) Threads & backlog: is the Player's view going stale? -----------
    for th in threads["open"]:
        if day is not None and th["opened"] is not None and day - th["opened"] >= stale_days:
            rep["threads"].append(
                ("warn", f"thread open since Day {th['opened']} "
                         f"({day - th['opened']} days), still unresolved: {th['text'][:70]}"))
    pending_now = [d for d in devs if "now" in d["surface"] and not d["drained"]]
    if pending_now:
        rep["backlog"].append(
            ("warn", f"{len(pending_now)} `Surface: now` development(s) never drained "
                     "— weave them in or they pile up as dead pressure:"))
        for d in pending_now[:5]:
            rep["backlog"].append(("note", f"  · {d['headline']}"))
    return rep


def _all_allied(group):
    if not world_tick:
        return False
    return all(world_tick._allied(group[i], group[j])
               for i in range(len(group)) for j in range(i + 1, len(group)))


def _is_isolated(agent, agents):
    if not world_tick:
        return False
    if world_tick._rels(agent):
        return False
    if world_tick._group(agent):
        return False
    t = world_tick.goal_target(agent)
    if t and t != "player":
        others = [o for o in agents if o is not agent and world_tick.goal_target(o) == t]
        if others:
            return False
    return True


def _ledger_phases(root):
    if ledger_mod is None:
        return []
    try:
        ledgers = ledger_mod.load_ledgers(root)
    except Exception:
        return []
    out = []
    for entity, led in (ledgers or {}).items():
        # `load_ledgers` returns ledger.Ledger objects; `phase` is a METHOD, not
        # a dict key. (Guarded so a future shape change can't crash the audit.)
        try:
            phase = led.phase() if hasattr(led, "phase") else None
        except Exception:
            phase = None
        if phase:
            out.append(f"{entity}: phase {phase}")
    return out


# --------------------------------------------------------------------------- #
# Optional tone/compliance read (the one non-structural signal). Local model;
# skipped cleanly when no server is up.
# --------------------------------------------------------------------------- #

_DEFAULT_TONE_SYS = (
    "You are the HEALTH AUDITOR for a solo World of Darkness chronicle, running "
    "on a small local model. You are given the campaign's tone/voice boundaries "
    "and a sample of recent narration and off-screen developments. Judge ONLY "
    "drift: has the prose or the world's moves wandered off the agreed tone, "
    "voice, or content limits, or gone slack on goal-progress? Answer with one "
    "JSON object and nothing else: "
    '{"on_tone": true|false, "drift": "<one short clause, or \'none\'>"}'
)


def _tone_prompt_sys(root):
    f = Path(root) / "Tools" / "local-agents" / "health-auditor.md"
    if f.exists():
        try:
            return f.read_text(encoding="utf-8").strip() or _DEFAULT_TONE_SYS
        except Exception:
            pass
    return _DEFAULT_TONE_SYS


def _extract_json(raw):
    """Return the first parseable top-level JSON object in `raw`, or None.

    Small local models routinely wrap their answer in prose or emit more than
    one object despite a 'JSON only' instruction. A greedy `\\{.*\\}` would span
    from the first `{` to the last `}` and fail to parse; instead we walk for
    balanced `{...}` spans (string- and escape-aware) and return the first that
    loads.
    """
    import json
    depth = start = 0
    in_str = esc = False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                try:
                    val = json.loads(raw[start:i + 1])
                except Exception:
                    continue
                if isinstance(val, dict):
                    return val
    return None


def tone_read(root, use_model):
    """Return (status, detail). status: 'ok' | 'drift' | 'skipped'."""
    if not use_model or local_client is None:
        return ("skipped", "no local model (structural metrics only)")
    boundaries = _read(root, "Game/boundaries.md")
    scene = _read(root, "Game/current-scene.md")
    devs = _read(root, "Game/developments.md")
    if not (scene.strip() or devs.strip()):
        return ("skipped", "nothing to audit yet")
    prompt = (f"# Tone & voice boundaries\n{boundaries}\n\n"
              f"# Most recent scene\n{scene[:2000]}\n\n"
              f"# Recent off-screen developments\n{devs[:2000]}\n")
    try:
        raw = local_client.generate(prompt, system=_tone_prompt_sys(root), root=root)
    except Exception as e:  # LocalUnavailable or anything else — degrade quietly
        return ("skipped", f"local model unavailable: {e}")
    verdict = _extract_json(raw)
    if verdict is None:
        return ("skipped", "auditor returned no parseable JSON")
    if verdict.get("on_tone") is False:
        return ("drift", str(verdict.get("drift") or "tone drift flagged"))
    return ("ok", str(verdict.get("drift") or "none"))


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def _section(out, title, findings):
    out.append(f"## {title}")
    if not findings:
        out.append("- ✓ nothing flagged.")
    for sev, msg in findings:
        mark = "⚠" if sev == "warn" else "·"
        out.append(f"- {mark} {msg}")
    out.append("")


def format_report(rep, tone):
    warns = sum(1 for grp in ("progression", "collision", "threads", "backlog")
                for sev, _ in rep[grp] if sev == "warn")
    out = [
        "# World health (GM ONLY)",
        "",
        "> Generated by `Tools/world_health.py` — a deterministic drift audit. "
        "Ephemeral; safe to delete. Not for the Player.",
        "",
        f"**Day {rep['day']}** · {rep['n_agents']} living agent(s) · "
        f"**{warns} warning(s)**.",
        "",
    ]
    if not rep["seeded"]:
        out += ["The world is not yet seeded (Session Zero pending) — no drift to "
                "measure. Promote some NPCs with a `drives.md` to bring it to life.",
                ""]
        return "\n".join(out) + "\n"
    _section(out, "Goal progression (are agents still moving?)", rep["progression"])
    _section(out, "Collision & collaboration (is the ensemble interacting?)",
             rep["collision"])
    if rep.get("ledgers"):
        out.append("## Control ledgers")
        for line in rep["ledgers"]:
            out.append(f"- · {line}")
        out.append("")
    _section(out, "Threads (is the Player's view going stale?)", rep["threads"])
    _section(out, "Developments backlog", rep["backlog"])
    out.append("## Tone & compliance (optional local read)")
    mark = {"ok": "✓", "drift": "⚠", "skipped": "·"}.get(tone[0], "·")
    out.append(f"- {mark} {tone[0]}: {tone[1]}")
    out.append("")
    if warns == 0:
        out.append("**Verdict:** the world is healthy — keep playing.")
    else:
        out.append("**Verdict:** bookkeeping drift detected. Clear the *mechanical* "
                   "snags — resolve a clock that filled, drain a `Surface: now` beat "
                   "that's piling up, close or advance a thread left hanging. (These "
                   "are forgotten-state fixes, not a cue to manufacture action; a "
                   "quiet world is a choice, not a fault.)")
    return "\n".join(out) + "\n"


def _emit(s):
    """Print without ever dying on a console that can't encode a glyph (Windows
    cp1252). The report file is always written UTF-8; only stdout is at risk."""
    try:
        print(s)
    except UnicodeEncodeError:
        enc = (sys.stdout.encoding or "ascii")
        print(s.encode(enc, "replace").decode(enc))


def run(root, args):
    root = Path(root)
    rep = assess(root, args.stale)
    tone = tone_read(root, use_model=not args.no_model)
    text = format_report(rep, tone)
    if not args.dry_run:
        out = root / "Game" / ".world-health.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    _emit(text)
    if args.dry_run:
        _emit("(--dry-run: no report file written.)")
    return 0


def _find_root(start):
    cur = start.resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return start


def main(argv):
    p = argparse.ArgumentParser(
        description="Audit the living world for drift (a deterministic health check).")
    p.add_argument("--stale", type=int, default=7,
                   help="days of silence before an agent/thread is flagged (default 7; "
                        "lower it for a fast-paced game, raise it for slow-burn horror)")
    p.add_argument("--no-model", action="store_true",
                   help="skip the optional local tone/compliance read")
    p.add_argument("--dry-run", action="store_true",
                   help="compute and print, but write no report file")
    p.add_argument("--self-test", action="store_true",
                   help="run built-in assertions and exit")
    args = p.parse_args(argv[1:])

    if args.self_test:
        return _self_test()
    if world_tick is None:
        print("world_health: cannot import world_tick (run from the repo). "
              "No audit performed.")
        return 1
    root = _find_root(Path.cwd())
    try:
        return run(root, args)
    except Exception as e:  # never crash a save-point audit
        print(f"world_health error: {e}\n(No audit this time.)")
        return 1


# --------------------------------------------------------------------------- #
# Built-in self-test (python world_health.py --self-test)
# --------------------------------------------------------------------------- #


def _self_test():
    # --- prose parsers ---
    plots = parse_plots(
        "## World plots\n"
        "### harbor-war — The Fight for the Harbor\n"
        "- State: rising\n- Player involvement: unaware\n- Surface: hidden\n"
        "- Opened: Day 2\n"
        "### dud — placeholder check\n- State: forming\n"
        "## Player plot\n- *(none yet)*\n")
    assert len(plots) == 2 and plots[0]["state"] == "rising", plots
    assert plots[0]["opened"] == 2

    threads = parse_threads(
        "## Open\n- [ ] Find the missing courier *(opened Day 1)*\n"
        "- [ ]  *(opened Day N)*\n"
        "## Resolved\n- [x] Met the Prince *(opened Day 1, resolved Day 3)*\n")
    assert len(threads["open"]) == 1, threads["open"]
    assert threads["open"][0]["opened"] == 1
    assert len(threads["resolved"]) == 1

    devs = parse_developments(
        "## [Day 3 — evening] — vance: moves on the council\n"
        "- What happened.\n- Surface: now\n- Drained: no\n"
        "## [Day 1 — dawn] — mara: old news\n- Surface: now\n- Drained: yes\n")
    assert len(devs) == 2
    nows = [d for d in devs if "now" in d["surface"] and not d["drained"]]
    assert len(nows) == 1 and nows[0]["day"] == 3

    assert last_seen_day("vance", "Day 3 vance did a thing\nDay 7 nothing\n"
                                  "Day 5 Vance again") == 5
    assert last_seen_day("ghost", "Day 3 someone else") is None

    # --- end-to-end assess on a built campaign (reuses world_tick discovery) -
    if world_tick is not None:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "CLAUDE.md").write_text("x", encoding="utf-8")
            (root / "Game").mkdir()
            (root / "Game" / "current-scene.md").write_text(
                "**Day 10 — night.** The docks.\n", encoding="utf-8")
            # a frozen agent (clock full, unresolved) + a mover that two contest
            def mkagent(name, block):
                p = root / "Cast" / name
                p.mkdir(parents=True)
                (p / "drives.md").write_text("---\n" + block + "---\n", encoding="utf-8")
            mkagent("stuck",
                    "living: true\nstate: confronting\n"
                    "goal: { pursue: control, target: harbor }\n"
                    "clock: { filled: 6, total: 6 }\nsalience: 3\n")
            mkagent("mara",
                    "living: true\nstate: scheming\n"
                    "goal: { pursue: control, target: harbor }\n"
                    "clock: { filled: 1, total: 6 }\nsalience: 4\n")
            mkagent("lone",
                    "living: true\nstate: brooding\n"
                    'goal: "wander alone"\nclock: { filled: 0, total: 4 }\nsalience: 1\n')
            (root / "Game" / "plots.md").write_text(
                "## World plots\n- *(none yet)*\n", encoding="utf-8")
            (root / "Game" / "threads.md").write_text(
                "## Open\n- [ ] The courier never arrived *(opened Day 2)*\n",
                encoding="utf-8")
            (root / "Game" / "developments.md").write_text(
                "## [Day 9 — dusk] — mara: bribes a dockhand\n"
                "- Surface: now\n- Drained: no\n", encoding="utf-8")
            (root / "Game" / "timeline.md").write_text("", encoding="utf-8")
            # a real control ledger over the contested target, so _ledger_phases
            # (which reads Ledger.phase() — a method, not a dict key) is covered.
            if ledger_mod is not None:
                ledgers = ledger_mod.load_ledgers(root)
                led = ledger_mod.get_or_create(ledgers, "harbor")
                ledger_mod.apply_pressure(led, {"mara": 5.0, "stuck": 2.0}, 9)
                ledger_mod.save_ledgers(root, ledgers)

            rep = assess(root, stale_days=4)
            assert rep["day"] == 10 and rep["n_agents"] == 3
            if ledger_mod is not None:
                assert rep["ledgers"], "ledger phase must be read, not silently empty"
                assert "phase" in format_report(rep, ("skipped", "x"))
            prog = " ".join(m for _, m in rep["progression"])
            assert "stuck" in prog and "clock full" in prog, prog
            # 'lone' has a string goal and no ties → isolated, and never logged
            coll = " ".join(m for _, m in rep["collision"])
            assert "lone" in coll, coll
            # the stale thread (Day 2, now Day 10) must warn
            assert any(s == "warn" for s, _ in rep["threads"]), rep["threads"]
            # the un-drained Surface: now development must warn
            assert any(s == "warn" for s, _ in rep["backlog"]), rep["backlog"]

            text = format_report(rep, ("skipped", "test"))
            assert "World health" in text and "Verdict" in text

            # unseeded world: graceful, no false alarms
            empty = root / "empty"
            (empty / "Game").mkdir(parents=True)
            (empty / "CLAUDE.md").write_text("x", encoding="utf-8")
            (empty / "Game" / "current-scene.md").write_text("Day 1\n", encoding="utf-8")
            erep = assess(empty, stale_days=4)
            assert erep["seeded"] is False
            assert "not yet seeded" in format_report(erep, ("skipped", "x"))

    # --- JSON extraction from a chatty local model (prose-wrapped, multi-object,
    #     string-internal braces) ------------------------------------------------
    assert _extract_json('ok! {"on_tone": true, "drift": "none"} done')["on_tone"] is True
    assert _extract_json('{"a": 1} then {"b": 2}')["a"] == 1  # first parseable wins
    assert _extract_json('{"drift": "a } inside a string"}')["drift"] == "a } inside a string"
    assert _extract_json("no json at all here") is None
    assert _extract_json('not-an-object: [1, 2, 3]') is None  # arrays aren't verdicts

    # --- tone_read's three return states, with a faked local model (no Ollama) --
    if local_client is not None:
        import tempfile
        _orig_gen = local_client.generate
        try:
            with tempfile.TemporaryDirectory() as d3:
                r3 = Path(d3)
                (r3 / "Game").mkdir(parents=True)
                (r3 / "Game" / "current-scene.md").write_text("a scene", encoding="utf-8")
                local_client.generate = lambda *a, **k: (
                    'Sure:\n{"on_tone": false, "drift": "present slipped to past"}\nok')
                assert tone_read(r3, use_model=True)[0] == "drift"
                local_client.generate = lambda *a, **k: '{"on_tone": true, "drift": "none"}'
                assert tone_read(r3, use_model=True)[0] == "ok"
                local_client.generate = lambda *a, **k: "no json whatsoever"
                assert tone_read(r3, use_model=True)[0] == "skipped"
                def _boom(*a, **k):
                    raise RuntimeError("server down")
                local_client.generate = _boom
                assert tone_read(r3, use_model=True)[0] == "skipped"  # degrades, no crash
        finally:
            local_client.generate = _orig_gen
    # --no-model must always skip without touching the model
    assert tone_read(Path("."), use_model=False)[0] == "skipped"

    print("world_health self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
