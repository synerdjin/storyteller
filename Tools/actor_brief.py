#!/usr/bin/env python3
"""Firewall-safe npc-actor briefing assembler.

Engine v2.11.0 — Part B of the firewall-safe actor pipeline.

Assembles a ready-to-use npc-actor briefing from a character's actor-safe
files only — the path allowlist makes it structurally impossible to leak
secrets.md, drives.md, or sheet.md into the briefing, no matter what the GM
accidentally types.

Paste the output to the npc-actor agent (or pipe it in). The footer reminds
the actor of its core contract.

Usage:
    python Tools/actor_brief.py diana
    python Tools/actor_brief.py diana --scene "Salt Quarter, pre-dawn, heavy fog" \\
        --said "I thought you'd gone for good" \\
        --stance "Tired, holding her ground; already committed to the bargain" \\
        --day 14
    python Tools/actor_brief.py diana --recent "<last 3 exchanges verbatim>"
    python Tools/actor_brief.py --self-test
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Optional: retrieval for relevant context — degrades gracefully when unavailable
try:
    import memory_search as _ms
    _HAS_SEARCH = True
except Exception:
    _HAS_SEARCH = False

# ── Security: path allowlist ──────────────────────────────────────────────────
#
# These are the ONLY filenames this tool may open for any Cast/<name>/ folder.
# Anything else — secrets.md, drives.md, sheet.md, gm-secrets.md, another
# character's files — is refused by _read_safe() before a single byte is read.
_ALLOWED_FILENAMES = {"profile.md", "memory.md"}

# ── Briefing template ─────────────────────────────────────────────────────────

_BRIEF_TEMPLATE = """\
# Actor briefing -- {name}

> You are voicing **{name}** in an ongoing tabletop RPG session. You know only
> what appears in this briefing -- not the GM's plans, not what other
> characters are hiding, not anything that isn't written below.

## In-fiction date: {day_line}

---

## Who you are

{profile}

---

## What you remember

{memory}
{extra_sections}\
## Your contract

Stay strictly in character -- in voice, mood, agenda, and limits. A quiet,
withholding, or evasive reply is a valid choice; the only wrong reply is a
generic, deflect-everything non-answer that ignores what was just said. If
you don't know something in the fiction, your character doesn't know it
either. Do not invent details not already established. Speak as {name} and
no one else.
"""

_SCENE_SECTION = """\
## The scene right now

{scene}

---

"""

_DIALOGUE_SECTION = """\
## Recent dialogue (verbatim -- quote your own words back to yourself)

{recent}
{stance_line}\

---

"""

_STANCE_LINE = "\n**Your stance so far this scene:** {stance}\n"

_SAID_SECTION = """\
## What the Player just said to you

{said}

---

"""

_RETRIEVAL_SECTION = """\
## Relevant context (from memory index)

{hits}

---

