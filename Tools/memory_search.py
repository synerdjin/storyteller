#!/usr/bin/env python3
"""Semantic search over the campaign's local memory index.

Returns the most relevant chunks from the index built by memory_index.py — each
with a source CITATION (path + Day N) so retrieved facts have real provenance the
GM can verify, instead of being recalled from a fallible model memory.

Retrieval is **hybrid** by default: it fuses a dense semantic ranking (the query
embedded by the local model, cosine over the index) with a sparse lexical ranking
(BM25 over the chunk text) via Reciprocal Rank Fusion, then applies small,
auditable metadata boosts. Dense alone misses exact proper nouns ("Club Schwarm",
"Sabine"); BM25 nails them. The two scales (BM25 0-20+, cosine 0-1) are never
compared directly — RRF fuses by *rank*, so no normalization is needed.

    mode=hybrid  (default) dense + BM25, fused by RRF, then boosts
    mode=dense             cosine only (the original behavior)
    mode=lexical           BM25 only — needs NO local model at all

The `--scope` flag enforces the engine's secret firewall:
    gm      — everything (default; for the GM and the secret-aware world tools)
    public  — actor-safe only (player + public tiers): what you may put in an
              npc-actor briefing. EXCLUDES every secret and GM-working file.
    player  — player-facing only (PLAYER-NOTES, Story/ chapters).

Usage:
    python Tools/memory_search.py "the harbor conspiracy"
    python Tools/memory_search.py "what does Vance want" --scope public --owner vance
    python Tools/memory_search.py "recent betrayals" --since-day 10 --k 5 --recency
    python Tools/memory_search.py "Club Schwarm" --mode lexical   # exact name, no model
    python Tools/memory_search.py "..." --json        # machine-readable output
    python Tools/memory_search.py --self-test         # assertions (no model)
"""

import argparse
import json
import math
import re
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

# --- Hybrid-search tuning (all on the RRF scale, so they stay auditable) ----- #
# A single top-rank RRF contribution is 1/RRF_K ≈ 0.0167; a chunk topping BOTH
# the dense and lexical lists scores ≈ 0.0333. The boosts below are sized in
# those units: an owner-boost is worth ~one rank, so it can overcome a one-rank
# gap (by design — an entity query should prefer that entity's files) but never
# overturns a strong dual match against an unrelated chunk.
RRF_K = 60                  # standard RRF constant (rank-fusion smoothing)
BM25_K1 = 1.5               # term-frequency saturation
BM25_B = 0.75              # length normalization
OWNER_BOOST = 1.0 / RRF_K   # chunk's owner is named in the query → ~one rank up
RECENCY_WEIGHT = 0.5 / RRF_K  # opt-in (--recency): newest day gets up to this much

# Lexical tokenization. A tiny, dependency-free stopword set — enough to keep
# BM25 focused on content words (names, places, nouns) without a real NLP stack.
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an the of to in on at for and or is are was were be been being it its "
    "this that these those with as by from into out up down over under i you "
    "he she they we him her them his their our your my me do does did has have "
    "had not no but if then than so what which who whom whose when where why "
    "how all any both each few more most other some such only own same too very "
    "can will just about".split())


def tokenize(text):
    """Lowercase content tokens for BM25 (stopwords and 1-char tokens dropped)."""
    return [t for t in _TOKEN_RE.findall(text.lower())
            if len(t) > 1 and t not in _STOPWORDS]


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


def _passes(r, allow, since_day, owner, ftype):
    """Shared firewall + metadata filter (vector-agnostic — lexical needs none)."""
    if r.get("visibility") not in allow:
        return False
    if since_day is not None and (r.get("day") is None or r["day"] < since_day):
        return False
    if owner and r.get("owner") != owner:
        return False
    if ftype and r.get("type") != ftype:
        return False
    return True


