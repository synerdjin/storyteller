#!/usr/bin/env python3
"""The living-world metronome for the Storyteller Game Master.

This is to the living world what dice.py is to a roll: the *deterministic,
auditable* layer. It does not invent anything. It reads the structured state of
every "living" NPC and faction, advances their progress clocks by fixed rules,
fires finite-state-machine transitions whose guards are met, and then SELECTS
which few of them are pressing enough to deliberate this tick. The narrative —
*what* a flagged character actually does off-screen — is decided afterward by
the `world-director` subagent, never here.

Why a script and not just the GM? The same reason rolls go through dice.py:
so the GM cannot quietly advance only the convenient threats. The clock math is
binding and shown.

Usage:
    python world_tick.py                 # a normal beat: 1 unit of time passes
    python world_tick.py --elapsed 3     # a time-skip: 3 units pass
    python world_tick.py --dawdle        # the Player stalled; 'dawdle' clocks tick
    python world_tick.py --fail          # a roll failed forward; 'on_fail' clocks tick
    python world_tick.py --max 3         # cap how many agents are queued (default 3)
    python world_tick.py --dry-run       # compute & print, but DON'T write any files
    python world_tick.py --self-test     # run built-in assertions and exit

What it reads (any file with a `living: true` block):
    Cast/<name>/drives.md     — one YAML front-matter block per living NPC
    Game/world-state.md       — a front-matter block (world clocks) and/or
                                fenced ```yaml blocks under `## ` headings (factions)

What it writes:
    - the advanced `state:`/`clock:` values, surgically, back into those same files
      (comments and prose untouched)
    - Game/.world-tick-queue.md — the hand-off for the world-director subagent

Block shape (the controlled YAML subset this parses):
    living: true
    state: scheming
    goal: "Seize the harbor council seat before the festival"
    clock: { filled: 2, total: 6 }
    advances_when: dawdle        # always | dawdle | on_fail | manual
    salience: 3                  # 1-5, gates selection priority
    states:
      scheming:    { to: moving,      when: "clock>=3" }
      moving:      { to: confronting, when: "clock>=5" }
      confronting: { to: regrouping,  when: "always" }
"""

import argparse
import re
import sys
from pathlib import Path

# Sibling module: the deterministic control ledger. Optional — if it can't be
# imported (run from an odd cwd), the tick still works, just without ledgers.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import ledger as ledger_mod
except Exception:  # pragma: no cover
    ledger_mod = None

# --------------------------------------------------------------------------- #
# A tiny, dependency-free parser for the controlled YAML subset above.
# It is intentionally NOT a general YAML parser — it understands exactly the
# block shape this tool documents, and nothing more.
# --------------------------------------------------------------------------- #

_INT_RE = re.compile(r"^-?\d+$")
_GUARD_RE = re.compile(r"^clock\s*(>=|<=|==|!=|>|<)\s*(\d+)$")


def _strip_comment(line):
    """Drop a trailing `# comment`, but not a `#` inside quotes."""
    out, in_q = [], None
    for ch in line:
        if in_q:
            out.append(ch)
            if ch == in_q:
                in_q = None
        elif ch in "\"'":
            in_q = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out)


def _split_top(s):
    """Split on commas that are not inside quotes or braces."""
    parts, depth, in_q, cur = [], 0, None, ""
    for ch in s:
        if in_q:
            cur += ch
            if ch == in_q:
                in_q = None
        elif ch in "\"'":
            in_q = ch
            cur += ch
        elif ch == "{":
            depth += 1
            cur += ch
        elif ch == "}":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def _parse_scalar(s):
    s = s.strip()
    if s == "":
        return None
    if s.startswith("{") and s.endswith("}"):
        return _parse_inline_map(s)
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if _INT_RE.match(s):
        return int(s)
    return s


def _parse_inline_map(s):
    inner = s.strip()[1:-1].strip()
    d = {}
    if not inner:
        return d
    for part in _split_top(inner):
        k, _, v = part.partition(":")
        d[k.strip()] = _parse_scalar(v)
    return d


def parse_block(text):
    """Parse a block of `key: value` lines (with one level of `key:`-nesting)."""
    entries = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip(" "))
        entries.append((indent, line.strip()))

    d, i, n = {}, 0, len(entries)
    while i < n:
        indent, content = entries[i]
        if indent != 0:
            i += 1
            continue
        key, _, rest = content.partition(":")
        key, rest = key.strip(), rest.strip()
        if rest == "":
            children, j = {}, i + 1
            while j < n and entries[j][0] > 0:
                ck, _, cv = entries[j][1].partition(":")
                children[ck.strip()] = _parse_scalar(cv.strip())
                j += 1
            d[key] = children
            i = j
        else:
            d[key] = _parse_scalar(rest)
            i += 1
    return d


