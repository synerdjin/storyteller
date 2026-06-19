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
try:
    import social  # firewall fingerprinting (goal/success text in actor memory)
except Exception:  # pragma: no cover
    social = None

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
            "surface": _surface_value(_bullet(block, "Surface")),
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
            "surface": _surface_value(_bullet(block, "Surface")),
            # Trust ONLY the explicit `- Drained:` bullet. A loose substring on
            # the headline would mis-read "the drained well" as a drained entry.
            "drained": drained.startswith("y") or drained == "drained",
        })
    return out


def _first_day(s):
    m = _DAY.search(s or "")
    return int(m.group(1)) if m else None


def _surface_value(raw):
    """The Surface *token* (now / soon / hidden), ignoring any trailing prose.

    `_bullet` hands us the whole value after `Surface:`, which may carry a
    parenthetical or prose — e.g. `hidden *(…ripens, not now)*` or
    `now (trigger: the festival)`. A naive substring test for "now" then
    false-flags a `hidden` entry whose prose merely contains the word "now".
    We take only the leading token (up to the first space, `(`, or `*`) and
    lower-case it, so the match is on the Surface *value*, never the prose.
    """
    token = re.split(r"[\s(*]", (raw or "").strip(), maxsplit=1)[0]
    return token.strip().lower()


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
           "director": director_lint(root),
           "firewall": firewall_scan(root, agents), "tone": None}

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
    pending_now = [d for d in devs if d["surface"] == "now" and not d["drained"]]
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


def _drives_body(folder):
    """The GM-only PROSE body of a drives.md (everything after the front-matter
    fence): ## Agenda, ## Reflection notes (director-appended beliefs), etc.
    The per-post propagation guard only sees parsed front-matter; this session-end
    detector reads the prose too, since reflection beliefs are a real leak vector."""
    try:
        lines = (folder / "drives.md").read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    if not lines or lines[0].strip() != "---":
        return "\n".join(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:])
    return ""


def _agent_secret_texts(folder, agent):
    """Every GM-only text the detector fingerprints for one agent: structured
    front-matter (goal/success + relationship notes, via social) PLUS the drives
    prose body PLUS secrets.md — the secret stores CLAUDE.md treats as primary."""
    texts = list(social._forbidden_texts([agent]))
    body = _drives_body(folder)
    if body.strip():
        texts.append(body)
    try:
        sec = (folder / "secrets.md").read_text(encoding="utf-8")
        if sec.strip():
            texts.append(sec)
    except Exception:
        pass
    return texts


def firewall_scan(root, agents):
    """Flag any actor-safe Cast/*/memory.md that echoes a living agent's secret
    text — the firewall-breach this audit catches for campaigns that ran an
    affected pre-fix world tick. Deterministic; reuses social's fingerprint.

    Unlike the per-post propagation guard (front-matter fields only), this
    session-end pass also fingerprints the drives.md prose body and secrets.md,
    so a leaked reflection belief or secret agenda is caught, not just goal text.

    Returns a list of (severity, message). A `note` (not a clean pass) is returned
    when the scan could not run (no `social` module), so a broken import never
    reads as a green checkmark."""
    if social is None:
        return [("note", "firewall scan SKIPPED — could not import the `social` "
                 "module, so actor memory was not fingerprinted this run. Re-run "
                 "from the repo root to enable it.")]
    if not agents:
        return []
    root = Path(root)
    # Per-agent secret text, so a hit can name *whose* secret leaked.
    per_agent = {}
    for a in agents:
        texts = _agent_secret_texts(root / "Cast" / a.name, a)
        if any(t.strip() for t in texts):
            per_agent[a.name] = texts
    if not per_agent:
        return []
    findings = []
    for mem in sorted((root / "Cast").glob("*/memory.md")):
        if mem.parent.name.startswith("_"):
            continue
        try:
            text = mem.read_text(encoding="utf-8")
        except Exception:
            continue
        owner = mem.parent.name
        for src_name, forbidden in per_agent.items():
            if social._shares_ngram(text, forbidden):
                findings.append((
                    "warn",
                    f"Cast/{owner}/memory.md echoes {src_name}'s secret text "
                    f"(goal / relationship note / agenda / reflection / secrets) "
                    f"— a firewall leak. Scrub the offending line(s)."))
    return findings


# --------------------------------------------------------------------------- #
# Director discipline lint — a heuristic nudge against pre-narration.
#
# Directors stage *conditions and off-screen consequences*; they must never
# resolve, pre-narrate, or author a scene the Player will play — and never put
# words or actions in the Player character's mouth. This lint flags staged
# `developments.md` entries and the director/propagation-written observation
# lines in `Cast/*/memory.md` that look like pre-narration. It is deliberately
# heuristic (warnings only; the GM adjudicates), the same nudge-not-gate stance
# as the rest of world_health. It scans only director-authored regions: all of
# developments.md, and the "What I've learned about others" section of a
# memory.md — never the character's own `## Log` of already-played history.
# --------------------------------------------------------------------------- #

