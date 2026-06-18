"""Social topology — ported from Tools/social.py.

The union of every living agent's `relationships` graph *is* a social network.
This module reads it and answers three deterministic questions (no model, no
randomness): who learns of an observable event (BFS within N hops, +1 hop for
in-group), who shares a group, and a derived reputation. The secrecy **firewall**
(`safe_headline` / `_shares_ngram`) is ported verbatim — it is what keeps a
secret goal/success string from ever reaching actor-safe memory.

Difference from the original: instead of writing to `Cast/*/memory.md`,
`propagate` returns the actor-safe observation records for the DB layer to
persist into the `memory_observations` table. The firewall still runs *here*, so
a secret-echoing headline is dropped before it can ever be written.
"""

from __future__ import annotations

import re
from collections import deque

from . import agent as A


def build_graph(agents):
    """Undirected adjacency among living NPCs, from their relationship edges.

    An edge exists if either side names the other; weight is the strongest
    |weight| of the two directions.
    """
    npc_names = {a.name for a in agents}
    graph = {a.name: {} for a in agents}
    by_name = {a.name: a for a in agents}
    for a in agents:
        for other, edge in A.rels(a).items():
            if other in npc_names and other != a.name:
                w = abs(A.weight(edge))
                graph[a.name][other] = max(graph[a.name].get(other, 0), w)
                graph[other][a.name] = max(graph[other].get(a.name, 0), w)
    return graph, by_name


def who_learns(graph, sources, max_hops=2, by_name=None):
    """Who hears of an event sourced at `sources`; return {learner: hops}.

    BFS distance over the relationship graph; a learner is admitted within
    `max_hops`, or `max_hops + 1` if they share a group with a source.
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
            g = A.group(by_name[s]) if s in by_name else None
            if g:
                src_groups.add(g)

    learned = {}
    for node, d in dist.items():
        if node in sources:
            continue
        limit = max_hops
        if by_name and node in by_name:
            g = A.group(by_name[node])
            if g and g in src_groups:
                limit = max_hops + 1
        if d <= limit:
            learned[node] = d
    return learned


def same_group(a, b):
    ga, gb = A.group(a), A.group(b)
    return ga is not None and ga == gb


def reputation(name, by_name, ledgers):
    """A derived standing: control held across all ledgers + own salience."""
    score = 0
    for led in (ledgers or {}).values():
        score += led.control.get(name, 0)
    a = by_name.get(name) if by_name else None
    if a is not None:
        score += A.salience(a)
    return score


def observation_line(day, participant, headline, hops):
    dl = f"Day {day}" if day is not None else "Day ?"
    how = "saw it first-hand" if hops <= 1 else "heard word"
    return f"about `{participant}`: {how} that {headline}"


# ── firewall — defense-in-depth (verbatim from social.py) ────────────────────

HEADLINE_MAX = 140
_WORD = re.compile(r"\w+", re.UNICODE)


def _tokens(s):
    return _WORD.findall(str(s or "").lower())


def forbidden_texts(agents):
    """Free-text spoiler fields from each living agent's drives front-matter: the
    goal's `pursue`/`success` strings (or a legacy string goal), and every
    relationship `note`. The short `target` id is excluded (common word)."""
    out = []
    items = agents.values() if isinstance(agents, dict) else (agents or [])
    for a in items:
        fields = getattr(a, "fields", {}) if a is not None else {}
        g = fields.get("goal")
        if isinstance(g, dict):
            for k in ("pursue", "success"):
                v = g.get(k)
                if isinstance(v, str) and v.strip():
                    out.append(v)
        elif isinstance(g, str) and g.strip():
            out.append(g)
        rels = fields.get("relationships")
        if isinstance(rels, dict):
            for edge in rels.values():
                note = edge.get("note") if isinstance(edge, dict) else None
                if isinstance(note, str) and note.strip():
                    out.append(note)
    return out


def _shares_ngram(text, forbidden, ngram=4):
    """True if `text` shares a verbatim run of words with any forbidden string."""
    htok = _tokens(text)
    if not htok:
        return False
    hgrams_by_n = {}
    for f in forbidden:
        ftok = _tokens(f)
        n = min(ngram, len(ftok))
        if n < 2 or len(htok) < n:
            continue
        if n not in hgrams_by_n:
            hgrams_by_n[n] = {tuple(htok[i:i + n]) for i in range(len(htok) - n + 1)}
        hgrams = hgrams_by_n[n]
        for i in range(len(ftok) - n + 1):
            if tuple(ftok[i:i + n]) in hgrams:
                return True
    return False


def safe_headline(headline, forbidden, max_len=HEADLINE_MAX, ngram=4):
    """Is this headline safe to write into actor-safe memory?"""
    h = " ".join(str(headline or "").split())
    if len(h) > max_len:
        return False
    return not _shares_ngram(h, forbidden, ngram)


def propagate(agents, events, max_hops=2):
    """Compute the actor-safe observation records for a batch of events.

    `events`: list of {participants: [names], headline, day}. Only *observable*
    events should be passed (the caller filters hidden/secret ones). Each headline
    is firewalled against the living agents' secret goal/success/note text; one
    that fails is dropped, never returned. Returns
    (observations, rejected_count) where each observation is a dict ready for the
    DB: {learner, day, about, text, hops}.
    """
    graph, by_name = build_graph(agents)
    forbidden = forbidden_texts(by_name)
    observations, rejected = [], 0
    for ev in events:
        headline = ev.get("headline", "something stirred")
        if not safe_headline(headline, forbidden):
            rejected += 1
            continue  # FIREWALL: never emit a headline that smells like drives.md
        sources = [p for p in ev.get("participants", []) if p in graph]
        if not sources:
            continue
        learners = who_learns(graph, sources, max_hops, by_name)
        for learner, hops in learners.items():
            part = sources[0] if len(sources) == 1 else ", ".join(sources)
            observations.append({
                "learner": learner,
                "day": ev.get("day"),
                "about": part,
                "text": observation_line(ev.get("day"), part, headline, hops),
                "hops": hops,
            })
    return observations, rejected