# --------------------------------------------------------------------------- #
# Locating living blocks in files, tracking each block's line span so we can
# write changes back surgically (touching only the state/clock lines).
# --------------------------------------------------------------------------- #


class Agent:
    """One living NPC or faction: its parsed fields and where they live on disk."""

    def __init__(self, name, fields, path, span):
        self.name = name
        self.fields = fields
        self.path = path          # Path to the file
        self.span = span          # (start, end) line indices of the block body
        # tick results, filled in by tick():
        self.advanced = 0
        self.transitioned = False
        self.became_full = False
        self.old_state = fields.get("state")
        self.old_filled = _clock(fields).get("filled", 0)


def _clock(fields):
    c = fields.get("clock")
    return c if isinstance(c, dict) else {}


def _frontmatter_block(lines):
    """If `lines` opens with a --- front-matter block, return (start, end)."""
    if not lines or lines[0].strip() != "---":
        return None
    for k in range(1, len(lines)):
        if lines[k].strip() == "---":
            return (1, k)  # body is lines[1:k]
    return None


def _fenced_blocks(lines):
    """Yield (heading, start, end) for each ```yaml ... ``` fence, with the
    nearest preceding `#`-heading as its name."""
    blocks, heading, i, n = [], None, 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s.startswith("#"):
            heading = s.lstrip("#").strip()
        if re.match(r"^```+\s*ya?ml\s*$", s):
            start = i + 1
            j = start
            while j < n and not lines[j].strip().startswith("```"):
                j += 1
            blocks.append((heading, start, j))
            i = j + 1
            continue
        i += 1
    return blocks


def discover_agents(root):
    """Find every living NPC (Cast/*/drives.md) and faction/world block."""
    agents = []

    for drives in sorted(root.glob("Cast/*/drives.md")):
        if drives.parent.name.startswith("_"):
            continue  # skip Cast/_template/ and any other skeleton folder
        lines = drives.read_text(encoding="utf-8").splitlines()
        span = _frontmatter_block(lines)
        if not span:
            continue
        fields = parse_block("\n".join(lines[span[0]:span[1]]))
        if fields.get("living") is True:
            agents.append(Agent(drives.parent.name, fields, drives, span))

    world = root / "Game" / "world-state.md"
    if world.exists():
        lines = world.read_text(encoding="utf-8").splitlines()
        fm = _frontmatter_block(lines)
        if fm:
            fields = parse_block("\n".join(lines[fm[0]:fm[1]]))
            if fields.get("living") is True:
                agents.append(Agent(fields.get("name", "world"), fields, world, fm))
        for heading, start, end in _fenced_blocks(lines):
            fields = parse_block("\n".join(lines[start:end]))
            if fields.get("living") is True:
                agents.append(Agent(heading or "faction", fields, world, (start, end)))

    return agents


# --------------------------------------------------------------------------- #
# The tick rules — deterministic, no randomness, no narrative.
# --------------------------------------------------------------------------- #


def eval_guard(guard, filled, total):
    """Evaluate an FSM transition guard against the current clock."""
    if guard is None:
        return False
    g = str(guard).strip()
    if g == "always":
        return True
    if g == "clock_full":
        return filled >= total
    m = _GUARD_RE.match(g)
    if not m:
        return False  # unknown guard never fires — fail safe, never crash play
    op, num = m.group(1), int(m.group(2))
    return {
        ">=": filled >= num, "<=": filled <= num, "==": filled == num,
        "!=": filled != num, ">": filled > num, "<": filled < num,
    }[op]


def advance_amount(advances_when, elapsed, dawdle, fail):
    aw = (advances_when or "manual")
    if aw == "always":
        return elapsed
    if aw == "dawdle":
        return 1 if dawdle else 0
    if aw in ("on_fail", "fail"):
        return 1 if fail else 0
    return 0  # manual: only the director moves it


