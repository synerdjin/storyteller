#!/usr/bin/env python3
"""Deterministic resource tracker for the Storyteller Game Master.

Reads and writes the volatile pools in Character/sheet.md (or any sheet
passed with --sheet), applies rule-based spends / gains / recovery, and
logs every change to Character/resource-log.md.

The GM calls this instead of hand-editing the sheet. Claude decides *when*
to spend or recover; the tool does the arithmetic and enforces the rules.

"Be seen to be fair" — every mutation is logged with a day-stamp and
reason, auditable the same way dice.py logs every roll.

Usage:
    python Tools/resources.py --show
    python Tools/resources.py --spend wp 1   --reason "soothe Diana's Beast" --day 1
    python Tools/resources.py --spend quint 2 --reason "ease the read of Kira"
    python Tools/resources.py --gain  wp 1   --reason "Nature: new sensation"
    python Tools/resources.py --rest
    python Tools/resources.py --rest --full
    python Tools/resources.py --node 2       --reason "Stadtbad Node"
    python Tools/resources.py --damage lethal 2
    python Tools/resources.py --damage bashing 3 --soak 1
    python Tools/resources.py --heal 1
    python Tools/resources.py --paradox +2   --reason "vulgar magick, witnessed"
    python Tools/resources.py --self-test
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ── Health track ──────────────────────────────────────────────────────────────

HEALTH_LEVELS = [
    "Bruised", "Hurt", "Injured", "Wounded", "Mauled", "Crippled", "Incapacitated",
]
HEALTH_PENALTIES = {
    "Bruised": 0, "Hurt": -1, "Injured": -1,
    "Wounded": -2, "Mauled": -2, "Crippled": -5, "Incapacitated": None,
}
DAMAGE_MARKS = {"bashing": "●", "lethal": "/", "aggravated": "*"}
MARK_EMPTY = "○"
MARK_SEVERITY = {"○": 0, "●": 1, "/": 2, "*": 3}

# ASCII fallbacks for console output. The sheet *file* keeps the real glyphs
# (it's written UTF-8); but `--show` prints to the terminal, which on Windows is
# cp1252 and cannot encode ● / ○ — so console rendering translates them. Keep
# every value here ASCII-only so `--show` can never crash on a stock console.
_ASCII_GLYPH = {"●": "#", "○": ".", "/": "/", "*": "*"}


def _ascii(s):
    """Translate display glyphs to ASCII so console output survives cp1252."""
    return "".join(_ASCII_GLYPH.get(ch, ch) for ch in s)


# Pool name normalisation
POOL_ALIASES = {
    "wp": "wp", "willpower": "wp",
    "quint": "quint", "quintessence": "quint",
    "paradox": "paradox",
}

# Recovery defaults — override via Game/resource-rules.json
_DEFAULTS = {
    "wp_rest": 1,       # WP regained per --rest
    "heal_per_call": 1, # Health levels healed per --heal
}

# ── Config ────────────────────────────────────────────────────────────────────


def load_config(root):
    """Load resource rules from Game/resource-rules.json if present."""
    p = Path(root) / "Game" / "resource-rules.json"
    cfg = dict(_DEFAULTS)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in data.items() if k in _DEFAULTS})
        except Exception:
            pass
    return cfg


def current_day(root):
    """Read Day N from Game/current-scene.md."""
    p = Path(root) / "Game" / "current-scene.md"
    if p.exists():
        m = re.search(r"Day\s+(\d+)", p.read_text(encoding="utf-8"))
        if m:
            return int(m.group(1))
    return None


# ── Sheet parser / writer ─────────────────────────────────────────────────────

def _pips(current, rating):
    """Rebuild a WP pip string: ●×current + ○×(rating-current)."""
    return "●" * current + "○" * max(0, rating - current)


class Sheet:
    """Parse and round-trip a WoD character sheet.

    Round-trip guarantee: every write op changes *only* the targeted
    number/glyph; the rest of the file is byte-identical to the original.
    """

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Sheet not found: {self.path}")
        self._lines = self.path.read_text(encoding="utf-8").splitlines()
        self._dirty = False
        self._parse()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse(self):
        self._wp_line = None
        self.wp_rating = None
        self.wp_current = None

        self._quint_line = None
        self.quint = None
        self.quint_max = 20

        self._paradox_line = None
        self.paradox = None
        self.paradox_max = 20

        self._health = {lvl: (None, MARK_EMPTY) for lvl in HEALTH_LEVELS}

        for i, line in enumerate(self._lines):
            self._try_wp(i, line)
            self._try_quint_paradox(i, line)
            self._try_health(i, line)

    def _try_wp(self, i, line):
        if "**Willpower**" not in line:
            return
        m_r = re.search(r"\(Rating\s+(\d+)\)", line)
        m_p = re.search(r"Current pool:\s*(\d+)\s*/\s*(\d+)", line)
        if m_r and m_p:
            self._wp_line   = i
            self.wp_rating  = int(m_r.group(1))
            self.wp_current = int(m_p.group(1))

    def _try_quint_paradox(self, i, line):
        if "Quintessence" in line:
            m = re.search(r"\*\*Quintessence:\*\*\s*(\d+)", line)
            if m:
                self._quint_line = i
                self.quint = int(m.group(1))
                mr = re.search(r"track\s*\d+[–\-]\s*(\d+)", line)
                if mr:
                    self.quint_max = int(mr.group(1))
        if "Paradox" in line:
            m = re.search(r"\*\*Paradox:\*\*\s*(\d+)", line)
            if m:
                self._paradox_line = i
                self.paradox = int(m.group(1))

    def _try_health(self, i, line):
        for lvl in HEALTH_LEVELS:
            if lvl not in line:
                continue
            # Match the mark in the last cell of the table row: | ○ | or | ○
            m = re.search(r"\|\s*([○●/*])\s*\|?\s*$", line)
            if m:
                self._health[lvl] = (i, m.group(1))

    # ── Derived ───────────────────────────────────────────────────────────────

    def wound_penalty(self):
        """Worst marked Health level's penalty dice (None = Incapacitated, 0 = none)."""
        for lvl in reversed(HEALTH_LEVELS):
            _, mark = self._health[lvl]
            if mark != MARK_EMPTY:
                return HEALTH_PENALTIES[lvl]
        return 0

    def health_summary(self):
        rows = []
        for lvl in HEALTH_LEVELS:
            _, mark = self._health[lvl]
            rows.append(f"  {lvl:<15} {mark}")
        return "\n".join(rows)

    # ── Line mutation (round-trip safe) ───────────────────────────────────────

    def _sub_line(self, i, pattern, repl, count=1, flags=0):
        """re.sub on one line. Returns True if the line changed, False if no match."""
        new = re.sub(pattern, repl, self._lines[i], count=count, flags=flags)
        if new == self._lines[i]:
            return False
        self._lines[i] = new
        self._dirty = True
        return True

    # ── Pool setters ──────────────────────────────────────────────────────────

    def set_wp(self, new_val):
        if self._wp_line is None:
            raise ValueError("Willpower not found on sheet.")
        if new_val < 0:
            raise ValueError(f"Willpower cannot go below 0 (tried {new_val}).")
        if new_val > self.wp_rating:
            raise ValueError(f"Willpower cannot exceed rating {self.wp_rating} (tried {new_val}).")
        if new_val == self.wp_current:
            return self.wp_current, new_val
        old = self.wp_current
        # 1. Update "Current pool: X / Y" — change X only, preserve Y (max)
        ok = self._sub_line(
            self._wp_line,
            r"(Current pool:\s*)(\d+)(\s*/\s*)(\d+)",
            lambda m: m.group(1) + str(new_val) + m.group(3) + m.group(4),
        )
        if not ok:
            raise ValueError(f"Could not find 'Current pool:' on WP line {self._wp_line+1}.")
        # 2. Rebuild pip string
        new_pips = _pips(new_val, self.wp_rating)
        self._sub_line(
            self._wp_line,
            r"(\*\*Willpower\*\*\s)[●○]+",
            lambda m: m.group(1) + new_pips,
        )
        self.wp_current = new_val
        return old, new_val

    def set_quint(self, new_val):
        if self._quint_line is None:
            raise ValueError("Quintessence not found on sheet.")
        new_val = max(0, min(new_val, self.quint_max))
        if new_val == self.quint:
            return self.quint, new_val
        old = self.quint
        ok = self._sub_line(
            self._quint_line,
            r"(\*\*Quintessence:\*\*\s*)(\d+)",
            lambda m: m.group(1) + str(new_val),
        )
        if not ok:
            raise ValueError(f"Could not update Quintessence on line {self._quint_line+1}.")
        self.quint = new_val
        return old, new_val

    def set_paradox(self, new_val):
        if self._paradox_line is None:
            raise ValueError("Paradox not found on sheet.")
        new_val = max(0, min(new_val, self.paradox_max))
        if new_val == self.paradox:
            return self.paradox, new_val
        old = self.paradox
        ok = self._sub_line(
            self._paradox_line,
            r"(\*\*Paradox:\*\*\s*)(\d+)",
            lambda m: m.group(1) + str(new_val),
        )
        if not ok:
            raise ValueError(f"Could not update Paradox on line {self._paradox_line+1}.")
        self.paradox = new_val
        return old, new_val

    def mark_health(self, damage_type, count):
        """Mark `count` empty Health levels with damage_type. Returns list of levels marked."""
        mark = DAMAGE_MARKS.get(damage_type)
        if mark is None:
            raise ValueError(
                f"Unknown damage type {damage_type!r}. Use: bashing, lethal, aggravated."
            )
        if not any(li is not None for li, _ in self._health.values()):
            raise ValueError("Health track not found on sheet.")
        marked = []
        for lvl in HEALTH_LEVELS:
            if count <= 0:
                break
            li, cur_mark = self._health[lvl]
            if li is None or cur_mark != MARK_EMPTY:
                continue
            self._sub_line(
                li,
                r"(\|\s*)([○●/*])(\s*\|?\s*$)",
                lambda m, mk=mark: m.group(1) + mk + m.group(3),
            )
            self._health[lvl] = (li, mark)
            marked.append(lvl)
            count -= 1
        return marked

    def heal_health(self, count):
        """Clear `count` Health levels, from Incapacitated upward. Returns levels healed."""
        if not any(li is not None for li, _ in self._health.values()):
            raise ValueError("Health track not found on sheet.")
        healed = []
        for lvl in reversed(HEALTH_LEVELS):
            if count <= 0:
                break
            li, cur_mark = self._health[lvl]
            if li is None or cur_mark == MARK_EMPTY:
                continue
            self._sub_line(
                li,
                r"(\|\s*)([○●/*])(\s*\|?\s*$)",
                lambda m: m.group(1) + MARK_EMPTY + m.group(3),
            )
            self._health[lvl] = (li, MARK_EMPTY)
            healed.append(lvl)
            count -= 1
        return healed

    # ── I/O ───────────────────────────────────────────────────────────────────

    def text(self):
        return "\n".join(self._lines) + "\n"

    def save(self):
        if self._dirty:
            self.path.write_text(self.text(), encoding="utf-8")
            self._dirty = False


