#!/usr/bin/env python3
"""Configuration for the Storyteller local-compute layer.

The engine's expensive work is Claude (live play, player-facing prose). The
*cheap, high-frequency* work — semantic retrieval, off-screen plot scribing,
triage, summarizing — can run on a small model on the Player's own GPU. This
module is the single place that knows where that local model lives and which
models to use, so the tools (`memory_index`, `memory_search`, `world_scribe`)
never hard-code it.

Resolution order (first non-empty wins), per key:
    1. environment variable
    2. Game/local-models.json in the campaign
    3. built-in defaults below

stdlib only. Importing this never touches the network — it only reads config.
"""

import json
import os
import sys
from pathlib import Path

# Built-in defaults. Tuned for an RTX 4070 (12 GB). The ONLY model on the hot
# path now is the embedder: it powers hybrid semantic retrieval (memory_*.py).
# The generative local tier (the qwen plot-scribe/critic/reflector) has been
# RETIRED — routine world moves are templated deterministically (world_scribe.py)
# and the rest escalates to Claude. `llm_model` is therefore OFF the per-post hot
# path; it is used only by two OPTIONAL, low-frequency paths that both degrade
# gracefully when no model is pulled: world_health.py's tone/compliance read, and
# the deferred reranker seam (memory_search.maybe_rerank). Override per-campaign
# in Game/local-models.json or via the env vars below.
DEFAULTS = {
    "host": "http://localhost:11434",     # Ollama's default address
    "embed_model": "bge-m3",              # 1024-dim, MIT, strong hybrid retrieval (~1.2 GB)
    "llm_model": "qwen3:14b",             # OFF the hot path — optional (world_health, reranker)
    "embed_timeout": 60,
    "llm_timeout": 300,
}

_ENV = {
    "host": "STORYTELLER_OLLAMA_HOST",
    "embed_model": "STORYTELLER_EMBED_MODEL",
    "llm_model": "STORYTELLER_LLM_MODEL",
}


def enable_utf8_output():
    """Make stdout/stderr UTF-8 so printing campaign text never crashes.

    Campaign markdown is full of em-dashes, arrows, and emoji; on Windows the
    console defaults to a legacy code page (cp1252) that can't encode them,
    so a plain `print()` of a search result raises UnicodeEncodeError. Every
    CLI entry point calls this first. Best-effort: silently no-ops if the
    streams can't be reconfigured (e.g. when piped through a wrapper).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfig = getattr(stream, "reconfigure", None)
        if reconfig is not None:
            try:
                reconfig(encoding="utf-8", errors="replace")
            except Exception:
                pass


def load_config(root=None):
    """Return the merged config dict (defaults < file < env)."""
    cfg = dict(DEFAULTS)
    if root is not None:
        path = Path(root) / "Game" / "local-models.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if k in cfg and v not in (None, ""):
                        cfg[k] = v
            except Exception:
                pass  # never crash play over a malformed config; use defaults
    for k, env in _ENV.items():
        v = os.environ.get(env)
        if v:
            cfg[k] = v
    return cfg


if __name__ == "__main__":
    root = Path.cwd()
    for cand in [root, *root.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            root = cand
            break
    print(json.dumps(load_config(root), indent=2))
    sys.exit(0)
