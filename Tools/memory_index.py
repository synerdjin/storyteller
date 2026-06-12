#!/usr/bin/env python3
"""Build a local semantic-search index over the campaign's markdown.

As a campaign grows, the dominant cost of every Claude call is re-feeding
accumulated state (timeline, memories, lore). This tool embeds the campaign's
markdown — chunked into day-stamped semantic units — into a small on-disk vector
index, so the GM and subagents can later retrieve the *relevant* handful of
chunks (via memory_search.py) instead of dumping whole files into context.

Embeddings run on a LOCAL model (see local_config.py / Ollama) — Anthropic has
no embeddings endpoint, and a local model keeps GM secrets on the Player's
machine. The index is a rebuildable artifact: markdown stays the single source
of truth, so the index is gitignored and can be regenerated any time.

Every chunk is tagged with a VISIBILITY tier so retrieval can respect the
engine's secret firewall:
    secret  — gm-secrets, world-state, developments, secrets/drives/sheet
    gm      — GM working files (timeline, threads, current-scene, campaign)
    public  — actor-safe (profile, memory, world lore, PC backstory)
    player  — player-facing (PLAYER-NOTES, Story/ chapters)

Usage:
    python Tools/memory_index.py              # incremental: (re)index changed files
    python Tools/memory_index.py --rebuild    # re-embed everything from scratch
    python Tools/memory_index.py --dry-run    # chunk & report, embed/write NOTHING
                                              #   (runs WITHOUT a local model)
    python Tools/memory_index.py --stats      # summarize the existing index
    python Tools/memory_index.py --self-test  # built-in assertions (no model needed)
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import local_config

try:
    import local_client  # only needed when actually embedding
except Exception:  # pragma: no cover
    local_client = None

# Target chunk size in characters (~roughly 300-600 tokens). Day-stamped log
# entries and headed sections are kept whole when they fit; longer bodies split.
MAX_CHARS = 1400
HARD_CAP = 2400
EMBED_BATCH = 64

INDEX_DIR = ("Game", ".memory-index")

DAY_RE = re.compile(r"\[Day\s+(\d+)")
DAY_LINE_RE = re.compile(r"^\s*#{0,6}\s*\[Day\s+\d+")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


# --------------------------------------------------------------------------- #
# Visibility / ownership classification, by path. This is the firewall.
# Returns (visibility, owner, type) or (None, None, None) to skip the file.
# --------------------------------------------------------------------------- #


def classify(rel):
    parts = rel.split("/")
    fn = parts[-1]

    if rel == "PLAYER-NOTES.md":
        return ("player", None, "player-notes")

    if parts[0] == "Story" and fn.startswith("chapter"):
        return ("player", None, "chapter")

    if parts[0] == "Character":
        if fn == "backstory.md":
            return ("public", "PC", "backstory")
        return (None, None, None)  # sheet.md is mechanical — skip

    if parts[0] == "Cast" and len(parts) >= 3 and not parts[1].startswith("_"):
        owner = parts[1]
        m = {
            "profile.md": ("public", "profile"),
            "memory.md": ("public", "memory"),
            "secrets.md": ("secret", "secrets"),
            "drives.md": ("secret", "drives"),
            "sheet.md": ("secret", "sheet"),
        }.get(fn)
        return (m[0], owner, m[1]) if m else (None, None, None)

    if parts[0] == "Game":
        m = {
            "gm-secrets.md": ("secret", "gm-secrets"),
            "world-state.md": ("secret", "world-state"),
            "developments.md": ("secret", "developments"),
            "world.md": ("public", "lore"),
            "campaign.md": ("gm", "campaign"),
            "threads.md": ("gm", "threads"),
            "timeline.md": ("gm", "timeline"),
            "current-scene.md": ("gm", "scene"),
        }.get(fn)
        return (m[0], None, m[1]) if m else (None, None, None)

    return (None, None, None)


def discover_files(root):
    """Yield (path, rel, visibility, owner, type) for every indexable file."""
    root = Path(root)
    candidates = []
    for pat in ("PLAYER-NOTES.md", "Story/*.md", "Character/*.md",
                "Cast/*/*.md", "Game/*.md"):
        candidates.extend(root.glob(pat))
    out = []
    for p in sorted(set(candidates)):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        vis, owner, ftype = classify(rel)
        if ftype is None:
            continue
        out.append((p, rel, vis, owner, ftype))
    return out


# --------------------------------------------------------------------------- #
# Chunking — by day-stamped entry, else by heading, else by size.
# --------------------------------------------------------------------------- #


def _chunk_by_day(lines):
    chunks, cur, cur_day, cur_head = [], [], None, None

    def flush():
        if cur:
            txt = "\n".join(cur).strip()
            if txt:
                chunks.append({"heading": cur_head, "day": cur_day, "text": txt})

    for ln in lines:
        if DAY_LINE_RE.match(ln):
            flush()
            cur = [ln]
            m = DAY_RE.search(ln)
            cur_day = int(m.group(1)) if m else None
            cur_head = ln.strip().lstrip("#").strip()
        else:
            cur.append(ln)
    flush()
    return chunks


def _chunk_by_heading(lines):
    chunks, cur, cur_head = [], [], None

    def flush():
        if cur:
            txt = "\n".join(cur).strip()
            if txt:
                m = DAY_RE.search(txt)
                chunks.append({"heading": cur_head,
                               "day": int(m.group(1)) if m else None,
                               "text": txt})

    for ln in lines:
        m = HEADING_RE.match(ln)
        if m:
            flush()
            cur = [ln]
            cur_head = m.group(2).strip()
        else:
            cur.append(ln)
    flush()
    return chunks


def _hard_split(p):
    """Split one over-long paragraph into <=MAX_CHARS pieces."""
    out, cur = [], ""
    for s in re.split(r"(?<=[.!?])\s+", p):
        if len(s) > MAX_CHARS:
            for i in range(0, len(s), MAX_CHARS):
                out.append(s[i:i + MAX_CHARS])
            continue
        if cur and len(cur) + len(s) + 1 > MAX_CHARS:
            out.append(cur)
            cur = s
        else:
            cur = (cur + " " + s) if cur else s
    if cur:
        out.append(cur)
    return out


def _split_by_size(body):
    """Split a long body into <=MAX_CHARS string pieces on paragraph breaks."""
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", body.strip()):
        para = para.strip()
        if not para:
            continue
        if len(para) > HARD_CAP:
            for piece in _hard_split(para):
                out.append(piece)
            continue
        if cur and len(cur) + len(para) + 2 > MAX_CHARS:
            out.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur:
        out.append(cur)
    return out


def chunk_file(rel, text, ftype):
    lines = text.splitlines()
    day_markers = sum(1 for ln in lines if DAY_LINE_RE.match(ln))
    if ftype in ("timeline", "memory", "developments") or day_markers >= 2:
        raw = _chunk_by_day(lines)
    elif any(HEADING_RE.match(ln) for ln in lines):
        raw = _chunk_by_heading(lines)
    else:
        raw = [{"heading": None, "day": None, "text": text.strip()}]

    final = []
    for c in raw:
        body = (c["text"] or "").strip()
        if not body:
            continue
        if len(body) <= HARD_CAP:
            final.append(c)
        else:
            for piece in _split_by_size(body):
                final.append({"heading": c["heading"], "day": c["day"],
                              "text": piece})
    return final


def _chunk_id(rel, ordinal, text):
    h = hashlib.sha1(f"{rel}|{ordinal}|{text}".encode("utf-8")).hexdigest()
    return h[:16]


def _file_sha(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _embed_batched(texts, embed_fn):
    vecs = []
    for i in range(0, len(texts), EMBED_BATCH):
        vecs.extend(embed_fn(texts[i:i + EMBED_BATCH]))
    return vecs


# --------------------------------------------------------------------------- #
# Build (incremental) and report
# --------------------------------------------------------------------------- #


def build(root, embed_fn=None, rebuild=False, dry_run=False, verbose=True):
    root = Path(root)
    cfg = local_config.load_config(root)
    if embed_fn is None and not dry_run:
        if local_client is None:
            raise RuntimeError("local_client unavailable; cannot embed")
        embed_fn = lambda batch: local_client.embed(batch, cfg=cfg)

    idx_dir = root.joinpath(*INDEX_DIR)
    meta_path = idx_dir / "meta.json"
    index_path = idx_dir / "index.jsonl"

    files = discover_files(root)
    cur_sha = {rel: _file_sha(p) for p, rel, _, _, _ in files}

    old_meta, old_by_path = {}, {}
    if not rebuild and meta_path.exists() and index_path.exists():
        try:
            old_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if old_meta.get("embed_model") == cfg["embed_model"]:
                for line in index_path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        rec = json.loads(line)
                        old_by_path.setdefault(rec["path"], []).append(rec)
            else:
                old_meta = {}  # embedder changed → vectors incomparable, rebuild
        except Exception:
            old_meta, old_by_path = {}, {}
    old_files = old_meta.get("files") or {}

    kept, to_embed = [], []
    stats = {"files": len(files), "reused_files": 0, "rechunked_files": 0,
             "new_chunks": 0, "reused_chunks": 0}

    for p, rel, vis, owner, ftype in files:
        if (not rebuild) and old_files.get(rel) == cur_sha[rel] \
                and rel in old_by_path:
            kept.extend(old_by_path[rel])
            stats["reused_files"] += 1
            stats["reused_chunks"] += len(old_by_path[rel])
            continue
        stats["rechunked_files"] += 1
        for i, c in enumerate(chunk_file(rel, p.read_text(encoding="utf-8"), ftype)):
            to_embed.append({
                "id": _chunk_id(rel, i, c["text"]),
                "path": rel, "visibility": vis, "owner": owner, "type": ftype,
                "day": c["day"], "heading": c["heading"], "text": c["text"],
            })
    stats["new_chunks"] = len(to_embed)

    if dry_run:
        if verbose:
            _print_report(stats, kept + to_embed)
            print("  (--dry-run: nothing embedded or written.)")
        return stats

    if to_embed:
        vecs = _embed_batched([r["text"] for r in to_embed], embed_fn)
        for r, v in zip(to_embed, vecs):
            r["vector"] = v

    all_recs = kept + to_embed
    idx_dir.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", encoding="utf-8") as f:
        for r in all_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    dim = next((len(r["vector"]) for r in all_recs if "vector" in r), None)
    meta_path.write_text(json.dumps({
        "embed_model": cfg["embed_model"], "dim": dim,
        "chunks": len(all_recs), "files": cur_sha,
    }, indent=2), encoding="utf-8")

    if verbose:
        print(f"Indexed {len(all_recs)} chunks from {len(files)} files "
              f"({stats['reused_files']} reused, {stats['rechunked_files']} "
              f"(re)chunked, {stats['new_chunks']} chunks embedded).")
    return stats


def _print_report(stats, recs):
    by_vis, by_type = {}, {}
    for r in recs:
        by_vis[r["visibility"]] = by_vis.get(r["visibility"], 0) + 1
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    print(f"{len(recs)} chunks across {stats['files']} files.")
    print("  by visibility: " + ", ".join(
        f"{k}={v}" for k, v in sorted(by_vis.items())))
    print("  by type: " + ", ".join(
        f"{k}={v}" for k, v in sorted(by_type.items())))


def stats_existing(root):
    index_path = Path(root).joinpath(*INDEX_DIR, "index.jsonl")
    if not index_path.exists():
        print("No index yet. Run `python Tools/memory_index.py` to build one.")
        return 1
    recs = [json.loads(l) for l in index_path.read_text(encoding="utf-8")
            .splitlines() if l.strip()]
    _print_report({"files": len({r["path"] for r in recs})}, recs)
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _find_root(start):
    cur = Path(start).resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return Path(start)


def main(argv):
    local_config.enable_utf8_output()
    p = argparse.ArgumentParser(description="Build the local semantic-memory index.")
    p.add_argument("--rebuild", action="store_true",
                   help="re-embed everything (ignore the existing index)")
    p.add_argument("--dry-run", action="store_true",
                   help="chunk & report only; embed and write nothing (no model)")
    p.add_argument("--stats", action="store_true",
                   help="summarize the existing index and exit")
    p.add_argument("--self-test", action="store_true",
                   help="run built-in assertions (no model needed) and exit")
    args = p.parse_args(argv[1:])

    if args.self_test:
        return _self_test()

    root = _find_root(Path.cwd())
    if args.stats:
        return stats_existing(root)
    try:
        build(root, rebuild=args.rebuild, dry_run=args.dry_run)
        return 0
    except Exception as e:
        print(f"memory_index error: {e}")
        return 1


# --------------------------------------------------------------------------- #
# Built-in self-test (uses a fake embedder — no Ollama required)
# --------------------------------------------------------------------------- #


def _fake_embed(texts):
    out = []
    for t in texts:
        d = hashlib.sha1(t.encode("utf-8")).digest()
        out.append([b / 255.0 for b in d[:8]])
    return out


def _self_test():
    import tempfile

    # --- classification / firewall ---
    assert classify("Game/gm-secrets.md") == ("secret", None, "gm-secrets")
    assert classify("Cast/vance/secrets.md") == ("secret", "vance", "secrets")
    assert classify("Cast/vance/profile.md") == ("public", "vance", "profile")
    assert classify("Game/timeline.md") == ("gm", None, "timeline")
    assert classify("PLAYER-NOTES.md") == ("player", None, "player-notes")
    assert classify("Cast/_template/profile.md") == (None, None, None)
    assert classify("Game/system.md") == (None, None, None)

    # --- day-stamped chunking ---
    log = ("preamble line\n\n"
           "[Day 1 — dawn] first thing happened.\n more of day 1\n\n"
           "[Day 4 — dusk] later thing happened.\n")
    cs = chunk_file("Game/timeline.md", log, "timeline")
    days = [c["day"] for c in cs]
    assert 1 in days and 4 in days, days
    assert any("preamble" in c["text"] for c in cs)

    # --- heading chunking + day extraction from body ---
    doc = "# Title\nintro\n\n## The Harbor [Day 2]\ndocks and tariffs\n"
    cs2 = chunk_file("Game/world.md", doc, "lore")
    assert any(c["heading"] == "The Harbor [Day 2]" and c["day"] == 2 for c in cs2)

    # --- end-to-end build + incremental reuse, with a fake embedder ---
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "CLAUDE.md").write_text("x", encoding="utf-8")
        (root / "Game").mkdir()
        (root / "Game" / "timeline.md").write_text(log, encoding="utf-8")
        (root / "Game" / "gm-secrets.md").write_text(
            "# secrets\nThe mayor is a wraith.\n", encoding="utf-8")
        (root / "Cast" / "vance").mkdir(parents=True)
        (root / "Cast" / "vance" / "profile.md").write_text(
            "# Vance\nA harbor boss who talks fast.\n", encoding="utf-8")

        s1 = build(root, embed_fn=_fake_embed, verbose=False)
        assert s1["rechunked_files"] == 3, s1
        idx = (root / "Game" / ".memory-index" / "index.jsonl")
        recs = [json.loads(l) for l in idx.read_text().splitlines() if l.strip()]
        assert all("vector" in r and len(r["vector"]) == 8 for r in recs)
        vis = {r["visibility"] for r in recs}
        assert {"secret", "public", "gm"} <= vis, vis

        # second build: nothing changed → all files reused, nothing re-embedded
        s2 = build(root, embed_fn=_fake_embed, verbose=False)
        assert s2["reused_files"] == 3 and s2["new_chunks"] == 0, s2

        # touch one file → only it re-chunks
        (root / "Cast" / "vance" / "profile.md").write_text(
            "# Vance\nNow he runs the customs house too.\n", encoding="utf-8")
        s3 = build(root, embed_fn=_fake_embed, verbose=False)
        assert s3["rechunked_files"] == 1 and s3["reused_files"] == 2, s3

    print("memory_index self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