def bm25_scores(query_tokens, recs, k1=BM25_K1, b=BM25_B):
    """Classic BM25 over the candidate chunks' text. Pure Python, computed at
    query time (a campaign corpus is small enough that precomputing is needless).
    Returns {chunk_id: score} for chunks with a positive score only."""
    docs = [(r.get("id"), tokenize(r.get("text", ""))) for r in recs]
    n = len(docs)
    if n == 0:
        return {}
    avgdl = sum(len(d) for _, d in docs) / n or 1.0
    df = {}
    for _, d in docs:
        for term in set(d):
            df[term] = df.get(term, 0) + 1
    qterms = set(query_tokens)
    scores = {}
    for cid, d in docs:
        dl = len(d)
        if dl == 0 or cid is None:
            continue
        tf = {}
        for term in d:
            if term in qterms:
                tf[term] = tf.get(term, 0) + 1
        s = 0.0
        for term, f in tf.items():
            nq = df.get(term, 0)
            idf = math.log(1 + (n - nq + 0.5) / (nq + 0.5))
            s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        if s > 0:
            scores[cid] = s
    return scores


def rrf_fuse(ranked_lists, k=RRF_K):
    """Reciprocal Rank Fusion: fuse ranked id-lists by rank, not score, so the
    incomparable BM25 and cosine scales never need normalizing."""
    fused = {}
    for ranked in ranked_lists:
        for rank, cid in enumerate(ranked):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)
    return fused


def detect_query_owners(query_tokens, recs):
    """Which indexed owners (Cast folder names / 'PC') are named in the query."""
    owners = {r.get("owner") for r in recs if r.get("owner")}
    qt = set(query_tokens)
    return {o for o in owners if o.lower() in qt}


def search(root, query_vec, scope="gm", k=8, since_day=None, owner=None,
           ftype=None, recs=None):
    """Dense-only cosine search (the original behavior; kept for back-compat)."""
    allow = SCOPES.get(scope, SCOPES["gm"])
    recs = load_index(root) if recs is None else recs
    scored = []
    for r in recs:
        if not _passes(r, allow, since_day, owner, ftype):
            continue
        if "vector" not in r:
            continue
        scored.append((cosine(query_vec, r["vector"]), r))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def maybe_rerank(scored, query, cfg):
    """Optional reranker seam — DEFERRED, a no-op today.

    Returns `scored` unchanged unless a `rerank_model` is configured (it isn't by
    default). A later implementation could re-order the top candidates with a
    local cross-encoder — Qwen3-Reranker-0.6B via Ollama's /api/chat (binary
    yes/no), or bge-reranker-v2-m3 via a llama.cpp /v1/rerank endpoint. Add only
    if hybrid + boosts prove insufficient on a real corpus."""
    if not cfg or not cfg.get("rerank_model"):
        return scored
    return scored  # placeholder: real reranking intentionally not wired yet


def search_hybrid(root, query, query_vec, scope="gm", k=8, since_day=None,
                  owner=None, ftype=None, recs=None, mode="hybrid",
                  recency=False, cfg=None):
    """Fuse dense + lexical rankings (RRF) and apply metadata boosts.

    `query_vec` may be None when mode == 'lexical' (no model needed). Returns the
    same (score, record) shape as search(), with score on the RRF scale."""
    allow = SCOPES.get(scope, SCOPES["gm"])
    recs = load_index(root) if recs is None else recs
    cand = [r for r in recs if _passes(r, allow, since_day, owner, ftype)]
    if not cand:
        return []
    by_id = {r.get("id"): r for r in cand if r.get("id") is not None}
    qtokens = tokenize(query)

    ranked_lists = []
    if mode in ("hybrid", "dense") and query_vec is not None:
        dense = sorted((r for r in cand if "vector" in r),
                       key=lambda r: -cosine(query_vec, r["vector"]))
        ranked_lists.append([r.get("id") for r in dense if r.get("id") is not None])
    if mode in ("hybrid", "lexical"):
        lex = bm25_scores(qtokens, cand)
        ranked_lists.append(
            [cid for cid, _ in sorted(lex.items(), key=lambda x: -x[1])])

    fused = rrf_fuse([rl for rl in ranked_lists if rl])

    # Deterministic, auditable metadata boosts on the fused score.
    boost_owners = detect_query_owners(qtokens, cand)
    days = [r["day"] for r in cand if r.get("day") is not None]
    dmin, dmax = (min(days), max(days)) if days else (None, None)
    for cid, r in by_id.items():
        if cid not in fused:
            continue
        if r.get("owner") and r["owner"] in boost_owners:
            fused[cid] += OWNER_BOOST
        if recency and r.get("day") is not None and dmax is not None and dmax > dmin:
            fused[cid] += RECENCY_WEIGHT * (r["day"] - dmin) / (dmax - dmin)

    ranked = sorted(fused.items(), key=lambda x: -x[1])
    scored = [(score, by_id[cid]) for cid, score in ranked if cid in by_id][:k]
    return maybe_rerank(scored, query, cfg)


