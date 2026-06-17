#!/usr/bin/env python3
"""The living-world dashboard — the author's god-view console.

Where `world_tick.py` *advances* the living world and `world_scribe.py` *records*
what moved, this tool simply *shows* it: it reads the scattered GM-only state
(plots, developments, the living cast, the control ledgers) and renders one
readable page — `Game/world-dashboard.md` — answering the two questions the
Player asked for:

  1. **What's going on?**  — a tick-by-tick view of the world in motion: who's
     active, what just happened off-screen, and where the pressure is building.
  2. **What could I pull on?** — every plot in the world, grouped by how involved
     the Player's character already is, so they can pick a thread to lean into.

It invents nothing and decides nothing — it is a *view*, the way `dice.py` is a
roll: deterministic and auditable. It reuses the existing parsers wholesale
(`world_tick.discover_agents`, `ledger.load_ledgers`) rather than re-reading the
files by hand.

**This file is GM / author tier — it CONTAINS SECRETS** (unaware plots, NPC
drives, the contested-control numbers). It is the opposite of the spoiler-free
`PLAYER-NOTES.md`: the Player reads it *as author*. So instead of *filtering*
secrets out, every item is **tagged** by spoiler tier — 🟢 KNOWN / 🟡 SENSED /
🔴 HIDDEN — so the author can see at a glance what their character has actually
earned. Never hand this file to an `npc-actor`; never index it as public (see
`memory_index.classify`, which skips it).

Usage:
    python Tools/world_dashboard.py             # (re)write Game/world-dashboard.md
    python Tools/world_dashboard.py --dry-run   # print to stdout, write nothing
    python Tools/world_dashboard.py --player     # strict view: KNOWN/SENSED only,
                                                #   no GM internals (a safety extra)
    python Tools/world_dashboard.py --self-test  # built-in assertions, then exit
"""

import argparse
import re
import sys
from pathlib import Path

# Sibling modules: the deterministic metronome (for its parsers) and the control
# ledger. Reuse, don't reinvent. Optional — the dashboard degrades to whatever it
# can read if one is unavailable from an odd cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import world_tick as wt
except Exception:  # pragma: no cover
    wt = None
try:
    import ledger as ledger_mod
except Exception:  # pragma: no cover
    ledger_mod = None

OUT_REL = ("Game", "world-dashboard.md")

# Spoiler tiers: (emoji, label). The whole point of the god-view file.
KNOWN = ("🟢", "KNOWN")
SENSED = ("🟡", "SENSED")
HIDDEN = ("🔴", "HIDDEN")

_FIELD_RE = re.compile(r"^\s*-\s*([A-Za-z][\w /]*?):\s*(.*)$")
_CLOCK_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
_DAY_RE = re.compile(r"Day\s+(\d+)")
# A real list item ('- text'), NOT a '---' horizontal rule (which would otherwise
# be captured as a bullet and swallow the entry's detail line).
_BULLET_RE = re.compile(r"^-\s+\S")


# --------------------------------------------------------------------------- #
# Tolerant little parsers for the two prose files that have no parser yet.
# Both skip ```fenced``` code (so the template's *example* entry is never read
# as a real one) and tolerate the blank-template placeholder bullets.
# --------------------------------------------------------------------------- #


def _split_id_title(heading):
    """`<id> — <Title>` → ('<id>', '<Title>'); tolerant of '-' and no dash.

    With no separator the whole heading is the id and the title is empty (the
    renderer then shows just the id, not a redundant 'id — id').
    """
    for sep in ("—", " - "):
        if sep in heading:
            left, _, right = heading.partition(sep)
            return left.strip(), right.strip()
    return heading.strip(), ""


def _fields_from(lines):
    f = {}
    for ln in lines:
        m = _FIELD_RE.match(ln)
        if m:
            f[m.group(1).strip().lower()] = m.group(2).strip()
    return f


def parse_plots(text):
    """Parse every `### <id> — <Title>` plot entry into a dict (fields lowered)."""
    plots, in_fence, section, cur = [], False, None, None
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m3 = re.match(r"^###\s+(.*\S)\s*$", raw)
        m2 = re.match(r"^##\s+(.*\S)\s*$", raw)
        if m3:
            if cur:
                plots.append(cur)
            pid, title = _split_id_title(m3.group(1).strip())
            cur = {"id": pid, "title": title, "section": section, "lines": []}
        elif m2:
            if cur:
                plots.append(cur)
                cur = None
            section = m2.group(1).strip()
        elif cur is not None and _BULLET_RE.match(s):
            cur["lines"].append(raw)
    if cur:
        plots.append(cur)
    for p in plots:
        p["fields"] = _fields_from(p.pop("lines"))
    return plots