def tick(agent, elapsed, dawdle, fail):
    """Advance one agent's clock and fire at most one FSM transition."""
    clock = _clock(agent.fields)
    filled = int(clock.get("filled", 0))
    total = int(clock.get("total", 0))
    state = agent.fields.get("state")
    states = agent.fields.get("states") or {}

    adv = advance_amount(agent.fields.get("advances_when"), elapsed, dawdle, fail)
    new_filled = min(total, filled + adv) if total else filled + adv
    agent.advanced = new_filled - filled
    agent.became_full = total > 0 and new_filled >= total and filled < total

    transition = states.get(state) if isinstance(states, dict) else None
    if isinstance(transition, dict):
        guard, target = transition.get("when"), transition.get("to")
        if target and eval_guard(guard, new_filled, total):
            state = target
            agent.transitioned = True

    # record results back into fields (write_back persists these to disk)
    clock["filled"] = new_filled
    agent.fields["clock"] = clock
    agent.fields["state"] = state


def priority(agent):
    """Deterministic selection score: who most deserves the director's attention."""
    sal = agent.fields.get("salience")
    sal = sal if isinstance(sal, int) else 1
    return (
        sal
        + (3 if agent.transitioned else 0)
        + (2 if agent.became_full else 0)
        + (1 if agent.advanced else 0)
    )


def changed(agent):
    return bool(agent.advanced) or agent.transitioned


# --------------------------------------------------------------------------- #
# Interaction detection — the deterministic half of emergence.
#
# This is to plots what the clock math is to a single agent: it only *detects*
# structural contention in the graph (two agents reaching for the same thing, a
# rivalry heating up, a goal aimed at the Player). It never decides who wins —
# that stays in the model tier (world_scribe / world-director), the same way the
# fiction of a clock advancing is decided by the director, not by this script.
# --------------------------------------------------------------------------- #

_ALLY_TIES = {"ally", "kin", "lover", "patron", "friend", "mentor"}
_HOSTILE_TIES = {"rival", "grudge", "enemy", "nemesis"}


def _goal_field(agent, key):
    g = agent.fields.get("goal")
    return g.get(key) if isinstance(g, dict) else None


def goal_target(agent):
    """The entity id this agent is reaching for, or None (legacy string goals)."""
    t = _goal_field(agent, "target")
    return str(t).strip() if t not in (None, "") else None


def _rels(agent):
    r = agent.fields.get("relationships")
    return r if isinstance(r, dict) else {}


def _weight(edge):
    w = edge.get("weight") if isinstance(edge, dict) else None
    return w if isinstance(w, int) else 0


def _group(agent):
    g = agent.fields.get("group")
    return str(g).strip() if g not in (None, "") else None


def _allied(a, b):
    """True if a and b share a positive bond, or belong to the same group."""
    ga, gb = _group(a), _group(b)
    if ga is not None and ga == gb:
        return True
    for x, y in ((a, b), (b, a)):
        e = _rels(x).get(y.name)
        if isinstance(e, dict) and e.get("tie") in _ALLY_TIES and _weight(e) > 0:
            return True
    return False


def _hostile_edge(a, b):
    """Return (tie, weight) for a hostile edge between a and b, else None."""
    for x, y in ((a, b), (b, a)):
        e = _rels(x).get(y.name)
        if isinstance(e, dict):
            tie, w = e.get("tie"), _weight(e)
            if tie in _HOSTILE_TIES or w <= -3:
                return (tie or "hostile", w)
    return None


def _resource_total(agent):
    r = agent.fields.get("resources")
    if not isinstance(r, dict):
        return 0, None
    nums = {k: v for k, v in r.items() if isinstance(v, int)}
    if not nums:
        return 0, None
    return sum(nums.values()), max(nums, key=nums.get)


def _advantage_hint(a, b):
    """A *hint* at who is better positioned — never a verdict (resolve honestly)."""
    ta, topa = _resource_total(a)
    tb, topb = _resource_total(b)
    if ta == tb:
        return f"even on resources ({a.name} {ta} vs {b.name} {tb}) — resolve honestly"
    lead, lt, lp = (a, ta, topa) if ta > tb else (b, tb, topb)
    edge = f" ({lp})" if lp else ""
    return (f"{lead.name} better-resourced{edge}: {a.name} {ta} vs {b.name} {tb}"
            f" — a hint, not a verdict")


def _sal(agent):
    s = agent.fields.get("salience")
    return s if isinstance(s, int) else 1


def _mood_total(agent):
    m = agent.fields.get("mood")
    return sum(v for v in m.values() if isinstance(v, int)) if isinstance(m, dict) else 0