# ── Logging ───────────────────────────────────────────────────────────────────

def _day_tag(day):
    return f"Day {day}" if day is not None else "Day ?"


def append_log(log_path, line):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text(
            "# Resource log\n\n"
            "> GM-only. Every pool mutation, day-stamped and reasoned.\n"
            "> Never hand to an `npc-actor`; never index at --scope public.\n\n",
            encoding="utf-8",
        )
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Pool dispatch ─────────────────────────────────────────────────────────────

def _pool_get_set(sheet, pool):
    """Return (get_fn, set_fn, max_val) for a normalised pool name."""
    if pool == "wp":
        if sheet.wp_current is None:
            raise ValueError("Willpower not found on sheet.")
        return lambda: sheet.wp_current, sheet.set_wp, sheet.wp_rating
    if pool == "quint":
        if sheet.quint is None:
            raise ValueError("Quintessence not found on sheet.")
        return lambda: sheet.quint, sheet.set_quint, sheet.quint_max
    if pool == "paradox":
        if sheet.paradox is None:
            raise ValueError("Paradox not found on sheet.")
        return lambda: sheet.paradox, sheet.set_paradox, sheet.paradox_max
    raise ValueError(f"Unknown pool {pool!r}.")


# ── Operations ────────────────────────────────────────────────────────────────