_OBS_HEADING = "## What I've learned about others"
# A named set-piece a development shouldn't be narrating before it's played.
_SCENE_RE = re.compile(
    r"\b(?:the|a|an)\s+[\w'’-]+(?:\s+[\w'’-]+){0,2}?\s+"
    r"(scene|dream|flashback|interlude|montage)\b", re.IGNORECASE)
# Future-tense, player-facing narration (gated on the PC being in the line).
_FUTURE_RE = re.compile(r"\b(will|won't|about to|going to|would soon|shall)\b",
                        re.IGNORECASE)
# Verbs that, with the PC as subject, mean the director authored the Player.
_PC_VERBS = (
    "said", "says", "whispered", "whispers", "murmured", "murmurs", "replied",
    "replies", "answered", "answers", "asked", "asks", "decided", "decides",
    "drew", "draws", "reached", "reaches", "felt", "feels", "thought", "thinks",
    "drifted", "drifts", "drifting", "kissed", "kisses", "walked", "walks",
    "stepped", "steps", "turned", "turns", "nodded", "nods", "smiled", "smiles",
    "agreed", "agrees", "refused", "refuses", "chose", "chooses", "drank",
    "drinks", "struck", "strikes", "ran", "runs", "slept", "sleeps", "wept",
    "weeps", "laughed", "laughs", "fell", "falls", "moved", "moves", "grabbed",
    "grabs", "pulled", "pulls", "leaned", "leans", "stood", "stands", "sat",
    "sits", "lay", "kills", "killed", "fled", "flees",
)


def _pc_action_re(pc):
    verbs = "|".join(_PC_VERBS)
    # PC name, then within ~3 words a verb it governs (subject = PC). Ordering
    # (name before verb) keeps "moves on Daniel" — PC as *object* — from matching.
    return re.compile(
        r"\b" + re.escape(pc) + r"\b(?:\s+\w+){0,3}?\s+(?:" + verbs + r")\b",
        re.IGNORECASE)


def _pc_name(root):
    """Best-effort Player-character first name from Character/sheet.md (heuristic).

    Returns None when not confidently found — the PC-authoring/future checks then
    skip rather than guess and mis-flag. Honest about being a nudge.
    """
    text = _read(root, "Character/sheet.md")
    name = None
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+?)\s+[—–-]\s*SHEET", line.strip(), re.IGNORECASE)
        if m:
            name = m.group(1)
            break
    if not name:
        m = re.search(r"^\s*[-*]?\s*\*{0,2}Name\*{0,2}\s*:\s*(.+)$",
                      text, re.IGNORECASE | re.MULTILINE)
        if m:
            name = m.group(1)
    if not name:
        return None
    name = re.sub(r"[*_`]", "", name).strip()
    name = re.split(r"[,—–(]", name)[0].strip()  # drop trailing concept/pronouns
    if not name or name.startswith("<") or _PLACEHOLDER.match(name):
        return None
    first = name.split()[0]
    return first if first and first[0].isalpha() else None


def _observation_lines(text):
    """Lines under '## What I've learned about others' (director/propagation-
    written), excluding the character's own '## Log' of played history."""
    out, grab = [], False
    for line in text.splitlines():
        s = line.strip()
        if s == _OBS_HEADING:
            grab = True
            continue
        if grab and s.startswith("## "):
            grab = False
        if grab and s:
            out.append(line)
    return out


def _development_entry_lines(text):
    """Lines inside dated `## [Day N …]` entries (heading + body), skipping the
    file's instructional preamble and the Surface-timing legend — only real
    staged content is linted, not the template's own scaffolding."""
    lines = _strip_fences(text).splitlines()
    heads = [i for i, l in enumerate(lines)
             if re.match(r"^##\s+\[Day\s+\d+", l, re.IGNORECASE)]
    out = []
    for k, start in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        out.extend(lines[start:end])
    return out