def _pressure(agent):
    """How hard an agent can press a contest: resources + mood + salience.

    Deterministic and auditable — the ledger uses this to decide who *gains*
    control, never a model. (Mirrors `the_city`'s numbers-not-LLM discipline.)
    """
    res, _ = _resource_total(agent)
    return float(res + _mood_total(agent) + _sal(agent))


def _current_day(root):
    p = Path(root) / "Game" / "current-scene.md"
    if p.exists():
        m = re.search(r"Day\s+(\d+)", p.read_text(encoding="utf-8"))
        if m:
            return int(m.group(1))
    return None


class Interaction:
    """A detected, unresolved point of contention between agents (or vs. player)."""

    def __init__(self, kind, a, b, over, why, hint):
        self.kind = kind      # contested-goal | rivalry | player-pressure
        self.a = a
        self.b = b            # None for player-pressure
        self.over = over      # the contested entity id (or "player")
        self.why = why
        self.hint = hint
        self.standing = None  # filled by the ledger pass (contested-goal only)
        self.phase = None

    def key(self):
        names = tuple(sorted([self.a.name, self.b.name if self.b else "player"]))
        return (self.kind, names, self.over)

    def heat(self):
        """How hot this tick: how many parties actually moved, then salience."""
        moved = changed(self.a) + (changed(self.b) if self.b else 0)
        sal = _sal(self.a) + (_sal(self.b) if self.b else 0)
        return (moved, sal)


def detect_interactions(agents, max_n=0):
    """Find structural collisions among the living agents this tick."""
    living = list(agents)
    found = {}

    # Rule (a): two non-allied agents reaching for the SAME target, and at least
    # one of them moved this tick (so the queue tracks motion, not standing facts).
    by_target = {}
    for a in living:
        t = goal_target(a)
        if t and t != "player":
            by_target.setdefault(t, []).append(a)
    for t, group in by_target.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if _allied(a, b) or not (changed(a) or changed(b)):
                    continue
                why = f"both reach for `{t}`"
                he = _hostile_edge(a, b)
                if he:
                    why += f"; they are {he[0]} ({he[1]})"
                it = Interaction("contested-goal", a, b, t, why, _advantage_hint(a, b))
                found[it.key()] = it

    # Rule (b): a hostile edge between two living agents, BOTH advancing this tick.
    # Skip any pair already captured by a contested-goal above — that entry is
    # richer (it names what they fight over), so we don't double-flag the pair.
    contesting_pairs = {tuple(sorted((it.a.name, it.b.name)))
                        for it in found.values() if it.b}
    for i in range(len(living)):
        for j in range(i + 1, len(living)):
            a, b = living[i], living[j]
            if not (changed(a) and changed(b)):
                continue
            if tuple(sorted((a.name, b.name))) in contesting_pairs:
                continue
            he = _hostile_edge(a, b)
            if not he:
                continue
            it = Interaction(
                "rivalry", a, b, None,
                f"{a.name} and {b.name} are {he[0]} ({he[1]}) and both moved this tick",
                _advantage_hint(a, b))
            found.setdefault(it.key(), it)

    # Rule (c): an agent whose goal targets the Player, who moved this tick.
    for a in living:
        if goal_target(a) == "player" and changed(a):
            it = Interaction(
                "player-pressure", a, None, "player",
                f"{a.name}'s goal reaches for the Player, and they moved this tick", None)
            found.setdefault(it.key(), it)

    out = sorted(found.values(),
                 key=lambda it: (-it.heat()[0], -it.heat()[1], it.a.name,
                                 it.b.name if it.b else ""))
    return out[:max_n] if max_n else out


def apply_ledgers(root, agents, interactions, dry_run):
    """Advance the deterministic control ledger for each contested entity.

    For every entity two or more agents are contesting this tick, move control
    points toward the higher-pressure claimant by `ledger.apply_pressure` (fixed
    rule, no model, no randomness — the metronome stays deterministic), then
    annotate the matching interactions with the new standing/phase so the queue
    (and the scribe) can narrate what the number means. Persists `ledgers.md`
    unless this is a dry run. A no-op when the ledger module is unavailable.
    """
    if ledger_mod is None:
        return
    contested = {}      # entity -> {agent_name: pressure}
    by_name = {a.name: a for a in agents}
    for it in interactions:
        if it.kind == "contested-goal" and it.over:
            contested.setdefault(it.over, {})
            for p in (it.a, it.b):
                if p is not None:
                    contested[it.over][p.name] = _pressure(p)
    # also fold in any third-party claimants reaching for the same entity
    for entity in list(contested):
        for a in agents:
            if goal_target(a) == entity:
                contested[entity].setdefault(a.name, _pressure(a))
    if not contested:
        return

    ledgers = ledger_mod.load_ledgers(root)
    day = _current_day(root)
    results = {}
    for entity, pressures in contested.items():
        led = ledger_mod.get_or_create(ledgers, entity)
        results[entity] = ledger_mod.apply_pressure(led, pressures, day)
    for it in interactions:
        if it.kind == "contested-goal" and it.over in results:
            r = results[it.over]
            it.standing = r["standing"]
            it.phase = r["phase"]
    if not dry_run:
        ledger_mod.save_ledgers(root, ledgers)


