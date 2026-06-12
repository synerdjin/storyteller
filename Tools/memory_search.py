#!/usr/bin/env python3
"""Semantic search over the campaign's local memory index.

Embeds a query with the local model and returns the most relevant chunks from
the index built by memory_index.py — each with a source CITATION (path + Day N)
so retrieved facts have real provenance the GM can verify, instead of being
recalled from a fallible model memory.

The `--scope` flag enforces the engine's secret firewall:
    gm      — everything (default; for the GM and the secret-aware world tools)
    public  — actor-safe only (player + public tiers): what you may put in an
              npc-actor briefing. EXCLUDES every secret and GM-working file.
    player  — player-facing only (PLAYER-NOTES, Story/ chapters).

Usage:
    python Tools/memory_search.py "the harbor conspiracy"
    python Tools/memory_search.py "what does Vance want" --scope public --owner vance
    python Tools/memory_search.py "recent betrayals" --since-day 10 --k 5
    python Tools/memory_search.py "..." --json        # machine-readable output
    python Tools/memory_search.py --self-test         # assertions (no model)
"""

import argparse
import json
import math
import sys
from pathlib import Path

import local_config

try:
    import local_client
except Exception:  # pragma: no cover
    local_client = None

INDEX_DIR = ("Game", ".memory-index")

# A scope names the set of visibility tiers it is allowed to see.
SCOPES = {
    "player": {"player"},
    "public": {"player", "public"},                 # actor-safe
    "gm": {"player", "public", "gm", "secret"},     # everything
}