def render_show(sheet):
    """Build the `--show` report as an ASCII-safe string.

    Returns ASCII only (no ● / ○) so it can be printed to a cp1252 console
    without crashing. The sheet *file* still stores the real glyphs.
    """
    lines = []
    if sheet.wp_rating is not None:
        pips = _ascii(_pips(sheet.wp_current, sheet.wp_rating))
        lines.append(f"Willpower:    [{pips}] ({sheet.wp_current}/{sheet.wp_rating})")
    if sheet.quint is not None:
        lines.append(f"Quintessence: {sheet.quint} / {sheet.quint_max}")
    if sheet.paradox is not None:
        lines.append(f"Paradox:      {sheet.paradox} / {sheet.paradox_max}")
    lines.append("\nHealth:")
    lines.append(_ascii(sheet.health_summary()))
    wp = sheet.wound_penalty()
    if wp is None:
        lines.append("\nStatus: INCAPACITATED")
    elif wp < 0:
        lines.append(f"\nWound penalty: {wp} dice")
    else:
        lines.append("\nWound penalty: none")
    return "\n".join(lines)


def op_show(sheet):
    print(render_show(sheet))


def op_spend(sheet, pool, amount, day, reason, log_path, dry_run):
    get, set_fn, _mx = _pool_get_set(sheet, pool)
    cur = get()
    if amount > cur:
        raise ValueError(f"Cannot spend {amount} {pool} — only {cur} available.")
    new = cur - amount
    label = f"{pool.upper()} {cur}->{new} (spend {amount})"
    if reason:
        label += f" -- {reason}"
    tag = f"- [{_day_tag(day)}] {label}"
    print(tag)
    if not dry_run:
        set_fn(new)
        append_log(log_path, tag)


