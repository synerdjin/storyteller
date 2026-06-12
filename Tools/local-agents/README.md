# Local-compute layer — setup & testing

This is the token-saving tier from the plan: a local embedding index for semantic
retrieval, plus an optional local plot-scribe + critic, all running on your own
GPU (an RTX 4070 is plenty). It is **optional and additive** — the engine runs
exactly as before without it. The point is to spend Claude tokens only on live
play and player-facing prose, and push retrieval, off-screen plot-scribing, and
triage onto a local model.

> **Why local, not Claude embeddings?** Anthropic has no embeddings endpoint, and
> a local embedder keeps GM secrets on your machine.

## What's here

| File | What it is |
|---|---|
| `Tools/local_config.py` | Where the local models live (host + model names). |
| `Tools/local_client.py` | Tiny stdlib client for a local Ollama server. |
| `Tools/memory_index.py` | Builds the semantic index over campaign markdown. |
| `Tools/memory_search.py` | Retrieves relevant chunks, firewall-scoped, with citations. |
| `Tools/world_scribe.py` | Local plot-scribe + critic → `Game/developments.md`. |
| `Tools/local-agents/plot-scribe.md`, `critic.md` | The local models' system prompts. |
| `Game/local-models.json` | Per-campaign model config (edit me). |
| `Game/cost-ledger.md` | Visible record of what ran locally vs on Claude. |

## One-time setup (on your machine)

1. Install [Ollama](https://ollama.com) and pull the two models (defaults in
   `Game/local-models.json`):
   ```bash
   ollama pull nomic-embed-text          # embeddings (~0.3 GB)
   ollama pull qwen3:14b                  # plot/critic scribe (~9 GB at Q4)
   ```
   On a 12 GB 4070 these coexist comfortably (verified: ~9.3 GB model + 0.3 GB
   embedder, ~60 tok/s warm). Qwen3-14B is the current pick for structured
   scribing — strong, reliable JSON/tool output. If VRAM is tight, swap the LLM
   for `llama3.1:8b` in `Game/local-models.json`. Prefer a different embedder?
   `bge-m3` or `mxbai-embed-large` also work — just `ollama pull` it and set
   `embed_model`.

2. Confirm the engine can reach Ollama:
   ```bash
   python Tools/local_client.py          # prints "ok: ... N model(s) installed"
   ```

## Build & use the index

```bash
python Tools/memory_index.py             # build / incrementally update the index
python Tools/memory_index.py --stats     # how many chunks, by tier & type
python Tools/memory_search.py "the harbor conspiracy"            # GM scope (all)
python Tools/memory_search.py "what does Vance want" --scope public --owner vance
python Tools/memory_search.py "recent betrayals" --since-day 10 --k 5 --json
```

`--scope` is the **secret firewall**: `public` returns only actor-safe chunks
(never secrets or GM working files), so it's safe to feed into an `npc-actor`
briefing. `gm` (default) sees everything.

Re-index at session end / save points (it's incremental — only changed files are
re-embedded). The index lives in `Game/.memory-index/` and is gitignored; it
rebuilds from the markdown any time.

## Local plot-scribe + critic

After a world tick writes its queue, scribe the routine moves locally instead of
spending Opus:

```bash
python Tools/world_tick.py               # metronome selects who moved
python Tools/world_scribe.py --dry-run   # SHOW the prompts it would send (no model)
python Tools/world_scribe.py             # scribe → Game/developments.md (needs Ollama)
```

The critic flags pivotal beats `Escalate: claude` in `developments.md` — for
those, run Claude's `world-director` as usual; the local model never resolves a
planned reveal on its own.

## Testing without a GPU (these need no Ollama)

```bash
python Tools/local_client.py --self-test
python Tools/memory_index.py --self-test
python Tools/memory_search.py --self-test
python Tools/world_scribe.py --self-test
python Tools/memory_index.py --dry-run     # real chunking over your files, no embeds
python Tools/world_scribe.py --dry-run     # real prompts, no model calls
```

## What still needs YOUR machine to verify (the GPU integration)

1. `python Tools/local_client.py` → server reachable, models installed.
2. `python Tools/memory_index.py` → builds a real index (check `--stats`).
3. `python Tools/memory_search.py "<something from your campaign>"` → relevant,
   day-stamped, cited results; `--scope public` excludes every secret file.
4. `python Tools/world_scribe.py` after a tick → a well-formed development entry,
   pivotal ones flagged for escalation.
5. Compare a session's Claude token total against before — log it in
   `Game/cost-ledger.md`.
