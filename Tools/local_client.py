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
import time
import urllib.error
import urllib.request

import local_config


class LocalUnavailable(RuntimeError):
    """The local model server can't be reached or returned an error."""


# Ollama can briefly return these while it loads or swaps a model into VRAM —
# observed: a 400 on /api/embed when the embedder reloads behind a resident 14B
# model on a 12 GB card. They clear on a quick retry. A genuine error (bad
# request, server down) just fails again and surfaces the same way. We do NOT
# retry 404 (model-not-found — not transient) or auth errors, and a refused
# connection raises immediately so the caller can fall back to Claude fast.
_TRANSIENT_HTTP = frozenset({400, 408, 409, 425, 429, 500, 502, 503, 504})
_RETRIES = 2          # extra attempts beyond the first
_RETRY_WAIT = 1.5     # seconds between attempts


def _post(url, payload, timeout, _sleep=time.sleep):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    for attempt in range(_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:  # subclass of URLError — catch first
            if e.code in _TRANSIENT_HTTP and attempt < _RETRIES:
                _sleep(_RETRY_WAIT)
                continue
            raise LocalUnavailable(
                f"cannot reach local model server at {url}: {e}")
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


def _self_test():
    """Lock down _post's retry policy with a fake urlopen (no server needed)."""
    calls = {"n": 0}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true}'

    def fake_urlopen(fail_times, code):
        def fake(req, timeout=None):
            if calls["n"] < fail_times:
                calls["n"] += 1
                raise urllib.error.HTTPError("http://x", code, "err", {}, None)
            return _Resp()
        return fake

    noop = lambda *_a, **_k: None
    orig = urllib.request.urlopen
    try:
        # A transient code that clears: fails twice, then the retry succeeds.
        calls["n"] = 0
        urllib.request.urlopen = fake_urlopen(2, 503)
        assert _post("http://x", {}, 5, _sleep=noop) == {"ok": True}
        assert calls["n"] == 2

        # A persistent transient code gives up after exactly _RETRIES+1 tries.
        calls["n"] = 0
        urllib.request.urlopen = fake_urlopen(99, 400)
        try:
            _post("http://x", {}, 5, _sleep=noop)
            assert False, "expected LocalUnavailable after retries exhausted"
        except LocalUnavailable:
            pass
        assert calls["n"] == _RETRIES + 1

        # A non-transient code (404 model-not-found) raises on the first try.
        calls["n"] = 0
        urllib.request.urlopen = fake_urlopen(99, 404)
        try:
            _post("http://x", {}, 5, _sleep=noop)
            assert False, "expected LocalUnavailable with no retry"
        except LocalUnavailable:
            pass
        assert calls["n"] == 1
    finally:
        urllib.request.urlopen = orig

    print("local_client self-test: OK")
    return 0


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv[1:]:
        sys.exit(_self_test())
    try:
        print(ping())
    except LocalUnavailable as e:
        print(e)
        sys.exit(1)
