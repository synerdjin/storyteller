# Local-compute layer — setup & testing

This is the token-saving tier: a **local embedding index for hybrid semantic
retrieval**, running on your own GPU (an RTX 4070 is plenty). It is **optional and
additive** — the engine runs without it (retrieval falls back to a model-free
lexical search, or you just read the markdown). The point is to spend Claude tokens
on live play and player-facing prose, not on re-feeding accumulated state.

> **Why local embeddings, not Claude's?** Anthropic has no embeddings endpoint, and
> a local embedder keeps GM secrets on your machine.

## What's here

| File | What it is |
|---|---|
| `Tools/local_config.py` | Where the local embedder lives (host + model name). |
| `Tools/local_client.py` | Tiny stdlib client for a local Ollama server. |
| `Tools/memory_index.py` | Builds the semantic index over campaign markdown. |
| `Tools/memory_search.py` | **Hybrid** retrieval (dense + BM25 + RRF), firewall-scoped, with citations. |
| `Game/local-models.json` | Per-campaign model config (edit me). |

## One-time setup (on your machine)

1. Install [Ollama](https://ollama.com) and pull the **embedder** (the default in
   `Game/local-models.json`):
   ```bash
   ollama pull bge-m3                     # embeddings: 1024-dim, MIT, ~1.2 GB VRAM
   ```
   `bge-m3` is the current pick for hybrid retrieval — strong dense recall, and its
   lexical strengths pair naturally with the BM25 half of our search. Prefer a
   smaller/lighter embedder? `nomic-embed-text` (768-dim) or `mxbai-embed-large`
   also work — just `ollama pull` it and set `embed_model` in
   `Game/local-models.json` (the index records the embedder and **rebuilds itself**
   when you change it).

   > No LLM pull is required. `llm_model` in the config is **off the hot path** —
   > it's kept only for the optional, deferred local *reranker* (see "Reranking",
   > below), which is not wired by default.

2. Confirm the engine can reach Ollama:
   ```bash
   python Tools/local_client.py          # prints "ok: ... N model(s) installed"
   ```

## Build & use the index (hybrid search)

```bash
python Tools/memory_index.py             # build / incrementally update the index
python Tools/memory_index.py --rebuild   # force a full re-embed (e.g. after an embedder swap)
python Tools/memory_index.py --stats     # how many chunks, by tier & type

python Tools/memory_search.py "the harbor conspiracy"            # GM scope, hybrid
python Tools/memory_search.py "Club Schwarm" --mode lexical      # exact name, NO model
python Tools/memory_search.py "what does Vance want" --scope public --owner vance
python Tools/memory_search.py "recent betrayals" --since-day 10 --recency --k 5
```

Retrieval is **hybrid by default**: a dense semantic ranking (the query embedded,
cosine over the index) fused with a sparse **BM25** lexical ranking via **Reciprocal
Rank Fusion**, then small, auditable metadata boosts (an owner named in the query;
optionally `--recency`). Modes: `--mode hybrid` (default), `--mode dense` (cosine
only), `--mode lexical` (BM25 only — needs **no model at all**, the graceful
fallback when Ollama is down).

`--scope` is the **secret firewall**: `public` returns only actor-safe chunks
(never secrets or GM working files), so it's safe to feed into an `npc-actor`
briefing. `gm` (default) sees everything.

Re-index at session end / save points (incremental — only changed files re-embed).
The index lives in `Game/.memory-index/` and is gitignored; it rebuilds from the
markdown any time. **After swapping the embedder, run `--rebuild` once** (the tool
also refuses to search an index built by a different embedder, so you can't get
silently-wrong results).

## Reranking (deferred — optional)

`memory_search.maybe_rerank()` is a no-op seam. Ollama has **no native rerank
endpoint**, so a neural reranker is the highest-friction piece and is **not wired**.
If hybrid + boosts ever prove insufficient on a real corpus, fill the seam with a
local cross-encoder — `Qwen3-Reranker-0.6B` via Ollama's `/api/chat` (binary
yes/no), or `bge-reranker-v2-m3` via a llama.cpp `/v1/rerank` server — and set
`rerank_model` in the config.

## Testing without a GPU (these need no Ollama)

```bash
python Tools/local_client.py --self-test
python Tools/memory_index.py --self-test
python Tools/memory_search.py --self-test     # covers BM25, RRF, boosts, firewall
python Tools/memory_index.py --dry-run        # real chunking over your files, no embeds
```

## What still needs YOUR machine to verify (the GPU integration)

1. `python Tools/local_client.py` → server reachable, embedder installed.
2. `python Tools/memory_index.py --rebuild` → builds a real 1024-dim index
   (`--stats`).
3. `python Tools/memory_search.py "<something from your campaign>"` → relevant,
   day-stamped, cited results; an exact-name query surfaces the literal chunk;
   `--scope public` excludes every secret file.