def op_gain(sheet, pool, amount, day, reason, log_path, dry_run):
    get, set_fn, mx = _pool_get_set(sheet, pool)
    cur = get()
    new = cur + amount
    capped = mx is not None and new > mx
    if capped:
        new = mx
    label = f"{pool.upper()} {cur}->{new} (gain {amount}" + (" -- capped at max" if capped else "") + ")"
    if reason:
        label += f" -- {reason}"
    tag = f"- [{_day_tag(day)}] {label}"
    print(tag)
    if not dry_run:
        set_fn(new)
        append_log(log_path, tag)


def op_rest(sheet, full, cfg, day, reason, log_path, dry_run):
    if sheet.wp_rating is None:
        raise ValueError("Willpower not found on sheet.")
    cur = sheet.wp_current
    new = sheet.wp_rating if full else min(cur + cfg["wp_rest"], sheet.wp_rating)
    if new == cur:
        print(f"  WP already at {'max' if full else 'rest cap'} ({cur}/{sheet.wp_rating}). No change.")
        return
    label = f"WP {cur}->{new} (rest{' full' if full else ''})"
    if reason:
        label += f" -- {reason}"
    tag = f"- [{_day_tag(day)}] {label}"
    print(tag)
    if not dry_run:
        sheet.set_wp(new)
        append_log(log_path, tag)


def op_node(sheet, rating, day, reason, log_path, dry_run):
    if sheet.quint is None:
        raise ValueError("Quintessence not found on sheet.")
    cur = sheet.quint
    mx = sheet.quint_max
    gain = min(rating, mx - cur)
    if gain <= 0:
        print(f"  Quintessence already at max ({cur}/{mx}). No change.")
        return
    new = cur + gain
    label = f"Quint {cur}->{new} (Node rating {rating})"
    if reason:
        label += f" -- {reason}"
    tag = f"- [{_day_tag(day)}] {label}"
    print(tag)
    if not dry_run:
        sheet.set_quint(new)
        append_log(log_path, tag)


def op_damage(sheet, dtype, count, soak, day, reason, log_path, dry_run):
    if soak is not None and soak > 0:
        absorbed = min(soak, count)
        count -= absorbed
        print(f"  Soak absorbs {absorbed}; {count} {dtype} lands.")
    if count <= 0:
        print("  No damage lands.")
        return
    if dry_run:
        print(f"  Would mark {count} {dtype} on Health track.")
        return
    marked = sheet.mark_health(dtype, count)
    if not marked:
        print("  Health track full — no empty levels to mark.")
        return
    wp = sheet.wound_penalty()
    wp_str = "Incapacitated" if wp is None else (f"{wp} dice" if wp else "none")
    label = f"Health: {', '.join(marked)} marked {dtype} | wound penalty: {wp_str}"
    if reason:
        label += f" -- {reason}"
    tag = f"- [{_day_tag(day)}] {label}"
    print(tag)
    append_log(log_path, tag)