def load_index(root):
    p = Path(root).joinpath(*INDEX_DIR, "index.jsonl")
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def load_meta(root):
    p = Path(root).joinpath(*INDEX_DIR, "meta.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def check_index_compatible(meta, embed_model, query_dim=None):
    """Guard against searching a stale index with the wrong embedder.

    cosine() uses zip(), which silently truncates mismatched-dimension
    vectors — so a query embedded by a *different* model than the one that
    built the index would return confidently-ranked garbage instead of an
    error. Refuse rather than mislead: the whole point of retrieval is to
    ground the fiction in real facts, not plausible noise.
    """
    idx_model = meta.get("embed_model")
    if idx_model and embed_model and idx_model != embed_model:
        raise RuntimeError(
            f"index was built with embedder '{idx_model}' but the config now "
            f"uses '{embed_model}' — the vectors are incomparable. "
            f"Run `python Tools/memory_index.py --rebuild`.")
    idx_dim = meta.get("dim")
    if idx_dim and query_dim is not None and query_dim != idx_dim:
        raise RuntimeError(
            f"query embedding has {query_dim} dims but the index has {idx_dim} "
            f"— re-embed with `python Tools/memory_index.py --rebuild`.")


def cosine(a, b):
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return s / (na * nb) if na and nb else 0.0


def search(root, query_vec, scope="gm", k=8, since_day=None, owner=None,
           ftype=None, recs=None):
    allow = SCOPES.get(scope, SCOPES["gm"])
    recs = load_index(root) if recs is None else recs
    scored = []
    for r in recs:
        if r.get("visibility") not in allow:
            continue
        if since_day is not None and (r.get("day") is None or r["day"] < since_day):
            continue
        if owner and r.get("owner") != owner:
            continue
        if ftype and r.get("type") != ftype:
            continue
        if "vector" not in r:
            continue
        scored.append((cosine(query_vec, r["vector"]), r))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def search_text(root, query, scope="gm", k=8, since_day=None, owner=None,
                ftype=None, cfg=None):
    """Convenience: embed `query` with the local model, then search."""
    if local_client is None:
        raise RuntimeError("local_client unavailable; cannot embed query")
    cfg = cfg or local_config.load_config(root)
    meta = load_meta(root)
    check_index_compatible(meta, cfg["embed_model"])      # fail fast on model swap
    vec = local_client.embed([query], cfg=cfg)[0]
    check_index_compatible(meta, cfg["embed_model"], len(vec))  # and on dim
    return search(root, vec, scope=scope, k=k, since_day=since_day,
                  owner=owner, ftype=ftype)


def _citation(r):
    day = f"Day {r['day']}" if r.get("day") is not None else "Day ?"
    head = f" :: {r['heading']}" if r.get("heading") else ""
    return f"[{day}] {r['path']}{head}"


def format_results(scored, snippet=240):
    if not scored:
        return "(no matches in scope)"
    out = []
    for score, r in scored:
        text = " ".join(r["text"].split())
        if len(text) > snippet:
            text = text[:snippet].rstrip() + "…"
        out.append(f"{score:.3f}  {_citation(r)}\n        {text}")
    return "\n".join(out)


def scope_banner(scope, count):
    """A header that makes the firewall scope of a result set self-evident.

    The default scope is `gm` (everything), so a result set pasted into an
    npc-actor briefing could carry secrets without anyone noticing. This banner
    labels every dump so a GM-scoped set is obviously *not* actor-safe.
    Returns (banner_text, actor_safe).
    """
    allow = SCOPES.get(scope, SCOPES["gm"])
    actor_safe = "secret" not in allow and "gm" not in allow
    tag = ("actor-safe" if actor_safe
           else "GM-ONLY — may contain secrets, NOT for an npc-actor briefing")
    return f"# scope={scope} ({tag}) — {count} result(s)", actor_safe


def results_json(scored):
    return [{"score": round(score, 4), "path": r["path"], "day": r.get("day"),
             "visibility": r["visibility"], "owner": r.get("owner"),
             "type": r["type"], "heading": r.get("heading"), "text": r["text"]}
            for score, r in scored]


def _find_root(start):
    cur = Path(start).resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return Path(start)


def main(argv):
    local_config.enable_utf8_output()
    p = argparse.ArgumentParser(description="Semantic search over campaign memory.")
    p.add_argument("query", nargs="?", help="what to search for")
    p.add_argument("--scope", choices=sorted(SCOPES), default="gm",
                   help="visibility firewall (default gm = everything)")
    p.add_argument("--k", type=int, default=8, help="how many results (default 8)")
    p.add_argument("--since-day", type=int, default=None,
                   help="only chunks stamped on/after this campaign day")
    p.add_argument("--owner", default=None,
                   help="restrict to one character's files (Cast folder name)")
    p.add_argument("--type", dest="ftype", default=None,
                   help="restrict to a chunk type (memory, lore, timeline, ...)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--self-test", action="store_true",
                   help="run built-in assertions (no model needed) and exit")
    args = p.parse_args(argv[1:])

    if args.self_test:
        return _self_test()
    if not args.query:
        p.error("a query is required (or use --self-test)")

    root = _find_root(Path.cwd())
    try:
        scored = search_text(root, args.query, scope=args.scope, k=args.k,
                             since_day=args.since_day, owner=args.owner,
                             ftype=args.ftype)
    except Exception as e:
        print(f"memory_search error: {e}")
        return 1
    banner, actor_safe = scope_banner(args.scope, len(scored))
    if args.json:
        print(json.dumps({"scope": args.scope, "actor_safe": actor_safe,
                          "count": len(scored), "results": results_json(scored)},
                         ensure_ascii=False, indent=2))
    else:
        print(banner)
        print(format_results(scored))
    return 0


def _self_test():
    import tempfile

    # Hand-build a tiny index with simple 3-d vectors and known tiers.
    recs = [
        {"id": "1", "path": "Game/gm-secrets.md", "visibility": "secret",
         "owner": None, "type": "gm-secrets", "day": 5, "heading": None,
         "text": "the mayor is a wraith", "vector": [1.0, 0.0, 0.0]},
        {"id": "2", "path": "Cast/vance/profile.md", "visibility": "public",
         "owner": "vance", "type": "profile", "day": None, "heading": "Vance",
         "text": "harbor boss", "vector": [0.9, 0.1, 0.0]},
        {"id": "3", "path": "PLAYER-NOTES.md", "visibility": "player",
         "owner": None, "type": "player-notes", "day": 12, "heading": None,
         "text": "you suspect the docks", "vector": [0.0, 1.0, 0.0]},
    ]
    q = [1.0, 0.0, 0.0]  # closest to the secret, then the public profile

    # gm scope sees everything; top hit is the secret.
    gm = search(None, q, scope="gm", recs=recs)
    assert gm[0][1]["visibility"] == "secret"

    # public scope must NEVER return secret/gm tiers — the firewall.
    pub = search(None, q, scope="public", recs=recs)
    assert all(r["visibility"] in ("player", "public") for _, r in pub), pub
    assert not any(r["visibility"] == "secret" for _, r in pub)

    # player scope is the narrowest.
    pl = search(None, q, scope="player", recs=recs)
    assert {r["visibility"] for _, r in pl} == {"player"}

    # since-day filter drops undated + older chunks.
    recent = search(None, [0.0, 1.0, 0.0], scope="gm", since_day=10, recs=recs)
    assert all(r["day"] is not None and r["day"] >= 10 for _, r in recent)

    # owner filter.
    owned = search(None, q, scope="public", owner="vance", recs=recs)
    assert all(r["owner"] == "vance" for _, r in owned)

    # citation formatting.
    assert "[Day 5]" in _citation(recs[0])

    # scope banner labels actor-safety correctly.
    assert scope_banner("public", 3)[1] is True
    assert scope_banner("player", 1)[1] is True
    assert scope_banner("gm", 5)[1] is False
    assert "GM-ONLY" in scope_banner("gm", 5)[0]

    # stale-index guard: wrong embedder or wrong dimension must raise, not
    # silently rank garbage. A matching index (or empty meta) must pass.
    check_index_compatible({}, "any-model")  # no meta yet → no opinion, OK
    check_index_compatible({"embed_model": "m", "dim": 3}, "m", 3)  # match → OK
    for bad in (lambda: check_index_compatible({"embed_model": "old"}, "new"),
                lambda: check_index_compatible({"embed_model": "m", "dim": 3}, "m", 768)):
        try:
            bad()
            assert False, "expected stale-index guard to raise"
        except RuntimeError:
            pass

    print("memory_search self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