def parse_developments(text):
    """Parse every `## [Day N ...] — <agent>: <headline>` entry into a dict."""
    devs, in_fence, cur = [], False, None
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^##\s+(.*\S)\s*$", raw)
        if m:
            if cur:
                devs.append(cur)
                cur = None
            head = m.group(1).strip()
            if re.search(r"\[?\s*Day\s+\d+", head):   # a real day-stamped entry
                cur = {"head": head, "lines": []}
            continue
        if re.match(r"^###\s+", raw):                 # leaves the "Entry format" note
            if cur:
                devs.append(cur)
                cur = None
            continue
        if cur is not None and _BULLET_RE.match(s):
            cur["lines"].append(raw)
    if cur:
        devs.append(cur)
    for d in devs:
        d["fields"] = _fields_from(d["lines"])
        # the first non-field bullet with real content is the "what happened" line
        detail = ""
        for ln in d["lines"]:
            if _FIELD_RE.match(ln):
                continue
            cand = ln.strip().lstrip("-").strip()
            if cand:
                detail = cand
                break
        d["detail"] = detail
        m = _DAY_RE.search(d["head"])
        d["day"] = int(m.group(1)) if m else None
    return devs


# --------------------------------------------------------------------------- #
# Spoiler tiering.
# --------------------------------------------------------------------------- #


def plot_tier(involvement, surface):
    inv = (involvement or "").strip().lower().split()
    inv = inv[0] if inv else ""
    surf = (surface or "").strip().lower()
    known_inv = inv in ("aware", "observing", "participating")
    if known_inv and surf.startswith("now"):
        return KNOWN
    # Known of (but not live), or surfacing soon → sensed/rumor. The `now` case
    # is already handled above, so any remaining known involvement is SENSED.
    if known_inv or surf.startswith("soon"):
        return SENSED
    return HIDDEN


def dev_tier(surface):
    surf = (surface or "").strip().lower()
    if surf.startswith("now"):
        return KNOWN
    if surf.startswith("soon"):
        return SENSED
    return HIDDEN


def _tag(tier):
    return f"{tier[0]} {tier[1]}"


# --------------------------------------------------------------------------- #
# Small render helpers.
# --------------------------------------------------------------------------- #


def clock_bar(value):
    """'2/6' (or a {filled,total} dict) → '▓▓░░░░ 2/6'. '—' when there's none."""
    filled = total = 0
    if isinstance(value, dict):
        filled, total = int(value.get("filled", 0) or 0), int(value.get("total", 0) or 0)
    elif value:
        m = _CLOCK_RE.search(str(value))
        if m:
            filled, total = int(m.group(1)), int(m.group(2))
    if total <= 0:
        return "—"
    f = max(0, min(total, filled))
    return "▓" * f + "░" * (total - f) + f" {filled}/{total}"


def _mood(fields):
    m = fields.get("mood")
    if isinstance(m, dict) and m:
        return ", ".join(f"{k} {v}" for k, v in m.items())
    return None


def _goal_target_str(agent):
    # Reuse world_tick's own goal formatter so the dashboard reads identically to
    # the tick queue (pursue target (success)); fall back if it's unavailable.
    if wt is not None:
        return wt._fmt_goal(agent)
    g = agent.fields.get("goal")
    if isinstance(g, dict):
        bits = " ".join(str(g[k]) for k in ("pursue", "target") if g.get(k))
        return bits or "—"
    return str(g) if g else "—"


# --------------------------------------------------------------------------- #
# Building the dashboard.
# --------------------------------------------------------------------------- #


def _last_tick_movers(root):
    """Names queued by the most recent tick, if the ephemeral queue is around."""
    q = Path(root) / "Game" / ".world-tick-queue.md"
    if not q.exists():
        return None, []
    text = q.read_text(encoding="utf-8")
    tick = next((ln.strip() for ln in text.splitlines() if ln.startswith("Tick:")), None)
    movers, in_section = [], True
    for ln in text.splitlines():
        if ln.startswith("## "):
            name = ln[3:].strip()
            if name in ("Interactions", "Reflection"):
                in_section = False
                continue
            if in_section:
                movers.append(name)
    return tick, movers


