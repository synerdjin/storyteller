#!/usr/bin/env python3
"""Compile the rendered chapters into a single Story/compiled.md for export.

The `chapter-renderer` writes one file per chapter under Story/chapters/. This
tool stitches them into a single readable document — front-matter and HTML
comments stripped, chapters ordered by their `chapter:` number — so the Player
can read or export the whole fic at once. Pure text work, no dependencies.

Usage:
    python Tools/story_compile.py             # write Story/compiled.md
    python Tools/story_compile.py --dry-run   # print, write nothing
    python Tools/story_compile.py --self-test # built-in assertions
"""

import argparse
import re
import sys
from pathlib import Path


def parse_front_matter(text):
    """Return (fields, body) for a '---' front-matter doc; ({}, text) if none."""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip().strip('"').strip("'")
    return fields, m.group(2)


def _strip_comments(body):
    """Drop HTML comment blocks (the template's author notes) and trim blanks."""
    return re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()


def _chapter_no(fields, path):
    try:
        return int(fields.get("chapter", ""))
    except (TypeError, ValueError):
        return 10**9  # unnumbered chapters sort last, then by name


def gather_chapters(root):
    """Every Story/chapters/*.md (skipping _skeletons), ordered for reading."""
    d = Path(root) / "Story" / "chapters"
    out = []
    for p in sorted(d.glob("*.md")):
        if p.name.startswith("_"):
            continue
        fields, body = parse_front_matter(p.read_text(encoding="utf-8"))
        out.append((p, fields, _strip_comments(body)))
    out.sort(key=lambda t: (_chapter_no(t[1], t[0]), t[0].name))
    return out


def story_title(root):
    """The H1 from Story/index.md, if the masthead has been filled in."""
    idx = Path(root) / "Story" / "index.md"
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                t = line[2:].strip()
                if t and "<" not in t and "&lt;" not in t:   # skip unfilled placeholder
                    return t
    return "The Chronicle"


def compile_text(root):
    chapters = gather_chapters(root)
    lines = [f"# {story_title(root)}", ""]
    if not chapters:
        lines.append("*(no chapters rendered yet)*")
        return "\n".join(lines) + "\n"
    for _, f, body in chapters:
        num = f.get("chapter", "").strip()
        head = f"## {num + '. ' if num else ''}{f.get('title', 'Untitled')}"
        meta = []
        if f.get("day"):
            meta.append(f"Day {f['day']}")
        if f.get("pov"):
            meta.append(f"POV: {f['pov']}")
        lines += ["", head]
        if meta:
            lines.append(f"*{' · '.join(meta)}*")
        lines += ["", body, ""]
    return "\n".join(lines).rstrip() + "\n"


def _find_root(start):
    cur = Path(start).resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Story").is_dir():
            return cand
    return Path(start)


def run(root, dry_run=False):
    text = compile_text(root)
    if dry_run:
        sys.stdout.write(text)
        return 0
    out = Path(root) / "Story" / "compiled.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    n = len(gather_chapters(root))
    print(f"Compiled {n} chapter(s) into {out.as_posix()}.")
    return 0


def _self_test():
    import tempfile

    fields, body = parse_front_matter(
        '---\nchapter: 2\ntitle: "Salt and Ash"\nday: 14\n---\n<!-- note -->\nProse.\n')
    assert fields["chapter"] == "2" and fields["title"] == "Salt and Ash"
    assert _strip_comments(body) == "Prose."

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        ch = root / "Story" / "chapters"
        ch.mkdir(parents=True)
        (root / "Story" / "index.md").write_text("# Blood on the Tide\n", encoding="utf-8")
        # written out of order; should compile in chapter-number order.
        (ch / "0002-salt.md").write_text(
            '---\nchapter: 2\ntitle: "Salt"\npov: player\nday: 14\n---\nSecond.\n',
            encoding="utf-8")
        (ch / "0001-ash.md").write_text(
            '---\nchapter: 1\ntitle: "Ash"\npov: mara\nday: 1\n---\n<!-- x -->\nFirst.\n',
            encoding="utf-8")
        (ch / "_TEMPLATE.md").write_text(
            "---\nchapter: 0\n---\nSKELETON MUST NOT APPEAR\n", encoding="utf-8")

        text = compile_text(root)
        assert "# Blood on the Tide" in text
        assert "SKELETON" not in text, "the _TEMPLATE skeleton must be skipped"
        assert text.index("First.") < text.index("Second."), "ordered by chapter number"
        assert "## 1. Ash" in text and "## 2. Salt" in text
        assert "Day 1 · POV: mara" in text
        rc = run(root)
        assert rc == 0 and (root / "Story" / "compiled.md").exists()

    print("story_compile self-test: OK")
    return 0


def main(argv):
    p = argparse.ArgumentParser(description="Compile Story/chapters into one file.")
    p.add_argument("--dry-run", action="store_true", help="print, write nothing")
    p.add_argument("--self-test", action="store_true", help="run assertions and exit")
    args = p.parse_args(argv[1:])
    if args.self_test:
        return _self_test()
    return run(_find_root(Path.cwd()), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
