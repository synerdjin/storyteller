#!/usr/bin/env python3
"""Firewall-safe pipeline for actor memory writes and briefing validation.

Engine v2.11.0 — Part A of the firewall-safe actor pipeline.

Promotes the secret-fingerprint logic from social.py into a single shared
module, then extends it for the per-post use case:

  - `append_observation` is the *only* sanctioned write path into the
    "What I've learned about others" section of a Cast/*/memory.md. It
    runs is_safe() and refuses anything that echoes a secret.

  - `--scan` runs the firewall check standalone after each director pass
    (faster feedback than waiting for session-end world_health).

  - `--scrub [--dry-run]` removes leaked observation lines.

  - `--check "<text>"` lets a director verify a single line before writing.

social.py imports from here (single source of truth for fingerprinting).
world_health.py's session-end firewall_scan stays independent and continues
to use social._forbidden_texts for its own coverage.

Usage:
    python Tools/firewall.py --scan
    python Tools/firewall.py --check "some line of text"
    python Tools/firewall.py --scrub --dry-run
    python Tools/firewall.py --scrub
    python Tools/firewall.py --self-test
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import world_tick as _wt
except Exception:  # pragma: no cover
    _wt = None

# ── Constants ─────────────────────────────────────────────────────────────────

HEADLINE_MAX = 140          # an abstract observation is short by definition
_OBS_HEADING = "## What I've learned about others"
_WORD = re.compile(r"\w+", re.UNICODE)
# Matches social.py's observation_line format:
#   - *[Day N]* — about `name`: ...
# Handles em-dash (U+2014) or double-hyphen.
_OBS_PATTERN = re.compile(
    r"^\s*-\s+\*\[Day[^\]]*\]\*\s+(?:—|--)\s+about `[^`]+`:",
    re.UNICODE,
)


# ── Core fingerprint functions (single source of truth) ──────────────────────
#
# These functions are imported by social.py — DO NOT change their signatures or
# token logic without verifying social._self_test() still passes.

def _tokens(s):
    """Unicode-aware word tokenizer. A non-ASCII NPC name can't dodge matches."""
    return _WORD.findall(str(s or "").lower())


def _shares_ngram(text, forbidden, ngram=4):
    """True if `text` shares a verbatim n-gram run with any forbidden string.

    For a long secret (>= ngram words), a run of `ngram` consecutive words is
    a coincidence-proof signal. A short secret (< ngram words) is caught by
    requiring its *whole* phrase verbatim (effective n = len), with a floor of
    2 so single-word secrets are not over-matched.
    """
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
    """True if `headline` is safe to write into actor-safe memory."""
    h = " ".join(str(headline or "").split())
    if len(h) > max_len:
        return False
    return not _shares_ngram(h, forbidden, ngram)


def _forbidden_texts(agents):
    """Structured front-matter secrets from each living agent's drives.md.

    Covers goal `pursue`/`success` strings and relationship `note` fields.
    This is the propagation-guard scope (fast, front-matter only). For the
    full per-post and session-end scan, use gather_secrets().

    Promoted from social.py as the single source of truth.
    """
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


# ── Extended secrets gathering (per-post and session-end scan) ────────────────

def _drives_body(folder):
    """Prose body of drives.md — everything after the front-matter fence.

    Covers ## Agenda, ## Reflection notes (director-appended beliefs). The
    per-post propagation guard sees only parsed front-matter; this catches
    reflection beliefs and agenda text that are equally secret.
    """
    try:
        lines = Path(folder, "drives.md").read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    if not lines or lines[0].strip() != "---":
        return "\n".join(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:])
    return ""


def gather_secrets(root, agents=None):
    """Build per-agent forbidden texts: front-matter + drives body + secrets.md.

    Returns {agent_name: [secret_str, ...]}.
    More comprehensive than _forbidden_texts() alone; used by both the
    per-post --scan and the scrub path.

    Scope boundary: this covers the *per-Cast-agent* corpus — each living
    agent's drives.md (front-matter + prose body) and their secrets.md. It does
    NOT include campaign-level secret files (`Game/gm-secrets.md`,
    `Game/developments.md` hidden entries, `Game/plots.md` prose). The leak
    vector this guards is director-written observations *about agents*, which is
    where the fingerprint lands. A campaign-level secret not encoded in any
    agent's drives won't be caught here — keep upstream discipline (a fixed,
    goal-free headline) as the primary defense.
    """
    if _wt is None:
        return {}
    if agents is None:
        try:
            agents = _wt.discover_agents(root)
        except Exception:
            return {}
    root = Path(root)
    per_agent = {}
    for a in (agents or []):
        folder = root / "Cast" / a.name
        texts = list(_forbidden_texts([a]))
        body = _drives_body(folder)
        if body.strip():
            texts.append(body)
        try:
            sec = (folder / "secrets.md").read_text(encoding="utf-8")
            if sec.strip():
                texts.append(sec)
        except Exception:
            pass
        if any(t.strip() for t in texts):
            per_agent[a.name] = texts
    return per_agent