def build(root, god=True):
    """Render the dashboard markdown. `god=False` → strict KNOWN/SENSED view."""
    root = Path(root)
    day = wt._current_day(root) if wt else None
    agents = wt.discover_agents(root) if wt else []
    ledgers = ledger_mod.load_ledgers(root) if ledger_mod else {}

    plots_path = root / "Game" / "plots.md"
    devs_path = root / "Game" / "developments.md"
    plots = parse_plots(plots_path.read_text(encoding="utf-8")) if plots_path.exists() else []
    devs = parse_developments(devs_path.read_text(encoding="utf-8")) if devs_path.exists() else []

    L = []
    L.append(
        "<!-- GENERATED by Tools/world_dashboard.py — do NOT hand-edit; it is "
        "overwritten every tick and on demand.\n"
        "     GM / AUTHOR tier: this file CONTAINS SECRETS (unaware plots, NPC "
        "drives, contested-control numbers).\n"
        "     It is NOT the spoiler-free PLAYER-NOTES.md. Never hand it to an "
        "npc-actor or index it as public. -->")
    L.append("")
    title = "World Dashboard — the author's console"
    if not god:
        title = "World Dashboard — your view"
    L.append(f"# {title}")
    L.append("")
    daystamp = f"Day {day}" if day is not None else "Day —"
    if god:
        L.append("> A god-view of the living world: what's moving, and every thread "
                 "you could pull. Spoiler-tiered so you can see at a glance what your "
                 "character actually knows.")
        L.append("")
        L.append(f"*{daystamp}.*  **Legend:** "
                 f"{_tag(KNOWN)} (your character knows it) · "
                 f"{_tag(SENSED)} (rumor / surfacing soon) · "
                 f"{_tag(HIDDEN)} (off-screen — not yet earned in play).")
    else:
        L.append("> What your character knows and senses about the wider world — and "
                 "the threads open to you. (Spoiler-free: brewing secrets are left out.)")
        L.append("")
        L.append(f"*{daystamp}.*")
    L.append("")

    # ----- §1 The world right now -------------------------------------------- #
    L.append("## 1 · The world right now")
    L.append("")

    if god:
        # Living cast roster (GM internals — author view only).
        L.append("### Who's in motion")
        movers_sorted = sorted(agents, key=lambda a: (-wt.priority(a), a.name)) if agents else []
        if not movers_sorted:
            L.append("- *The world is quiet — no living agents yet. Promote an NPC with "
                     "a `drives.md` (`living: true`) to bring the world to life.*")
        for a in movers_sorted:
            state = a.fields.get("state")
            bar = clock_bar(a.fields.get("clock"))
            sal = a.fields.get("salience")
            line = (f"- {HIDDEN[0]} **{a.name}** — state `{state}` · clock {bar} · "
                    f"salience {sal}")
            L.append(line)
            L.append(f"  - reaching for: {_goal_target_str(a)}")
            mood = _mood(a.fields)
            if mood:
                L.append(f"  - mood: {mood}")
        L.append("")

    # Recent developments — the "what just moved" feed.
    L.append("### What just happened")
    shown_devs = devs if god else [d for d in devs
                                   if dev_tier(d["fields"].get("surface")) != HIDDEN]
    shown_devs = sorted(shown_devs, key=lambda d: (d["day"] is None, -(d["day"] or 0)))
    if not shown_devs:
        L.append("- *Nothing has stirred off-screen yet.*")
    for d in shown_devs[:12]:
        tier = dev_tier(d["fields"].get("surface"))
        drained = (d["fields"].get("drained") or "").lower().startswith("y")
        flags = []
        if d["fields"].get("surface"):
            flags.append(f"surface: {d['fields']['surface']}")
        flags.append("drained" if drained else "fresh")
        head = d["head"]
        L.append(f"- {_tag(tier)} — {head}")
        if d["detail"]:
            L.append(f"  - {d['detail']}")
        L.append(f"  - *{' · '.join(flags)}*")
    L.append("")

    if god:
        # Collisions & contested control — where pressure is building.
        L.append("### Where the pressure is building")
        cols, pressers = _latent_collisions(agents)
        any_pressure = False
        for over, a, b in cols:
            any_pressure = True
            led = ledgers.get(over)
            stand = f" · {led.standing()} · phase {led.phase()}" if led else ""
            he = wt._hostile_edge(a, b)
            rel = f" ({he[0]} {he[1]})" if he else ""
            L.append(f"- {HIDDEN[0]} **{a.name}** vs **{b.name}** over `{over}`{rel}{stand}")
        for a in pressers:
            any_pressure = True
            L.append(f"- {HIDDEN[0]} **{a.name}** is moving on **you** "
                     f"(goal: {_goal_target_str(a)})")
        # ledgers with no live collision this read still matter
        for entity, led in sorted(ledgers.items()):
            if entity not in {c[0] for c in cols}:
                any_pressure = True
                L.append(f"- {HIDDEN[0]} contested: `{entity}` — {led.standing()} · "
                         f"phase {led.phase()}")
        if not any_pressure:
            L.append("- *No open contests — nobody is reaching for the same thing yet.*")
        L.append("")

        tick, movers = _last_tick_movers(root)
        if tick:
            L.append("### Most recent tick")
            L.append(f"- {tick}")
            if movers:
                L.append(f"- Queued movers: {', '.join(movers)}")
            L.append("")

    # ----- §2 Threads you could pull ----------------------------------------- #
    L.append("## 2 · Threads you could pull")
    L.append("")
    order = [("participating", "You're in it"),
             ("observing", "You're watching"),
             ("aware", "You've heard of it"),
             ("unaware", "Off your radar (your character doesn't know yet)")]
    buckets = {k: [] for k, _ in order}
    resolved = []
    other = []
    for p in plots:
        inv = (p["fields"].get("player involvement") or "").strip().lower().split()
        inv = inv[0] if inv else ""
        if (p.get("section") or "").lower().startswith("resolved"):
            resolved.append(p)
        elif inv in buckets:
            buckets[inv].append(p)
        else:
            other.append(p)

    def _render_plot(p):
        f = p["fields"]
        tier = plot_tier(f.get("player involvement"), f.get("surface"))
        bar = clock_bar(f.get("clock"))
        state = f.get("state") or "—"
        label = f"**`{p['id']}`**" + (f" — {p['title']}" if p.get("title") else "")
        head = f"- {_tag(tier)} {label} · state {state}"
        if bar != "—":
            head += f" · clock {bar}"
        L.append(head)
        if f.get("stakes"):
            L.append(f"  - Stakes: {f['stakes']}")
        meta = []
        if f.get("surface"):
            meta.append(f"surface: {f['surface']}")
        if f.get("participants"):
            meta.append(f"who: {f['participants']}")
        if meta:
            L.append(f"  - *{' · '.join(meta)}*")

    rendered_any = False
    for key, label in order:
        group = buckets[key]
        if not god and plot_tier_for_bucket(key) == HIDDEN:
            continue  # strict view never shows unaware plots
        if not group:
            continue
        rendered_any = True
        L.append(f"### {label}")
        for p in group:
            _render_plot(p)
        L.append("")
    if god and other:
        rendered_any = True
        L.append("### Other plots")
        for p in other:
            _render_plot(p)
        L.append("")
    if god and resolved:
        L.append("### Resolved")
        for p in resolved:
            _render_plot(p)
        L.append("")
    if not rendered_any:
        L.append("*No plots are in motion yet — the world hasn't started colliding. "
                 "As you play, threads will appear here.*")
        L.append("")

    L.append("---")
    L.append("> **To pull on a thread:** tell the GM — e.g. *\"I want to lean into "
             "`<plot-id>`.\"* The GM raises your involvement and weaves an offered hook "
             "into the next scene (no record-scratch). You can also just ask *\"show me "
             "the world\"* anytime to refresh this page.")
    return "\n".join(L) + "\n"