"""


# ── Core functions ────────────────────────────────────────────────────────────

def _read_safe(path, allowed_names=_ALLOWED_FILENAMES):
    """Read file at `path` only if its basename is in `allowed_names`.

    Raises PermissionError on any violation — this is the structural guarantee
    that secrets.md, drives.md, and sheet.md can never appear in a briefing.
    """
    p = Path(path)
    if p.name not in allowed_names:
        raise PermissionError(
            f"actor_brief path-allowlist violation: '{p.name}' is not in "
            f"{sorted(allowed_names)}. "
            f"Refusing to read '{p}'. Never pass secrets.md, drives.md, "
            f"sheet.md, or gm-secrets.md to the npc-actor."
        )
    return p.read_text(encoding="utf-8")


def assemble(name, root, scene=None, recent=None, stance=None, said=None,
             day=None, retrieve=True):
    """Build and return the npc-actor briefing string.

    Reads ONLY Cast/<name>/profile.md and Cast/<name>/memory.md.
    All other file reads are physically refused by _read_safe().

    Parameters
    ----------
    name     : NPC name (must match Cast/<name>/ folder)
    root     : campaign root directory
    scene    : public scene context (actor-safe text only)
    recent   : verbatim recent dialogue to preserve continuity
    stance   : 2-3 sentence stance recap from this scene
    said     : what the Player just said (the turn this actor must respond to)
    day      : in-fiction day number; if None, reads from Game/current-scene.md
    retrieve : whether to attempt memory_search retrieval (defaults True)
    """
    cast_dir = Path(root) / "Cast" / name
    if not cast_dir.exists():
        raise FileNotFoundError(
            f"Cast/{name}/ not found under {root}. "
            f"Create the folder and add at least profile.md."
        )

    profile_path = cast_dir / "profile.md"
    if not profile_path.exists():
        raise FileNotFoundError(
            f"Cast/{name}/profile.md not found. "
            f"Cannot build a briefing without a profile."
        )

    profile = _read_safe(profile_path)

    memory_path = cast_dir / "memory.md"
    memory = _read_safe(memory_path) if memory_path.exists() else "*(no memory recorded yet)*"

    day_line = f"Day {day}" if day is not None else "Day ? (unknown -- check current-scene.md)"

    # Optional retrieval pass (scope=public guarantees no secret chunks)
    retrieval_block = ""
    if retrieve and _HAS_SEARCH and scene:
        try:
            hits = _ms.search(scene, scope="public", owner=name, top_k=3, mode="lexical")
            if hits:
                snippets = "\n".join(
                    f"- {h.get('text', '').strip()[:140]}" for h in hits[:3]
                )
                retrieval_block = _RETRIEVAL_SECTION.format(hits=snippets)
        except Exception:
            pass  # retrieval is a bonus; never fail the briefing because of it

    # Build the optional sections in reading order
    extra = ""
    if scene:
        extra += _SCENE_SECTION.format(scene=scene.strip())
    if recent or stance:
        stance_line = _STANCE_LINE.format(stance=stance.strip()) if stance else ""
        extra += _DIALOGUE_SECTION.format(
            recent=(recent.strip() if recent else "*(none yet)*"),
            stance_line=stance_line,
        )
    if said:
        extra += _SAID_SECTION.format(said=said.strip())
    if retrieval_block:
        extra += retrieval_block

    return _BRIEF_TEMPLATE.format(
        name=name,
        day_line=day_line,
        profile=profile.strip(),
        memory=memory.strip(),
        extra_sections=("\n---\n\n" + extra) if extra else "\n---\n\n",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_root():
    root = Path.cwd()
    for cand in [root, *root.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return root


def _current_day(root):
    p = Path(root) / "Game" / "current-scene.md"
    if p.exists():
        m = re.search(r"Day\s+(\d+)", p.read_text(encoding="utf-8"))
        if m:
            return int(m.group(1))
    return None


# ── Self-test ─────────────────────────────────────────────────────────────────

def _self_test():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cast_dir = root / "Cast" / "diana"
        cast_dir.mkdir(parents=True)

        profile_text = (
            "# Diana\n\n## At a glance\n"
            "- Role: key NPC in the chronicle\n"
            "- Voice: clipped, precise, never wastes a word\n"
            "- Vibe: guarded but magnetic; hides grief behind competence\n"
        )
        memory_text = (
            "# Diana -- memory\n\n## Standing\n"
            "- Disposition toward player: cautious, watching\n\n"
            "## Log\n"
            "- [Day 1] First meeting at the docks.\n"
        )
        secret_text = (
            "# Diana -- secrets (GM ONLY)\n\n"
            "She is secretly the sire of half the coterie.\n"
            "Her real goal is to hollow out the coterie from within.\n"
        )
        drives_text = (
            "---\nliving: true\n"
            "goal: { pursue: control, target: coterie, "
            "success: hollow out the coterie without revealing involvement }\n"
            "---\n\n## Agenda\nShe will manipulate the player into the role of pawn.\n"
        )

        (cast_dir / "profile.md").write_text(profile_text, encoding="utf-8")
        (cast_dir / "memory.md").write_text(memory_text, encoding="utf-8")
        (cast_dir / "secrets.md").write_text(secret_text, encoding="utf-8")
        (cast_dir / "drives.md").write_text(drives_text, encoding="utf-8")

        # ── 1. Briefing contains profile + memory content + correct day ────────
        brief = assemble("diana", root, scene="foggy docks", day=7, retrieve=False)
        assert "guarded but magnetic" in brief, "profile content must appear in brief"
        assert "cautious, watching" in brief, "memory content must appear in brief"
        assert "Day 7" in brief, "day stamp must appear in brief"
        assert "diana" in brief.lower(), "NPC name must appear in brief"

        # ── 2. secrets.md / drives.md content must NEVER appear in the briefing -
        assert "secretly the sire" not in brief, "secrets.md leaked into brief"
        assert "hollow out the coterie without" not in brief, "drives.md goal leaked"
        assert "She will manipulate the player" not in brief, "drives.md agenda leaked"

        # ── 3. Missing profile fails loudly (FileNotFoundError) ───────────────
        (root / "Cast" / "ghost").mkdir(parents=True)
        try:
            assemble("ghost", root, retrieve=False)
            assert False, "Should raise FileNotFoundError for missing profile"
        except FileNotFoundError:
            pass

        # ── 4. Path allowlist rejects secrets.md and drives.md explicitly ──────
        for forbidden in ("secrets.md", "drives.md", "sheet.md", "gm-secrets.md"):
            try:
                _read_safe(cast_dir / forbidden)
                assert False, f"Should raise PermissionError for {forbidden}"
            except PermissionError:
                pass

        # ── 4b. Safe files are explicitly allowed ─────────────────────────────
        _read_safe(cast_dir / "profile.md")
        _read_safe(cast_dir / "memory.md")

        # ── 5. Optional args appear in brief ──────────────────────────────────
        brief2 = assemble(
            "diana", root, scene="at the docks", day=7, retrieve=False,
            said="I thought you'd gone for good.",
            stance="Tired; holding her ground; committed to the deal.",
        )
        assert "I thought you" in brief2, "--said must appear in brief"
        assert "Tired" in brief2, "--stance must appear in brief"

    print("actor_brief self-test: OK")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv):
    ap = argparse.ArgumentParser(
        prog="actor_brief.py",
        description="Assemble a firewall-safe npc-actor briefing from actor-safe files only.",
    )
    ap.add_argument("name", nargs="?", help="NPC name matching Cast/<name>/")
    ap.add_argument("--scene", type=str,
                    help="public scene context (actor-safe; quoted string)")
    ap.add_argument("--recent", type=str,
                    help="verbatim recent dialogue (paste the last few exchanges)")
    ap.add_argument("--stance", type=str,
                    help="2-3 sentence stance recap (what the character committed to this scene)")
    ap.add_argument("--said", type=str,
                    help="what the Player just said to the character")
    ap.add_argument("--day", type=int,
                    help="in-fiction day number (default: read from Game/current-scene.md)")
    ap.add_argument("--no-retrieve", action="store_true",
                    help="skip the optional memory_search retrieval pass")
    ap.add_argument("--self-test", action="store_true",
                    help="run built-in assertions and exit")
    ns = ap.parse_args(argv[1:])

    if ns.self_test:
        return _self_test()

    if not ns.name:
        ap.error("NPC name is required (or pass --self-test)")

    root = _find_root()
    day = ns.day if ns.day is not None else _current_day(root)

    try:
        brief = assemble(
            ns.name, root,
            scene=ns.scene,
            recent=ns.recent,
            stance=ns.stance,
            said=ns.said,
            day=day,
            retrieve=not ns.no_retrieve,
        )
    except (FileNotFoundError, PermissionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(brief)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