# --------------------------------------------------------------------------- #
# Surgical write-back: rewrite ONLY the state: and clock: lines within a
# block's span, preserving comments, prose, and every other line.
# --------------------------------------------------------------------------- #

_STATE_LINE = re.compile(r"^(\s*state:\s*)(\S+)(.*)$")
_FILLED = re.compile(r"(filled:\s*)(-?\d+)")


def write_back(agents):
    """Persist advanced state/clock for changed agents, grouped by file."""
    by_file = {}
    for a in agents:
        if changed(a):
            by_file.setdefault(a.path, []).append(a)

    for path, file_agents in by_file.items():
        lines = path.read_text(encoding="utf-8").splitlines()
        for a in file_agents:
            start, end = a.span
            new_state = a.fields.get("state")
            new_filled = _clock(a.fields).get("filled")
            for idx in range(start, min(end, len(lines))):
                line = lines[idx]
                if _STATE_LINE.match(line) and new_state is not None:
                    lines[idx] = _STATE_LINE.sub(rf"\g<1>{new_state}\g<3>", line)
                elif "clock:" in line and "filled:" in line and new_filled is not None:
                    lines[idx] = _FILLED.sub(rf"\g<1>{new_filled}", line)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Output: a human-readable summary, and the queue file for the director.
# --------------------------------------------------------------------------- #


def summarize(agents, selected, interactions, reflectors, args):
    out = []
    flags = []
    if args.elapsed != 1:
        flags.append(f"elapsed={args.elapsed}")
    if args.dawdle:
        flags.append("dawdle")
    if args.fail:
        flags.append("fail")
    out.append(f"World tick ({', '.join(flags) or 'one beat'}): "
               f"{len(agents)} living, {sum(changed(a) for a in agents)} moved, "
               f"{len(selected)} queued, {len(interactions)} interaction(s), "
               f"{len(reflectors)} reflecting.")
    for it in interactions:
        who = f"{it.a.name} vs {it.b.name}" if it.b else f"{it.a.name} → player"
        over = f" over {it.over}" if it.over and it.over != "player" else ""
        out.append(f"  ! {it.kind}: {who}{over}")
    if not agents:
        out.append("  (No living NPCs or factions. The world is static - "
                   "promote someone with a drives.md to bring it to life.)")
    for a in agents:
        if not changed(a):
            continue
        c = _clock(a.fields)
        bits = []
        if a.advanced:
            bits.append(f"clock {a.old_filled}->{c.get('filled')}/{c.get('total')}")
        if a.transitioned:
            bits.append(f"state {a.old_state} -> {a.fields.get('state')}")
        star = " *QUEUED*" if a in selected else ""
        out.append(f"  - {a.name}: {', '.join(bits)}{star}")
    return "\n".join(out)


def _fmt_goal(agent):
    """Render a goal for the queue: targeted map → 'pursue `target` (success)'."""
    g = agent.fields.get("goal")
    if isinstance(g, dict):
        bits = " ".join(str(g[k]) for k in ("pursue", "target") if g.get(k))
        succ = g.get("success")
        return f"{bits}" + (f" ({succ})" if succ else "")
    return str(g) if g is not None else "(unset)"