def director_lint(root, pc_name=None):
    """Flag staged entries that look like pre-narration. Warnings only.

    Three heuristics, in priority order per line:
      (c) the Player character is the subject of an action verb — directors
          never author the PC;
      (b) future-tense, player-facing narration (the PC is named in the line);
      (a) a named scene/dream/flashback that doesn't appear in timeline.md yet
          (likely un-played, and being narrated as if it had happened).
    """
    root = Path(root)
    if pc_name is None:
        pc_name = _pc_name(root)
    timeline = _read(root, "Game/timeline.md").lower()
    pc_re = _pc_action_re(pc_name) if pc_name else None
    pc_low = pc_name.lower() if pc_name else None
    findings = []

    def check(rel, line):
        s = line.strip()
        if not s or s.startswith(">") or _PLACEHOLDER.match(s):
            return
        if pc_re and pc_re.search(s):
            findings.append((
                "warn", f"{rel}: stages an action for the Player character "
                        f"(`{pc_name}`) — stage the world *around* the PC, never "
                        f"author the PC: \"{s[:90]}\""))
        elif pc_low and pc_low in s.lower() and _FUTURE_RE.search(s):
            findings.append((
                "warn", f"{rel}: pre-narrates a Player scene in the future tense — "
                        f"stage intent/positioning, not an outcome the Player "
                        f"hasn't played: \"{s[:90]}\""))
        else:
            m = _SCENE_RE.search(s)
            if m and m.group(0).lower() not in timeline:
                findings.append((
                    "warn", f"{rel}: names a scene not in timeline.md (un-played?) "
                            f"— don't pre-narrate it: \"{m.group(0)}\""))

    for line in _development_entry_lines(_read(root, "Game/developments.md")):
        check("developments.md", line)
    for mem in sorted((root / "Cast").glob("*/memory.md")):
        if mem.parent.name.startswith("_"):
            continue
        try:
            text = mem.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in _observation_lines(text):
            check(f"Cast/{mem.parent.name}/memory.md", line)
    return findings


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
    warns = sum(1 for grp in ("progression", "collision", "threads", "backlog",
                              "director", "firewall")
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
    _section(out, "Director discipline (no pre-narration / no authoring the PC)",
             rep.get("director") or [])
    _section(out, "Firewall (no secret goal/success text in actor memory)",
             rep.get("firewall") or [])
    out.append("## Tone & compliance (optional local read)")
    mark = {"ok": "✓", "drift": "⚠", "skipped": "·"}.get(tone[0], "·")
    out.append(f"- {mark} {tone[0]}: {tone[1]}")
    out.append("")
    if rep.get("firewall"):
        out.append("**Verdict (firewall):** secret goal/success text was found in "
                   "an actor-safe `memory.md`. This is a spoiler leak, not mere "
                   "bookkeeping — scrub the flagged line(s) before voicing those "
                   "NPCs via `npc-actor`. (Fixed at the source in the engine; this "
                   "catches save data written by an affected earlier tick.)")
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
    nows = [d for d in devs if d["surface"] == "now" and not d["drained"]]
    assert len(nows) == 1 and nows[0]["day"] == 3

    # --- Surface-value parse (regression): the token, not a substring of prose --
    assert _surface_value("now") == "now"
    assert _surface_value("now (trigger: the festival)") == "now"      # trailing note
    assert _surface_value("hidden *(…ripens toward rung two, not now)*") == "hidden"
    assert _surface_value("hidden (nothing perceptible now)") == "hidden"
    assert _surface_value("soon (… happens now-ish)") == "soon"
    assert _surface_value(None) == "" and _surface_value("") == ""
    # end-to-end: a `hidden` entry whose prose contains "now" must NOT be counted.
    bug = parse_developments(
        "## [Day 5 — dusk] — sabine: the plan ripens\n"
        "- Surface: hidden *(ripens toward rung two, not now)*\n- Drained: no\n"
        "## [Day 5 — dusk] — mara: presses now\n"
        "- Surface: now (trigger: the vote)\n- Drained: no\n"
        "## [Day 5 — dusk] — lucien: bides his time\n"
        "- Surface: soon (… happens now-ish)\n- Drained: no\n")
    real_nows = [d for d in bug if d["surface"] == "now" and not d["drained"]]
    assert len(real_nows) == 1, [d["surface"] for d in bug]   # was 3 before the fix
    assert real_nows[0]["headline"].endswith("presses now")

    # --- director discipline lint (no pre-narration / no authoring the PC) ----
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Game").mkdir(parents=True)
        (root / "Game" / "timeline.md").write_text(
            "## Timeline\n- [Day 4] Met Diana at the docks.\n", encoding="utf-8")
        (root / "Game" / "developments.md").write_text(
            "## [Day 5 — dusk] — vance: presses toward the council seat\n"
            "- Stages intent; clock now 4/6.\n"
            "## [Day 5 — dusk] — diana: pre-narration creeps in\n"
            "- Daniel drew his blade and agreed to the pact.\n"
            "- During the going-home scene, Daniel will drift toward sleep.\n"
            "- Sets up a candlelight dream offstage.\n",
            encoding="utf-8")
        fnd = director_lint(root, pc_name="Daniel")
        msgs = " || ".join(m for _, m in fnd)
        assert all(s == "warn" for s, _ in fnd), fnd          # warnings only
        # (c) the PC as the subject of an action verb is flagged
        assert any("Player character" in m and "drew his blade" in m
                   for _, m in fnd), msgs
        # (b) a future-tense player-facing scene is flagged
        assert any("future tense" in m for _, m in fnd), msgs
        # (a) a named scene not in timeline.md is flagged
        assert any("not in timeline" in m and "candlelight dream" in m
                   for _, m in fnd), msgs
        # clean NPC staging (intent / off-screen) is NOT flagged
        assert not any("council seat" in m or "clock now 4/6" in m
                       for _, m in fnd), msgs
        # with no PC name, the PC-specific checks skip gracefully (still does (a))
        nopc = director_lint(root, pc_name=None)
        assert not any("Player character" in m for _, m in nopc), nopc
        assert any("candlelight dream" in m for _, m in nopc), nopc

    # observation-section scoping: a played interaction in the NPC's own ## Log
    # must NOT be linted (only director-written observations are), even if it
    # names the PC as an actor.
    obs = _observation_lines(
        "# kira — memory\n\n## Log\n- [Day 3] Daniel drew his blade in my parlor.\n"
        "\n## What I've learned about others\n"
        "- *[Day 4]* — about `vance`: pressed toward the seat.\n")
    assert len(obs) == 1 and "vance" in obs[0] and "Daniel drew" not in " ".join(obs)

    # PC-name heuristic reads a `# <Name> — SHEET` heading, skips the template.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Character").mkdir(parents=True)
        (root / "Character" / "sheet.md").write_text(
            "# Daniel Vass — SHEET (GM ONLY)\n\n## At a glance\n", encoding="utf-8")
        assert _pc_name(root) == "Daniel"
        (root / "Character" / "sheet.md").write_text(
            "# <Name> — SHEET (GM ONLY)\n", encoding="utf-8")
        assert _pc_name(root) is None    # template placeholder → no guess

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
            # clean save data: the firewall scan must not false-alarm here
            assert not rep["firewall"], rep["firewall"]

            # --- firewall scan: a memory.md that echoes a secret goal must warn ---
            if social is not None:
                fw = root / "fw"
                (fw / "Game").mkdir(parents=True)
                (fw / "CLAUDE.md").write_text("x", encoding="utf-8")
                (fw / "Game" / "current-scene.md").write_text("Day 5\n", encoding="utf-8")
                secret = ("keeps Daniel-the-bridge hers without ever revealing "
                          "the cult to the court")
                (fw / "Cast" / "sabine").mkdir(parents=True)
                (fw / "Cast" / "sabine" / "drives.md").write_text(
                    "---\nliving: true\nstate: moving\n"
                    "goal: { pursue: control, target: diana, "
                    f"success: \"{secret}\" }}\nsalience: 4\n---\n", encoding="utf-8")
                # kira's actor-safe memory carries the leaked goal text (the bug)
                (fw / "Cast" / "kira").mkdir(parents=True)
                (fw / "Cast" / "kira" / "memory.md").write_text(
                    "# kira — memory\n\n## What I've learned about others\n"
                    f"- *[Day 1]* — about `sabine`: heard word that {secret}\n",
                    encoding="utf-8")
                (fw / "Cast" / "kira" / "drives.md").write_text(
                    "---\nliving: true\nstate: scheming\nsalience: 2\n---\n",
                    encoding="utf-8")
                frep = assess(fw, stale_days=4)
                assert any(s == "warn" for s, _ in frep["firewall"]), frep["firewall"]
                assert any("kira" in m for _, m in frep["firewall"])
                assert "firewall" in format_report(frep, ("skipped", "x")).lower()

                # the detector also catches a secrets.md leak (not just goal text):
                # a distinctive secrets.md sentence echoed in another NPC's memory.
                secret2 = "the relic beneath the chapel is a forgery she planted"
                (fw / "Cast" / "sabine" / "secrets.md").write_text(
                    f"# sabine — secrets (GM ONLY)\n\n{secret2}.\n", encoding="utf-8")
                (fw / "Cast" / "lucien").mkdir(parents=True)
                (fw / "Cast" / "lucien" / "drives.md").write_text(
                    "---\nliving: true\nstate: brooding\nsalience: 1\n---\n",
                    encoding="utf-8")
                (fw / "Cast" / "lucien" / "memory.md").write_text(
                    "# lucien — memory\n\n## What I've learned about others\n"
                    f"- *[Day 2]* — about `sabine`: I suspect {secret2}.\n",
                    encoding="utf-8")
                frep2 = assess(fw, stale_days=4)
                assert any("lucien" in m and s == "warn"
                           for s, m in frep2["firewall"]), frep2["firewall"]

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