def search_text(root, query, scope="gm", k=8, since_day=None, owner=None,
                ftype=None, cfg=None, mode="hybrid", recency=False):
    """Convenience: run a search for a text query.

    Hybrid (default) and dense modes embed `query` with the local model; lexical
    mode needs no model at all. The result is the (score, record) list."""
    cfg = cfg or local_config.load_config(root)
    recs = load_index(root)
    vec = None
    if mode in ("hybrid", "dense"):
        if local_client is None:
            raise RuntimeError("local_client unavailable; cannot embed query "
                               "(use --mode lexical for a model-free search)")
        meta = load_meta(root)
        check_index_compatible(meta, cfg["embed_model"])      # fail fast on model swap
        vec = local_client.embed([query], cfg=cfg)[0]
        check_index_compatible(meta, cfg["embed_model"], len(vec))  # and on dim
    if mode == "dense":
        return search(root, vec, scope=scope, k=k, since_day=since_day,
                      owner=owner, ftype=ftype, recs=recs)
    return search_hybrid(root, query, vec, scope=scope, k=k, since_day=since_day,
                         owner=owner, ftype=ftype, recs=recs, mode=mode,
                         recency=recency, cfg=cfg)


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
    p.add_argument("--mode", choices=("hybrid", "dense", "lexical"),
                   default="hybrid",
                   help="retrieval mode (default hybrid = dense+BM25 via RRF; "
                        "lexical needs no local model)")
    p.add_argument("--recency", action="store_true",
                   help="gently boost more recent (higher-day) chunks")
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
                             ftype=args.ftype, mode=args.mode, recency=args.recency)
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

    # --- hybrid layer: tokenize, BM25, RRF, owner detection, fusion ---
    assert tokenize("The Harbor boss, Vance!") == ["harbor", "boss", "vance"]

    # BM25 ranks the doc containing the query term; absent term scores nothing.
    bm = bm25_scores(["harbor"], recs)
    assert recs[1]["id"] in bm and recs[0]["id"] not in bm, bm

    # RRF rewards agreement across lists and is order-correct.
    fused = rrf_fuse([["b", "a"], ["a", "c"]])
    assert fused["a"] == 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 0)
    assert max(fused, key=fused.get) == "a"

    # Owners named in the query are detected (case-insensitive).
    assert detect_query_owners(tokenize("what does Vance want"), recs) == {"vance"}

    # Hybrid: an exact-name lexical hit surfaces a chunk pure dense would rank
    # lower, and the firewall still holds under fusion.
    hq = [0.0, 0.0, 1.0]  # dense-nearest is the player-notes chunk (rec 3)
    hy = search_hybrid(None, "harbor boss vance", hq, scope="gm", recs=recs)
    ids = [r["id"] for _, r in hy]
    assert recs[1]["id"] in ids, "lexical+owner boost must surface the harbor chunk"

    pub = search_hybrid(None, "the mayor wraith", [1.0, 0.0, 0.0],
                        scope="public", recs=recs)
    assert all(r["visibility"] in ("player", "public") for _, r in pub), pub

    # Lexical-only mode needs no vector at all.
    lex = search_hybrid(None, "harbor", None, scope="gm", mode="lexical", recs=recs)
    assert recs[1]["id"] in [r["id"] for _, r in lex]

    # The deferred reranker seam is a no-op without a configured model.
    assert maybe_rerank(hy, "x", {}) == hy
    assert maybe_rerank(hy, "x", {"rerank_model": ""}) == hy

    print("memory_search self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