def write_queue(root, selected, interactions, reflectors, args, dry_run):
    path = root / "Game" / ".world-tick-queue.md"
    lines = [
        "# World-tick queue (for the world-director subagent)",
        "",
        "> Generated by `Tools/world_tick.py`. Ephemeral hand-off — the director",
        "> (or the local `world_scribe.py`) reads this, decides what each agent",
        "> *does* off-screen and how flagged collisions resolve, then writes the",
        "> narrative consequences. Safe to delete after deliberation.",
        "",
        f"Tick: elapsed={args.elapsed}, dawdle={args.dawdle}, fail={args.fail}.",
        "",
    ]
    if not selected and not interactions and not reflectors:
        lines.append("**Queue empty.** Nothing pressing advanced this tick — "
                     "no deliberation needed.")
    for a in selected:
        c = _clock(a.fields)
        why = []
        if a.transitioned:
            why.append(f"entered **{a.fields.get('state')}** (was {a.old_state})")
        if a.became_full:
            why.append("**clock filled**")
        elif a.advanced:
            why.append(f"clock advanced to {c.get('filled')}/{c.get('total')}")
        lines += [
            f"## {a.name}",
            f"- Source: `{a.path.as_posix()}`",
            f"- State: `{a.fields.get('state')}`  |  "
            f"Clock: {c.get('filled')}/{c.get('total')}  |  "
            f"Salience: {a.fields.get('salience')}",
            f"- Goal: {_fmt_goal(a)}",
            f"- Why flagged: {', '.join(why) or 'changed'}",
            "- Director: read this agent's full folder (profile/secrets/memory/drives), "
            "decide what they do off-screen now, and record the consequences.",
            "",
        ]

    if interactions:
        lines += [
            "## Interactions",
            "",
            "> Structural collisions the metronome detected this tick. It found the",
            "> contention; it did **not** decide the outcome. Resolve each honestly",
            "> (resources are a hint, not a verdict; use the d6 oracle or a dice pool",
            "> for genuine uncertainty). When a clash matures into a standing conflict,",
            "> **promote it to `Game/plots.md`** as a new plot entry.",
            "",
        ]
        for it in interactions:
            who = f"{it.a.name} vs {it.b.name}" if it.b else f"{it.a.name} → player"
            over = f" over `{it.over}`" if it.over and it.over != "player" else ""
            lines += [
                f"### {who}{over}",
                f"- Kind: {it.kind}",
                "- Participants: "
                + ", ".join(
                    f"{p.name} (`{p.path.as_posix()}`)"
                    for p in (it.a, it.b) if p is not None),
                f"- Why: {it.why}",
            ]
            if it.hint:
                lines.append(f"- Advantage hint: {it.hint}")
            if it.standing:
                lines.append(
                    f"- Control ledger: {it.standing}  |  phase: {it.phase}  "
                    "(deterministic — narrate what this number *means*, don't change it)")
            lines.append(
                "- Resolver: decide what actually happens between them this tick, "
                "in character and in the live game's idiom; promote it to "
                "`Game/plots.md` if it becomes a standing conflict.")
            lines.append("")

    if reflectors:
        lines += [
            "## Reflection",
            "",
            "> These agents just completed a phase or culminated a clock — the",
            "> agent loop's *reflect* step. Synthesise their recent memory into 1–2",
            "> higher-level beliefs and append them to that agent's `drives.md`",
            "> **Reflection notes**. If a new belief warrants it, the director may",
            "> *re-plan*: adjust the agent's `goal` / `clock` / `relationships`.",
            "",
        ]
        for a in reflectors:
            why = "entered " + str(a.fields.get("state")) if a.transitioned \
                else "clock filled"
            lines += [
                f"### {a.name}",
                f"- Source: `{a.path.as_posix()}`",
                f"- Trigger: {why}",
                "- Reflect: append a synthesised belief to their Reflection notes; "
                "re-plan if it changed what they want.",
                "",
            ]

    text = "\n".join(lines) + "\n"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return path, text


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def run(root, args):
    agents = discover_agents(root)
    for a in agents:
        tick(a, args.elapsed, args.dawdle, args.fail)
    candidates = sorted(
        (a for a in agents if changed(a)),
        key=lambda a: (-priority(a), a.name),
    )
    selected = candidates[: args.max]
    interactions = detect_interactions(agents, args.max)
    apply_ledgers(root, agents, interactions, args.dry_run)
    # An agent is "due for reflection" when it completes a phase (FSM transition)
    # or culminates a clock — natural beats to synthesise what it has learned.
    reflectors = [a for a in agents if a.transitioned or a.became_full][: args.max]
    if not args.dry_run:
        write_back(agents)
    _, _ = write_queue(root, selected, interactions, reflectors, args, args.dry_run)
    print(summarize(agents, selected, interactions, reflectors, args))
    if args.dry_run:
        print("  (--dry-run: no files written.)")
    return 0


def _find_root(start):
    """Walk up from cwd to find the campaign root (has CLAUDE.md or Game/)."""
    cur = start.resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return start