def plot_tier_for_bucket(involvement_key):
    """Worst-case tier for a whole involvement bucket (used by the strict view)."""
    if involvement_key == "unaware":
        return HIDDEN
    return SENSED


def _latent_collisions(agents):
    """Standing contention: non-allied agents sharing a target (motion-agnostic).

    `world_tick.detect_interactions` only fires for agents that *moved this tick*;
    a dashboard reads state statically, so it surfaces latent collisions instead,
    reusing the same `goal_target` / `_allied` rules.
    """
    if not wt:
        return [], []
    by_target = {}
    for a in agents:
        t = wt.goal_target(a)
        if t and t != "player":
            by_target.setdefault(t, []).append(a)
    cols = []
    for t, group in by_target.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if not wt._allied(a, b):
                    cols.append((t, a, b))
    pressers = [a for a in agents if wt.goal_target(a) == "player"]
    return cols, pressers


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _find_root(start):
    cur = Path(start).resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return Path(start)


def run(root, args):
    text = build(root, god=not args.player)
    if args.dry_run:
        sys.stdout.write(text)
        print("\n  (--dry-run: no file written.)")
        return 0
    out = Path(root) / OUT_REL[0] / OUT_REL[1]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out.as_posix()} ({'player view' if args.player else 'god-view'}).")
    return 0