def _flat(per_agent):
    """Flatten a per-agent dict of secret texts into a single list."""
    return [s for texts in per_agent.values() for s in texts]


def is_safe(text, root=None, forbidden=None):
    """True if `text` is safe to write into actor-safe memory.

    Pass `forbidden` (flat list) or `root` (will call gather_secrets).
    """
    if forbidden is None:
        if root is None:
            raise ValueError("Either root or forbidden must be provided.")
        forbidden = _flat(gather_secrets(root))
    return safe_headline(text, forbidden)


# ── Sanctioned write path ─────────────────────────────────────────────────────

def append_observation(root, learner, day, text):
    """The *only* sanctioned way to add a cross-character observation.

    Validates `text` against all living agents' secret corpus before writing.
    Returns True if written, False if rejected by the firewall or already present.
    Raises FileNotFoundError if the learner's memory.md does not exist.

    Directors: call this instead of raw Write/Edit on 'What I've learned'.
    Or validate first: `python Tools/firewall.py --check "<line>"`.
    """
    forbidden = _flat(gather_secrets(root))
    if not safe_headline(text, forbidden):
        print(
            f"firewall: REJECTED observation for {learner!r} -- text echoes a secret. "
            f"Nothing written.",
            file=sys.stderr,
        )
        return False

    p = Path(root) / "Cast" / learner / "memory.md"
    if not p.exists():
        return False
    content = p.read_text(encoding="utf-8")
    if text in content:
        return False  # idempotent
    if _OBS_HEADING in content:
        idx = content.index(_OBS_HEADING)
        nl = content.index("\n", idx)
        content = content[:nl + 1] + text + "\n" + content[nl + 1:]
    else:
        content = content.rstrip() + f"\n\n{_OBS_HEADING}\n{text}\n"
    # Atomic write: stage to a temp file in the same dir, then replace, so a
    # crash mid-write can never truncate the learner's memory.md.
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(p)
    return True


# ── Scan ──────────────────────────────────────────────────────────────────────

def scan(root, agents=None):
    """Scan all Cast/*/memory.md for leaked secret text.

    Returns list of (severity, message) — same shape as world_health.firewall_scan.
    Uses the full secret corpus (front-matter + drives body + secrets.md), so
    it catches reflection beliefs and secrets.md text, not just goal text.
    Exit-signal: a non-empty list means leaks were found.
    """
    if _wt is None:
        return [("note", "scan skipped: could not import world_tick")]
    per_agent = gather_secrets(root, agents)
    if not per_agent:
        return []
    root = Path(root)
    findings = []
    for mem in sorted((root / "Cast").glob("*/memory.md")):
        if mem.parent.name.startswith("_"):
            continue
        try:
            text = mem.read_text(encoding="utf-8")
        except Exception:
            continue
        owner = mem.parent.name
        for src_name, forbidden in per_agent.items():
            if _shares_ngram(text, forbidden):
                findings.append((
                    "warn",
                    f"Cast/{owner}/memory.md echoes {src_name}'s secret text "
                    f"-- firewall leak. Run --scrub --dry-run to see the line.",
                ))
    return findings


# ── Scrub ─────────────────────────────────────────────────────────────────────

def scrub(root, agents=None, dry_run=True):
    """Remove leaked cross-character observation lines from Cast/*/memory.md.

    Only removes lines that are ALL of:
      1. Under '## What I've learned about others'
      2. Match the auto-generated observation format (never authored log entries)
      3. Echo a secret fingerprint

    In dry_run mode, prints the offending lines and returns them without writing.
    Always run --dry-run first; --scrub is irreversible without git.

    Returns list of (relative_path, line_text) pairs that were/would be removed.
    """
    per_agent = gather_secrets(root, agents)
    if not per_agent:
        return []
    forbidden = _flat(per_agent)
    root = Path(root)
    removed = []

    for mem in sorted((root / "Cast").glob("*/memory.md")):
        if mem.parent.name.startswith("_"):
            continue
        try:
            content = mem.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = content.splitlines(keepends=True)
        in_obs = False
        new_lines = []
        changed = False

        for raw in lines:
            stripped = raw.rstrip("\r\n")
            # Track section boundaries
            if stripped.strip() == _OBS_HEADING:
                in_obs = True
                new_lines.append(raw)
                continue
            if in_obs and re.match(r"^##\s", stripped) and stripped.strip() != _OBS_HEADING:
                in_obs = False

            if in_obs and _OBS_PATTERN.match(stripped):
                if _shares_ngram(stripped, forbidden):
                    removed.append((str(mem.relative_to(root)), stripped.strip()))
                    changed = True
                    continue  # drop the line

            new_lines.append(raw)

        if changed and not dry_run:
            mem.write_text("".join(new_lines), encoding="utf-8")

    return removed


# ── Root finder ───────────────────────────────────────────────────────────────