def op_heal(sheet, count, day, reason, log_path, dry_run):
    if dry_run:
        print(f"  Would heal {count} Health level(s).")
        return
    healed = sheet.heal_health(count)
    if not healed:
        print("  No marked Health levels to heal.")
        return
    wp = sheet.wound_penalty()
    wp_str = "Incapacitated" if wp is None else (f"{wp} dice" if wp else "none")
    label = f"Health: healed {', '.join(healed)} | wound penalty now: {wp_str}"
    if reason:
        label += f" -- {reason}"
    tag = f"- [{_day_tag(day)}] {label}"
    print(tag)
    append_log(log_path, tag)


def op_paradox(sheet, delta, day, reason, log_path, dry_run):
    if sheet.paradox is None:
        raise ValueError("Paradox not found on sheet.")
    cur = sheet.paradox
    new = max(0, min(cur + delta, sheet.paradox_max))
    if new == cur:
        print(f"  Paradox unchanged ({cur}).")
        return
    label = f"Paradox {cur}->{new} ({delta:+d})"
    if reason:
        label += f" -- {reason}"
    tag = f"- [{_day_tag(day)}] {label}"
    print(tag)
    if not dry_run:
        sheet.set_paradox(new)
        append_log(log_path, tag)


# ── Root finder ───────────────────────────────────────────────────────────────

def _find_root():
    root = Path.cwd()
    for cand in [root, *root.parents]:
        if (cand / "CLAUDE.md").exists() or (cand / "Game").is_dir():
            return cand
    return root


# ── Self-test ─────────────────────────────────────────────────────────────────

_SAMPLE_SHEET = """\
# Character Sheet

## Pools

- **Willpower** ●●●●●○○○○○ (Rating 10) — **Current pool: 5 / 10** *(spend 1 for +1 automatic success)*
- **Quintessence:** 7 / **Paradox:** 2 *(track 0–20; permanent max 10)*

## Health

| Level         | Penalty | Marked |
|---------------|---------|--------|
| Bruised       | —       | ○      |
| Hurt          | -1      | ○      |
| Injured       | -1      | ○      |
| Wounded       | -2      | ○      |
| Mauled        | -2      | ○      |
| Crippled      | -5      | ○      |
| Incapacitated | —       | ○      |

## Advancement

*(XP log here)*
"""