def main(argv):
    p = argparse.ArgumentParser(description="Render the living-world dashboard.")
    p.add_argument("--dry-run", action="store_true",
                   help="print the dashboard, write no file")
    p.add_argument("--player", action="store_true",
                   help="strict spoiler-free view (KNOWN/SENSED only, no GM internals)")
    p.add_argument("--self-test", action="store_true",
                   help="run built-in assertions and exit")
    args = p.parse_args(argv[1:])
    # The dashboard is emoji-heavy; keep --dry-run from choking on a cp1252 console.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover — older Python / non-reconfigurable stream
        pass
    if args.self_test:
        return _self_test()
    root = _find_root(Path.cwd())
    try:
        return run(root, args)
    except Exception as e:  # never crash a play session over a malformed file
        print(f"world_dashboard error: {e}\n(No dashboard written this time.)")
        return 1


# --------------------------------------------------------------------------- #
# Built-in self-test
# --------------------------------------------------------------------------- #


def _self_test():
    import tempfile

    # --- tiering ---
    assert plot_tier("participating", "now") == KNOWN
    assert plot_tier("aware", "now") == KNOWN
    assert plot_tier("aware", "soon (trigger: x)") == SENSED
    assert plot_tier("aware", "hidden") == SENSED      # known of, but partial
    assert plot_tier("unaware", "hidden") == HIDDEN
    assert plot_tier("unaware", "now") == HIDDEN       # involvement gates KNOWN
    assert dev_tier("now") == KNOWN and dev_tier("soon") == SENSED
    assert dev_tier("hidden") == HIDDEN

    # --- clock bar ---
    assert clock_bar("2/6") == "▓▓░░░░ 2/6"
    assert clock_bar({"filled": 3, "total": 3}) == "▓▓▓ 3/3"
    assert clock_bar("") == "—"

    # --- plots parser skips the fenced example and groups correctly ---
    plots_md = (
        "# Plots (GM ONLY)\n\n"
        "## How an entry works\n"
        "```\n"
        "### example-id — Example (this is in a fence, must be ignored)\n"
        "- Player involvement: unaware\n"
        "```\n\n"
        "## World plots\n"
        "### harbor-seat — The Harbor Seat\n"
        "- Participants: mara, vance\n"
        "- Stakes: who controls the council\n"
        "- State: rising\n"
        "- Clock: 2/6\n"
        "- Player involvement: unaware\n"
        "- Surface: hidden\n\n"
        "### the-courier — The Missing Courier\n"
        "- Stakes: a debt comes due\n"
        "- State: forming\n"
        "- Clock: 1/4\n"
        "- Player involvement: aware\n"
        "- Surface: now\n\n"
        "### rumor-mill — The Rumor Mill\n"
        "- State: rising\n"
        "- Player involvement: aware\n"
        "- Surface: hidden\n\n"
        "## Resolved\n"
        "### old-feud — The Old Feud\n"
        "- Player involvement: observing\n"
        "- Surface: now\n"
    )
    plots = parse_plots(plots_md)
    ids = {p["id"] for p in plots}
    assert "example-id" not in ids, "fenced example must not be parsed as a plot"
    assert {"harbor-seat", "the-courier", "old-feud", "rumor-mill"} <= ids, ids
    hs = next(p for p in plots if p["id"] == "harbor-seat")
    assert hs["title"] == "The Harbor Seat" and hs["fields"]["state"] == "rising"
    assert plot_tier(hs["fields"]["player involvement"], hs["fields"]["surface"]) == HIDDEN
    # aware-but-hidden: known of, not live → SENSED (must not be dropped/HIDDEN)
    rm = next(p for p in plots if p["id"] == "rumor-mill")
    assert plot_tier(rm["fields"]["player involvement"], rm["fields"]["surface"]) == SENSED

    # --- developments parser ---
    devs_md = (
        "# Developments (GM ONLY)\n\n"
        "## Pending\n\n"
        "## [Day 9 — Frostmoon] — mara: presses on the docks\n"
        "- Mara leaned on a dockhand for the swing vote.\n"
        "- Surface: now\n"
        "- Drained: no\n\n"
        "## [Day 7] — archive: a sealed vault\n"
        "- The old archive quietly sealed its vault.\n\n"
        "---\n"
        "### Entry format (for the director)\n"
        "```\n"
        "## [Day N] — agent: headline (fenced — ignore)\n"
        "- Surface: now\n"
        "```\n"
    )
    devs = parse_developments(devs_md)
    assert len(devs) == 2, devs
    assert devs[0]["day"] == 9 and devs[0]["fields"]["surface"] == "now"
    assert "dockhand" in devs[0]["detail"]
    # a development with no Surface field is HIDDEN (fails closed)
    assert "surface" not in devs[1]["fields"] and dev_tier(devs[1]["fields"].get("surface")) == HIDDEN

    # regression: a '---' rule between the headline and the detail must NOT swallow
    # the detail line (the rule isn't a bullet, so it's skipped, not captured).
    d_rule = parse_developments(
        "## [Day 3] — vance: a quiet move\n"
        "---\n"
        "- Vance slipped a note under the door.\n"
        "- Surface: soon\n")
    assert len(d_rule) == 1 and "note under the door" in d_rule[0]["detail"], d_rule

    # --- end-to-end build over a small synthetic campaign ---
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        game = root / "Game"
        game.mkdir(parents=True)
        (root / "CLAUDE.md").write_text("x", encoding="utf-8")
        (game / "current-scene.md").write_text(
            "## Where & when\n**Day 12 — evening.** The harbor.\n", encoding="utf-8")
        (game / "plots.md").write_text(plots_md, encoding="utf-8")
        (game / "developments.md").write_text(devs_md, encoding="utf-8")
        # two living NPCs contesting the same target → a latent collision
        for name, sal, extra in (("mara", 4, "resources: { influence: 3, secrets: 2 }\n"
                                             "relationships:\n  vance: { tie: rival, weight: -4 }\n"),
                                 ("vance", 3, "resources: { muscle: 2 }\n")):
            npc = root / "Cast" / name
            npc.mkdir(parents=True)
            (npc / "drives.md").write_text(
                "---\n"
                "living: true\n"
                "state: scheming\n"
                "goal: { pursue: control, target: harbor-seat }\n"
                "clock: { filled: 2, total: 6 }\n"
                "advances_when: dawdle\n"
                f"salience: {sal}\n"
                f"{extra}"
                "---\n\n## Agenda\nprose\n", encoding="utf-8")
        if ledger_mod is not None:
            ledger_mod.save_ledgers(root, {"harbor-seat": ledger_mod.Ledger(
                "harbor-seat", total=10, control={"mara": 6, "vance": 1, "_neutral": 3},
                holder="mara")})

        god_text = build(root, god=True)
        assert "## 1 · The world right now" in god_text
        assert "## 2 · Threads you could pull" in god_text
        assert "Day 12" in god_text
        assert "**mara**" in god_text and "harbor-seat" in god_text
        assert "vs **vance**" in god_text, "latent collision should render"
        assert "holder: mara" in god_text, "ledger standing should render"
        # an unaware plot is shown but flagged HIDDEN in god-view
        assert f"{_tag(HIDDEN)} **`harbor-seat`**" in god_text
        # a known thread is tagged KNOWN
        assert f"{_tag(KNOWN)} **`the-courier`**" in god_text

        player_text = build(root, god=False)
        assert HIDDEN[0] not in player_text, "strict view must contain no 🔴 items"
        assert "harbor-seat" not in player_text, "strict view hides unaware plots"
        assert "Who's in motion" not in player_text, "strict view hides GM internals"
        assert "the-courier" in player_text, "strict view keeps known threads"
        # an aware-but-hidden plot is kept as SENSED, not dropped
        assert f"{_tag(SENSED)} **`rumor-mill`**" in player_text, "SENSED thread must survive"
        # a no-Surface (HIDDEN) development is filtered out of the player view
        assert "sealed vault" not in player_text, "strict view hides HIDDEN developments"
        assert "sealed vault" in god_text, "god-view still shows it"

    # --- empty world degrades gracefully ---
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Game").mkdir(parents=True)
        (root / "CLAUDE.md").write_text("x", encoding="utf-8")
        txt = build(root, god=True)
        assert "world is quiet" in txt and "Nothing has stirred" in txt

    print("world_dashboard self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
