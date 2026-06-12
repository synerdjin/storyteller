#!/usr/bin/env python3
"""A tiny, dependency-free client for a local Ollama server.

Used by the local-compute tools to get embeddings and short LLM completions from
a model running on the Player's own machine, so the engine spends Claude tokens
only on player-facing prose and live adjudication — not on bookkeeping.

stdlib only (urllib). If the server isn't running, callers get a clear
`LocalUnavailable` and can fall back to Claude or skip the local step.

Quick check (needs Ollama running locally):
    python Tools/local_client.py            # ping the server, list models
"""

import json
import urllib.error
import urllib.request

import local_config


class LocalUnavailable(RuntimeError):
    """The local model server can't be reached or returned an error."""


def _post(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise LocalUnavailable(f"cannot reach local model server at {url}: {e}")
    except Exception as e:
        raise LocalUnavailable(f"local model request failed: {e}")


def embed(texts, cfg=None, root=None):
    """Return a list of embedding vectors, one per input string."""
    cfg = cfg or local_config.load_config(root)
    if isinstance(texts, str):
        texts = [texts]
    url = cfg["host"].rstrip("/") + "/api/embed"
    out = _post(url, {"model": cfg["embed_model"], "input": list(texts)},
                cfg.get("embed_timeout", 60))
    vecs = out.get("embeddings")
    if not vecs or len(vecs) != len(texts):
        raise LocalUnavailable(
            f"embedder returned {len(vecs) if vecs else 0} vectors for "
            f"{len(texts)} inputs (model={cfg['embed_model']})")
    return vecs


def generate(prompt, system=None, cfg=None, root=None, options=None):
    """Return a single (non-streamed) chat completion as text."""
    cfg = cfg or local_config.load_config(root)
    url = cfg["host"].rstrip("/") + "/api/chat"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": cfg["llm_model"], "messages": messages, "stream": False}
    if options:
        payload["options"] = options
    out = _post(url, payload, cfg.get("llm_timeout", 300))
    msg = (out.get("message") or {}).get("content")
    if not msg:
        raise LocalUnavailable("local LLM returned an empty completion")
    return msg


def ping(cfg=None, root=None):
    """Cheap reachability check; returns a status string or raises."""
    cfg = cfg or local_config.load_config(root)
    url = cfg["host"].rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise LocalUnavailable(f"cannot reach {url}: {e}")
    names = [m.get("name") for m in tags.get("models", [])]
    return (f"ok: {cfg['host']} reachable; {len(names)} model(s) installed: "
            f"{', '.join(n for n in names if n) or '(none)'}")


if __name__ == "__main__":
    import sys
    try:
        print(ping())
    except LocalUnavailable as e:
        print(e)
        sys.exit(1)