def main(argv):
    p = argparse.ArgumentParser(description="Advance the living world by one tick.")
    p.add_argument("--elapsed", type=int, default=1,
                   help="units of time passing (default 1; use for time-skips)")
    p.add_argument("--dawdle", action="store_true",
                   help="the Player stalled — advance 'dawdle' clocks")
    p.add_argument("--fail", action="store_true",
                   help="a roll failed forward — advance 'on_fail' clocks")
    p.add_argument("--max", type=int, default=3,
                   help="max agents to queue for deliberation (default 3)")
    p.add_argument("--dry-run", action="store_true",
                   help="compute and print, but write no files")
    p.add_argument("--self-test", action="store_true",
                   help="run built-in assertions and exit")
    args = p.parse_args(argv[1:])

    if args.self_test:
        return _self_test()

    root = _find_root(Path.cwd())
    try:
        return run(root, args)
    except Exception as e:  # never crash a play session over a malformed block
        print(f"world_tick error: {e}\n(The world stands still this tick.)")
        return 1


# --------------------------------------------------------------------------- #
# Built-in self-test (python world_tick.py --self-test)
# --------------------------------------------------------------------------- #


def _self_test():
    import tempfile

    # --- parser ---
    fields = parse_block(
        'living: true\n'
        'state: scheming\n'
        'goal: "Seize the seat"\n'
        'clock: { filled: 2, total: 6 }\n'
        'advances_when: dawdle\n'
        'salience: 3\n'
        'states:\n'
        '  scheming: { to: moving, when: "clock>=3" }\n'
        '  moving: { to: confronting, when: "always" }\n'
    )
    assert fields["living"] is True
    assert fields["goal"] == "Seize the seat"
    assert fields["clock"] == {"filled": 2, "total": 6}
    assert fields["states"]["scheming"] == {"to": "moving", "when": "clock>=3"}

    # --- guards ---
    assert eval_guard("always", 0, 6) is True
    assert eval_guard("clock>=3", 3, 6) is True
    assert eval_guard("clock>=3", 2, 6) is False
    assert eval_guard("clock_full", 6, 6) is True
    assert eval_guard("garbage", 9, 9) is False  # unknown never fires

    # --- advancement amounts ---
    assert advance_amount("always", 3, False, False) == 3
    assert advance_amount("dawdle", 3, True, False) == 1
    assert advance_amount("dawdle", 3, False, False) == 0
    assert advance_amount("on_fail", 1, False, True) == 1
    assert advance_amount("manual", 9, True, True) == 0

    # --- end-to-end tick + transition + selection + surgical write-back ---
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "CLAUDE.md").write_text("x", encoding="utf-8")
        npc = root / "Cast" / "vance"
        npc.mkdir(parents=True)
        drives = npc / "drives.md"
        drives.write_text(
            "---\n"
            "living: true\n"
            "state: scheming          # current node\n"
            'goal: "Take the seat"\n'
            "clock: { filled: 2, total: 3 }\n"
            "advances_when: dawdle\n"
            "salience: 4\n"
            "states:\n"
            "  scheming: { to: moving, when: \"clock>=3\" }\n"
            "---\n\n"
            "## Agenda\nProse the director reads.\n",
            encoding="utf-8",
        )
        # a non-living NPC must be ignored
        idle = root / "Cast" / "extra"
        idle.mkdir(parents=True)
        (idle / "drives.md").write_text(
            "---\nliving: false\nstate: idle\n---\n", encoding="utf-8")
        # the _template skeleton must be skipped even though it says living: true
        tmpl = root / "Cast" / "_template"
        tmpl.mkdir(parents=True)
        (tmpl / "drives.md").write_text(
            "---\nliving: true\nstate: scheming\nclock: { filled: 0, total: 3 }\n"
            "advances_when: always\n---\n", encoding="utf-8")

        class A:  # minimal args
            elapsed, dawdle, fail, max, dry_run = 1, True, False, 3, False

        run(root, A())

        text = drives.read_text(encoding="utf-8")
        assert "state: moving" in text, "state should have transitioned and persisted"
        assert "filled: 3" in text, "clock should have advanced and persisted"
        assert "# current node" in text, "trailing comment must be preserved"
        assert "## Agenda" in text, "prose body must be preserved"

        queue = (root / "Game" / ".world-tick-queue.md").read_text(encoding="utf-8")
        assert "vance" in queue and "extra" not in queue, "only living, moved agents queue"
        assert "_template" not in queue, "the _template skeleton must never be ticked"
        assert "entered **moving**" in queue

    # --- interaction detection (the emergence layer) ---
    def _mk(name, block, moved=True):
        a = Agent(name, parse_block(block), Path(f"Cast/{name}/drives.md"), (0, 0))
        a.advanced = 1 if moved else 0
        return a

    mara = _mk("mara",
               "living: true\nstate: scheming\n"
               "goal: { pursue: control, target: harbor-council }\n"
               "salience: 4\nresources: { influence: 2, secrets: 4 }\n"
               "relationships:\n  vance: { tie: rival, weight: -4 }\n")
    vance2 = _mk("vance",
                 "living: true\nstate: scheming\n"
                 "goal: { pursue: control, target: harbor-council }\n"
                 "salience: 3\nresources: { muscle: 3 }\n")
    bryce = _mk("bryce",
                "living: true\nstate: scheming\n"
                "goal: { pursue: control, target: harbor-council }\n"
                "salience: 2\nrelationships:\n  mara: { tie: ally, weight: 3 }\n")
    hunter = _mk("hunter",
                 "living: true\nstate: moving\n"
                 "goal: { pursue: destroy, target: player }\nsalience: 5\n")

    ix = detect_interactions([mara, vance2, bryce, hunter])
    kinds = {(i.kind, tuple(sorted([i.a.name, i.b.name if i.b else "player"])))
             for i in ix}
    assert ("contested-goal", ("mara", "vance")) in kinds, "rivals over one target collide"
    assert ("contested-goal", ("bryce", "mara")) not in kinds, "allies don't collide"
    assert ("player-pressure", ("hunter", "player")) in kinds, "goal at player → pressure"

    # group-mates default allied: same group + same target must NOT collide.
    g1 = _mk("g1", "living: true\nstate: s\ngroup: camarilla\n"
                   "goal: { pursue: control, target: court }\n")
    g2 = _mk("g2", "living: true\nstate: s\ngroup: camarilla\n"
                   "goal: { pursue: control, target: court }\n")
    assert not any(i.kind == "contested-goal" for i in detect_interactions([g1, g2])), \
        "same-group agents over one target are allied, not colliding"
    mv = next(i for i in ix if i.kind == "contested-goal" and {i.a.name, i.b.name} == {"mara", "vance"})
    assert "mara better-resourced" in mv.hint, "resource advantage hint (6 vs 3)"

    # rivalry rule (b): hostile edge + BOTH moved, even on different targets.
    a1 = _mk("a", "living: true\nstate: s\ngoal: { pursue: control, target: x }\n"
                  "relationships:\n  b: { tie: grudge, weight: -5 }\n")
    b1 = _mk("b", "living: true\nstate: s\ngoal: { pursue: control, target: y }\n")
    assert any(i.kind == "rivalry" for i in detect_interactions([a1, b1]))
    b_idle = _mk("b", "living: true\nstate: s\ngoal: { pursue: control, target: y }\n",
                 moved=False)
    assert not any(i.kind == "rivalry" for i in detect_interactions([a1, b_idle])), \
        "rivalry needs both to move this tick"

    # backward-compat: a legacy plain-string goal must never crash detection.
    legacy = _mk("old", 'living: true\nstate: s\ngoal: "a plain string goal"\n')
    assert detect_interactions([legacy]) == [], "string goals don't collide, don't crash"

    # --- deterministic control ledger over a contested entity ---
    if ledger_mod is not None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Game").mkdir(parents=True)
            (root / "Game" / "current-scene.md").write_text(
                "**Day 5 — evening.** The harbor.\n", encoding="utf-8")
            ixs = detect_interactions([mara, vance2])
            apply_ledgers(root, [mara, vance2], ixs, dry_run=False)
            mv2 = next(i for i in ixs if i.kind == "contested-goal")
            assert mv2.standing and "holder: mara" in mv2.standing, mv2.standing
            led = (root / "Game" / "ledgers.md").read_text(encoding="utf-8")
            assert "## harbor-council" in led and "mara=" in led
            # dry-run must NOT persist the ledger file
            with tempfile.TemporaryDirectory() as d2:
                root2 = Path(d2)
                (root2 / "Game").mkdir(parents=True)
                apply_ledgers(root2, [mara, vance2], detect_interactions([mara, vance2]),
                              dry_run=True)
                assert not (root2 / "Game" / "ledgers.md").exists(), "dry-run writes nothing"

    print("world_tick self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