def _find_root():
    root = Path.cwd()
    for cand in [root, *root.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return root


# ── Self-test ─────────────────────────────────────────────────────────────────

def _self_test():
    import tempfile

    # ── 1. Verbatim secret echoed in a line → is_safe returns False ───────────
    secret = "keep diana and through her daniel the bridge controlled without revealing the cult"
    forbidden = [secret]
    assert not safe_headline(secret, forbidden), "verbatim secret must be rejected"
    # Truncated with ellipsis still caught via 4-gram
    trunc = secret[:60] + "..."
    assert not safe_headline(trunc, forbidden), "truncated leak must be rejected"

    # ── 2. Clean witnessed-event line → safe, not flagged ─────────────────────
    clean = "has been quietly pursuing aims of their own lately"
    assert safe_headline(clean, forbidden), "abstract observation must pass"
    assert safe_headline("Mara seized the customs house", forbidden), "unrelated event must pass"

    # ── 3. Common short words → no false-positive (1-word secret too generic) ──
    one_word = ["control"]
    assert safe_headline("the council will control nothing", one_word), \
        "1-word secret must not block a 3-word run (1-word secrets are too generic)"
    # Short secret (3 words) caught by whole-phrase match
    short3 = ["burn the chantry"]
    assert not safe_headline("she plans to burn the chantry tonight", short3), \
        "3-word short secret must be caught whole-phrase"
    assert safe_headline("she lit a candle", short3), "unrelated must pass"

    # ── 4. --scrub --dry-run lists offending lines; --scrub removes only them ──
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "CLAUDE.md").write_text("x", encoding="utf-8")
        sabine_dir = root / "Cast" / "sabine"
        sabine_dir.mkdir(parents=True)
        (sabine_dir / "drives.md").write_text(
            f"---\nliving: true\ngoal: {{ pursue: control, target: diana, "
            f"success: \"{secret}\" }}\n---\n",
            encoding="utf-8",
        )
        kira_dir = root / "Cast" / "kira"
        kira_dir.mkdir(parents=True)
        (kira_dir / "drives.md").write_text("---\nliving: true\n---\n", encoding="utf-8")
        leaked_line = f"- *[Day 1]* — about `sabine`: heard word that {secret}"
        safe_line = "- *[Day 2]* — about `sabine`: heard word that moved on her own designs"
        kira_mem = (kira_dir / "memory.md")
        kira_mem.write_text(
            f"# kira\n\n{_OBS_HEADING}\n{leaked_line}\n{safe_line}\n",
            encoding="utf-8",
        )

        dry = scrub(root, dry_run=True)
        assert len(dry) == 1, f"dry-run should list 1 leaked line, got {len(dry)}: {dry}"
        assert "sabine" in dry[0][1], dry[0]
        # dry-run: file unchanged
        assert leaked_line in kira_mem.read_text(encoding="utf-8"), "dry-run must not modify file"

        live = scrub(root, dry_run=False)
        assert len(live) == 1, f"live scrub should remove 1 line, got {len(live)}"
        after = kira_mem.read_text(encoding="utf-8")
        assert leaked_line not in after, "scrub must remove the leaked line"
        assert safe_line in after, "scrub must preserve the safe observation line"

    # ── 5. Unicode NPC name can't dodge the fingerprint match ─────────────────
    uni_secret = "Søren guards the Zaïre relic in secret"
    uni_forbidden = [uni_secret]
    assert _shares_ngram("they say Søren guards the Zaïre relic now", uni_forbidden), \
        "Unicode name in a secret must be matched"

    print("firewall self-test: OK")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv):
    ap = argparse.ArgumentParser(
        prog="firewall.py",
        description="Firewall scan and sanctioned write path for actor memory.",
    )
    ap.add_argument("--scan", action="store_true",
                    help="scan all Cast/*/memory.md for leaked secrets (exit 1 if any)")
    ap.add_argument("--check", type=str, metavar="TEXT",
                    help="check whether a single line is actor-safe")
    ap.add_argument("--scrub", action="store_true",
                    help="remove leaked observation lines from Cast/*/memory.md")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --scrub: show what would be removed without writing")
    ap.add_argument("--self-test", action="store_true",
                    help="run built-in assertions and exit")
    ns = ap.parse_args(argv[1:])

    if ns.self_test:
        return _self_test()

    root = _find_root()

    if ns.check is not None:
        forbidden = _flat(gather_secrets(root))
        if safe_headline(ns.check, forbidden):
            print("SAFE: the line does not echo any secret text.")
            return 0
        else:
            print("REJECTED: the line echoes a secret. Do not write it to actor memory.")
            return 1

    if ns.scrub:
        removed = scrub(root, dry_run=ns.dry_run)
        if not removed:
            print("No leaked observation lines found.")
            return 0
        label = "Would remove" if ns.dry_run else "Removed"
        for path, line in removed:
            print(f"{label}: {path}")
            print(f"  {line[:120]}")
        if ns.dry_run:
            print(f"\n{len(removed)} line(s) flagged. Run without --dry-run to remove them.")
        else:
            print(f"\n{len(removed)} line(s) removed.")
        return 0

    if ns.scan:
        findings = scan(root)
        if not findings:
            print("Firewall scan: clean. No leaked secret text in actor memory.")
            return 0
        for sev, msg in findings:
            mark = "WARN" if sev == "warn" else "NOTE"
            print(f"[{mark}] {msg}")
        return 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