def _self_test():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Game").mkdir()
        char_dir = root / "Character"
        char_dir.mkdir()
        sheet_path = char_dir / "sheet.md"
        log_path = char_dir / "resource-log.md"

        def make_sheet():
            sheet_path.write_text(_SAMPLE_SHEET, encoding="utf-8")
            return Sheet(sheet_path)

        # ── 1. Round-trip: spend changes only the targeted number/glyph ──────
        s = make_sheet()
        assert s.wp_rating == 10 and s.wp_current == 5, f"WP parse: {s.wp_rating}/{s.wp_current}"
        assert s.quint == 7 and s.quint_max == 20, f"Quint parse: {s.quint}/{s.quint_max}"
        assert s.paradox == 2, f"Paradox parse: {s.paradox}"

        s.set_wp(4)
        new_text = s.text()
        orig_lines = _SAMPLE_SHEET.splitlines()
        new_lines = new_text.splitlines()
        changed = [i for i, (o, n) in enumerate(zip(orig_lines, new_lines)) if o != n]
        assert len(changed) == 1, f"Expected 1 changed line, got {len(changed)}: {changed}"
        assert "Current pool: 4 / 10" in new_lines[changed[0]], new_lines[changed[0]]
        assert "●●●●○○○○○○" in new_lines[changed[0]], new_lines[changed[0]]

        # ── 2. Clamp / guard ──────────────────────────────────────────────────
        s2 = make_sheet()
        try:
            s2.set_wp(11)
            assert False, "Should have raised for WP > rating"
        except ValueError:
            pass
        try:
            s2.set_wp(-1)
            assert False, "Should have raised for WP < 0"
        except ValueError:
            pass
        # Gain beyond max clamps
        s2.set_quint(20)
        assert s2.quint == 20
        s2.set_quint(25)  # should clamp to 20
        assert s2.quint == 20, f"Expected 20, got {s2.quint}"

        # ── 3. Rest rule: adds wp_rest (default 1), capped at rating ─────────
        cfg = load_config(root)
        assert cfg["wp_rest"] == 1
        s3 = make_sheet()
        s3.set_wp(9)
        op_rest(s3, full=False, cfg=cfg, day=1, reason=None, log_path=log_path, dry_run=False)
        assert s3.wp_current == 10, f"Expected 10 after rest, got {s3.wp_current}"

        s3b = make_sheet()
        s3b.set_wp(2)
        op_rest(s3b, full=True, cfg=cfg, day=1, reason=None, log_path=log_path, dry_run=False)
        assert s3b.wp_current == 10, f"Expected 10 after full rest, got {s3b.wp_current}"

        # ── 4. Node rule: refills Quint by ≤ rating, capped at max ───────────
        s4 = make_sheet()
        s4.set_quint(5)
        op_node(s4, rating=3, day=1, reason="Stadtbad", log_path=log_path, dry_run=False)
        assert s4.quint == 8, f"Expected 8 (5+3), got {s4.quint}"

        s4b = make_sheet()
        s4b.set_quint(19)
        op_node(s4b, rating=5, day=1, reason=None, log_path=log_path, dry_run=False)
        assert s4b.quint == 20, f"Expected 20 (capped), got {s4b.quint}"

        # Node doesn't come from rest
        s4c = make_sheet()
        q_before = s4c.quint
        op_rest(s4c, full=False, cfg=cfg, day=1, reason=None, log_path=log_path, dry_run=False)
        assert s4c.quint == q_before, "Quint must not change on --rest"

        # ── 5. Health: damage fills in order; wound penalty derived correctly ─
        s5 = make_sheet()
        marked = s5.mark_health("lethal", 2)
        assert marked == ["Bruised", "Hurt"], f"Expected Bruised+Hurt, got {marked}"
        assert s5._health["Bruised"][1] == "/"
        assert s5._health["Hurt"][1] == "/"
        assert s5._health["Injured"][1] == MARK_EMPTY
        assert s5.wound_penalty() == -1, f"Expected -1 (Hurt), got {s5.wound_penalty()}"

        # Soak step
        s5b = make_sheet()
        op_damage(s5b, "bashing", 4, soak=2, day=1, reason=None, log_path=log_path, dry_run=False)
        n_marked = sum(1 for lvl in HEALTH_LEVELS if s5b._health[lvl][1] != MARK_EMPTY)
        assert n_marked == 2, f"Expected 2 marked after 4 bashing / soak 2, got {n_marked}"

        # Heal from bottom upward
        s5c = make_sheet()
        s5c.mark_health("lethal", 4)   # Bruised Hurt Injured Wounded
        healed = s5c.heal_health(2)
        assert healed == ["Wounded", "Injured"], f"Expected Wounded+Injured, got {healed}"
        assert s5c._health["Injured"][1] == MARK_EMPTY
        assert s5c._health["Bruised"][1] == "/"

        # ── 6. Digest override changes recovery numbers ───────────────────────
        (root / "Game" / "resource-rules.json").write_text(
            json.dumps({"wp_rest": 3}), encoding="utf-8"
        )
        cfg2 = load_config(root)
        assert cfg2["wp_rest"] == 3, f"Expected 3 from override, got {cfg2['wp_rest']}"

        s6 = make_sheet()
        s6.set_wp(5)
        op_rest(s6, full=False, cfg=cfg2, day=2, reason=None, log_path=log_path, dry_run=False)
        assert s6.wp_current == 8, f"Expected 8 (5+3 override), got {s6.wp_current}"

        # ── 7. Day inference ──────────────────────────────────────────────────
        assert current_day(root) is None  # no current-scene.md yet
        (root / "Game" / "current-scene.md").write_text("**Day 14** — evening.", encoding="utf-8")
        assert current_day(root) == 14

        # ── 8. Firewall: resource-log.md must classify as secret or be skipped
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            import memory_index
            vis, _owner, _ftype = memory_index.classify("Character/resource-log.md")
            assert vis in ("secret", None), (
                f"Character/resource-log.md classified as {vis!r}; must be 'secret' or skipped"
            )
        except ImportError:
            pass  # memory_index not importable in isolated test environment

        # ── 9. `--show` output is ASCII-safe (cp1252 console can't crash) ─────
        s9 = make_sheet()
        s9.mark_health("bashing", 1)   # marks Bruised with ● in the file
        report = render_show(s9)
        assert report.isascii(), f"render_show must be ASCII-only; got: {report!r}"
        # encoding to cp1252 must not raise (the actual crash this guards against)
        report.encode("cp1252")
        # but the file itself keeps the real glyphs
        assert "●" in s9.text(), "the sheet file must still store the real glyph"

    print("resources self-test: OK")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv):
    ap = argparse.ArgumentParser(
        prog="resources.py",
        description="Deterministic resource tracker for the Storyteller GM.",
    )
    ap.add_argument("--show", action="store_true", help="print current resources and wound penalty")
    ap.add_argument("--spend", nargs=2, metavar=("POOL", "N"), help="spend N from POOL")
    ap.add_argument("--gain",  nargs=2, metavar=("POOL", "N"), help="gain N into POOL")
    ap.add_argument("--rest",  action="store_true", help="apply WP rest recovery")
    ap.add_argument("--full",  action="store_true", help="with --rest: refill WP to max")
    ap.add_argument("--node",  type=int, metavar="RATING", help="refill Quint from a Node")
    ap.add_argument("--damage", nargs=2, metavar=("TYPE", "N"),
                    help="mark Health levels (bashing / lethal / aggravated)")
    ap.add_argument("--soak", type=int, metavar="N",
                    help="with --damage: pre-rolled soak successes to subtract")
    ap.add_argument("--heal",  type=int, metavar="N", help="heal N Health levels")
    ap.add_argument("--paradox", type=str, metavar="DELTA",
                    help="adjust Paradox by +N or -N")
    ap.add_argument("--reason", type=str, help="reason text appended to the log entry")
    ap.add_argument("--day",    type=int, help="day stamp (default: read from current-scene.md)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would change without writing anything")
    ap.add_argument("--sheet",   type=str,
                    help="path to the sheet to operate on (default: Character/sheet.md)")
    ap.add_argument("--self-test", action="store_true", help="run built-in assertions and exit")
    ns = ap.parse_args(argv[1:])

    if ns.self_test:
        return _self_test()

    root = _find_root()
    cfg = load_config(root)
    sheet_path = Path(ns.sheet) if ns.sheet else root / "Character" / "sheet.md"
    log_path = sheet_path.parent / "resource-log.md"
    day = ns.day if ns.day is not None else current_day(root)
    dry = ns.dry_run

    try:
        sheet = Sheet(sheet_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    has_op = bool(
        ns.spend or ns.gain or ns.rest
        or (ns.node is not None)
        or ns.damage
        or (ns.heal is not None)
        or ns.paradox
    )

    try:
        if ns.show or not has_op:
            op_show(sheet)
            return 0

        if ns.spend:
            pool_raw, n_str = ns.spend
            pool = POOL_ALIASES.get(pool_raw.lower())
            if not pool:
                print(f"Error: unknown pool {pool_raw!r}", file=sys.stderr)
                return 1
            op_spend(sheet, pool, int(n_str), day, ns.reason, log_path, dry)

        elif ns.gain:
            pool_raw, n_str = ns.gain
            pool = POOL_ALIASES.get(pool_raw.lower())
            if not pool:
                print(f"Error: unknown pool {pool_raw!r}", file=sys.stderr)
                return 1
            op_gain(sheet, pool, int(n_str), day, ns.reason, log_path, dry)

        elif ns.rest:
            op_rest(sheet, ns.full, cfg, day, ns.reason, log_path, dry)

        elif ns.node is not None:
            op_node(sheet, ns.node, day, ns.reason, log_path, dry)

        elif ns.damage:
            dtype, n_str = ns.damage
            op_damage(sheet, dtype.lower(), int(n_str), ns.soak, day, ns.reason, log_path, dry)

        elif ns.heal is not None:
            op_heal(sheet, ns.heal, day, ns.reason, log_path, dry)

        elif ns.paradox is not None:
            try:
                delta = int(ns.paradox)
            except ValueError:
                print(f"Error: --paradox expects +N or -N, got {ns.paradox!r}", file=sys.stderr)
                return 1
            op_paradox(sheet, delta, day, ns.reason, log_path, dry)

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not dry:
        sheet.save()
    else:
        print("(dry-run: no files written)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
