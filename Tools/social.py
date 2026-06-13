#!/usr/bin/env python3
"""Social topology for the living world: who learns what, who stands where.

Ported in spirit from `the_city`'s `SocialConfig` (network_structure /
reputation / groups). The key idea borrowed: a population's **structure**
determines who observes whom, so information spreads asymmetrically rather than
everyone magically knowing everything.

In `storyteller` the network already exists — it's the union of every living
agent's `relationships` graph in their `drives.md`. This module reads that graph
and answers three deterministic questions (no model, no randomness):

  1. **Propagation** — when an *observable* off-screen event happens, which other
     NPCs come to hear of it? (Within N hops on the relationship graph.) Each
     learner gets an actor-safe observation appended to their `memory.md`
     "What I've learned about others" — the generative-agents observation step.
  2. **Groups** — same-faction membership (`group:` in the agent block) means
     in-group: they learn faster and default to allied.
  3. **Reputation** — a *derived* standing (control held across `ledgers.md` +
     salience), so it's always consistent with the deterministic world state and
     needs no separate store.

The firewall holds: only *observable* developments propagate (never a hidden
secret), and the note written to a learner's memory is the visible move only.

Usage:
    python Tools/social.py --graph        # print the living social graph
    python Tools/social.py --self-test
"""

import argparse
import re
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_tick  # reuse discover_agents + relationship parsing

try:
    import ledger as ledger_mod
except Exception:  # pragma: no cover
    ledger_mod = None


def _group(agent):
    g = agent.fields.get("group")
    return str(g).strip() if g not in (None, "") else None


def build_graph(root=None, agents=None):
    """Undirected adjacency among *living* NPCs, from their relationship edges.

    Nodes are living Cast NPCs (faction/world entries and the player are not
    learners — they have no memory.md). An edge exists if either side names the
    other; its weight is the strongest |weight| of the two directions.
    """
    if agents is None:
        agents = world_tick.discover_agents(root)
    npc_names = {a.name for a in agents}
    graph = {a.name: {} for a in agents}
    by_name = {a.name: a for a in agents}
    for a in agents:
        for other, edge in world_tick._rels(a).items():
            if other in npc_names and other != a.name:
                w = abs(world_tick._weight(edge))
                graph[a.name][other] = max(graph[a.name].get(other, 0), w)
                graph[other][a.name] = max(graph[other].get(a.name, 0), w)
    return graph, by_name


def who_learns(graph, sources, max_hops=2, by_name=None):
    """Who hears of an event sourced at `sources`; return {learner: hops}.

    Plain BFS distance over the relationship graph, then a learner is admitted
    within `max_hops` — or `max_hops + 1` if they share a group with a source
    (in-groups talk more, so a faction hears its own news one hop further).
    Sources themselves are excluded — they already know.
    """
    sources = [s for s in sources if s in graph]
    dist = {s: 0 for s in sources}
    q = deque(sources)
    while q:
        node = q.popleft()
        for nbr in graph.get(node, {}):
            if nbr not in dist:
                dist[nbr] = dist[node] + 1
                q.append(nbr)

    src_groups = set()
    if by_name:
        for s in sources:
            g = _group(by_name[s]) if s in by_name else None
            if g:
                src_groups.add(g)

    learned = {}
    for node, d in dist.items():
        if node in sources:
            continue
        limit = max_hops
        if by_name and node in by_name:
            g = _group(by_name[node])
            if g and g in src_groups:
                limit = max_hops + 1
        if d <= limit:
            learned[node] = d
    return learned


def same_group(a, b):
    """True if two agents share a non-empty group (in-group)."""
    ga, gb = _group(a), _group(b)
    return ga is not None and ga == gb


def reputation(name, by_name, ledgers):
    """A derived standing: control held across all ledgers + own salience.

    Derived (not stored) so it can never drift from the deterministic world
    state. GM-only signal — its *public* portion may colour how others treat
    them, but the number itself is backstage.
    """
    score = 0
    for led in (ledgers or {}).values():
        score += led.control.get(name, 0)
    a = by_name.get(name) if by_name else None
    if a is not None:
        score += world_tick._sal(a)
    return score


_OBS_HEADING = "## What I've learned about others"


def observation_line(day, participant, headline, hops):
    dl = f"Day {day}" if day is not None else "Day ?"
    how = "saw it first-hand" if hops <= 1 else "heard word"
    return f"- *[{dl}]* — about `{participant}`: {how} that {headline}"


def append_observation(root, learner, day, participant, headline, hops):
    """Append an actor-safe observation to a learner's memory.md."""
    p = Path(root) / "Cast" / learner / "memory.md"
    if not p.exists():
        return False
    text = p.read_text(encoding="utf-8")
    line = observation_line(day, participant, headline, hops)
    if line in text:
        return False  # idempotent: don't double-record the same beat
    if _OBS_HEADING in text:
        idx = text.index(_OBS_HEADING)
        nl = text.index("\n", idx)
        text = text[:nl + 1] + line + "\n" + text[nl + 1:]
    else:
        text = text.rstrip() + f"\n\n{_OBS_HEADING}\n{line}\n"
    p.write_text(text, encoding="utf-8")
    return True


def propagate(root, events, max_hops=2, agents=None):
    """For each observable event, record it in the memory of those who'd learn.

    `events` is a list of dicts: {participants: [names], headline, day}. Only
    pass *observable* events (the caller filters out hidden/secret ones). Returns
    the number of observation notes written.
    """
    graph, by_name = build_graph(root, agents)
    written = 0
    for ev in events:
        sources = [p for p in ev.get("participants", []) if p in graph]
        if not sources:
            continue
        learners = who_learns(graph, sources, max_hops, by_name)
        for learner, hops in learners.items():
            part = sources[0] if len(sources) == 1 else ", ".join(sources)
            if append_observation(root, learner, ev.get("day"), part,
                                   ev.get("headline", "something stirred"), hops):
                written += 1
    return written


def _self_test():
    import tempfile

    # --- graph + BFS reachability, including the in-group extra hop ---
    class A:
        def __init__(self, name, rels, group=None):
            self.name = name
            self.fields = {"relationships": rels, "salience": 3}
            if group:
                self.fields["group"] = group

    agents = [
        A("mara", {"vance": {"tie": "rival", "weight": -4},
                   "bryce": {"tie": "ally", "weight": 3}}, group="anarch"),
        A("vance", {}, group="camarilla"),
        A("bryce", {"cleo": {"tie": "kin", "weight": 4}}, group="anarch"),
        A("cleo", {}),
    ]
    graph, by_name = build_graph(agents=agents)
    assert graph["mara"]["vance"] == 4 and graph["vance"]["mara"] == 4, "undirected edge"
    assert graph["bryce"]["cleo"] == 4 and graph["mara"]["bryce"] == 3

    # From mara, 1 hop reaches vance + bryce; 2 hops also reaches cleo.
    l1 = who_learns(graph, ["mara"], max_hops=1, by_name=by_name)
    assert set(l1) == {"vance", "bryce"} and l1["vance"] == 1
    l2 = who_learns(graph, ["mara"], max_hops=2, by_name=by_name)
    assert "cleo" in l2 and l2["cleo"] == 2, l2

    # Groups + reputation.
    assert same_group(agents[0], agents[2]) and not same_group(agents[0], agents[1])
    if ledger_mod is not None:
        led = ledger_mod.Ledger("seat", control={"mara": 5, "vance": 1})
        assert reputation("mara", by_name, {"seat": led}) == 5 + 3  # control + salience

    # --- propagation writes an actor-safe note into a learner's memory.md ---
    drives_for = {
        "mara": ("---\nliving: true\nstate: s\n"
                 "relationships:\n  vance: { tie: rival, weight: -4 }\n---\n"),
        "vance": "---\nliving: true\nstate: s\n---\n",
        "bryce": "---\nliving: true\nstate: s\n---\n",
    }
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "CLAUDE.md").write_text("x", encoding="utf-8")
        for n, drv in drives_for.items():
            md = root / "Cast" / n
            md.mkdir(parents=True)
            (md / "memory.md").write_text(
                f"# {n} — memory\n\n## What I've learned about others\n",
                encoding="utf-8")
            (md / "drives.md").write_text(drv, encoding="utf-8")
        # mara seized the docks; vance (1 hop, rival) should hear of it.
        wrote = propagate(root, [{"participants": ["mara"],
                                  "headline": "Mara seized the customs house",
                                  "day": 7}], max_hops=2)
        vance_mem = (root / "Cast" / "vance" / "memory.md").read_text(encoding="utf-8")
        assert wrote >= 1 and "Mara seized the customs house" in vance_mem, vance_mem
        # idempotent: re-running writes nothing new.
        assert propagate(root, [{"participants": ["mara"],
                                 "headline": "Mara seized the customs house",
                                 "day": 7}]) == 0

    print("social self-test: OK")
    return 0


def main(argv):
    p = argparse.ArgumentParser(description="Social topology for the living world.")
    p.add_argument("--graph", action="store_true", help="print the living social graph")
    p.add_argument("--self-test", action="store_true", help="run assertions and exit")
    args = p.parse_args(argv[1:])
    if args.self_test:
        return _self_test()
    root = Path.cwd()
    for cand in [root, *root.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            root = cand
            break
    graph, _ = build_graph(root)
    for node in sorted(graph):
        nbrs = ", ".join(f"{n}({w})" for n, w in sorted(graph[node].items()))
        print(f"{node}: {nbrs or '(isolated)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
