"""Keystone test: the ported engine == the legacy Tools/ code, fixture-for-fixture.

This is the contract that lets us trust the SQLite port preserved the engine's
auditable fairness. The same agent `.fields` are fed to both the legacy
`Tools/world_tick.py` / `ledger.py` / `social.py` and the new `app/backend/engine`
modules, and the outputs are asserted identical: clock advance, FSM transitions,
selection priority, collision detection (modulo the deliberately-dropped
player-pressure rule), ledger control math, social BFS, and the firewall.

Run: python -m pytest app/backend/tests/test_parity.py
 or: python app/backend/tests/test_parity.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))                       # for `app.backend...`
sys.path.insert(0, str(ROOT / "Tools"))             # for legacy world_tick/ledger/social

import world_tick as legacy_tick           # noqa: E402
import ledger as legacy_ledger             # noqa: E402
import social as legacy_social             # noqa: E402

from app.backend.engine import tick as new_tick          # noqa: E402
from app.backend.engine import ledger as new_ledger      # noqa: E402
from app.backend.engine import social as new_social      # noqa: E402
from app.backend.engine.agent import Agent as NewAgent   # noqa: E402


# Fixture agent definitions as raw `.fields` dicts (the shared shape).
FIXTURES = {
    "mara": {
        "living": True, "state": "scheming",
        "goal": {"pursue": "control", "target": "harbor-council",
                 "success": "holds the swing vote before the festival"},
        "clock": {"filled": 2, "total": 6}, "advances_when": "dawdle",
        "salience": 4, "group": "anarch",
        "resources": {"influence": 2, "secrets": 4},
        "mood": {"confidence": 3, "desperation": 1},
        "relationships": {"vance": {"tie": "rival", "weight": -4,
                                    "note": "the one person who can block the seat"},
                          "bryce": {"tie": "ally", "weight": 3}},
        "states": {"scheming": {"to": "moving", "when": "clock>=3"},
                   "moving": {"to": "confronting", "when": "clock>=6"}},
    },
    "vance": {
        "living": True, "state": "scheming",
        "goal": {"pursue": "control", "target": "harbor-council"},
        "clock": {"filled": 1, "total": 4}, "advances_when": "always",
        "salience": 3, "resources": {"muscle": 3},
        "states": {"scheming": {"to": "moving", "when": "clock>=2"}},
    },
    "bryce": {
        "living": True, "state": "scheming",
        "goal": {"pursue": "control", "target": "harbor-council"},
        "clock": {"filled": 0, "total": 5}, "advances_when": "dawdle",
        "salience": 2, "group": "anarch",
        "relationships": {"mara": {"tie": "ally", "weight": 3}},
    },
    "sabine": {
        "living": True, "state": "moving",
        "goal": {"pursue": "destroy", "target": "diana",
                 "success": "keeps Daniel-the-bridge hers without revealing the cult"},
        "clock": {"filled": 3, "total": 6}, "advances_when": "always",
        "salience": 5,
        "relationships": {"kira": {"tie": "grudge", "weight": -5},
                          "diana": {"tie": "wary", "weight": -2}},
        "states": {"moving": {"to": "confronting", "when": "clock>=4"}},
    },
    "kira": {
        "living": True, "state": "moving",
        "goal": {"pursue": "expose", "target": "diana"},
        "clock": {"filled": 2, "total": 3}, "advances_when": "always",
        "salience": 3,
        "relationships": {"sabine": {"tie": "grudge", "weight": -5}},
        "states": {"moving": {"to": "confronting", "when": "clock>=3"}},
    },
}


def _legacy_agents():
    out = []
    for name, fields in FIXTURES.items():
        out.append(legacy_tick.Agent(name, copy.deepcopy(fields),
                                     Path(f"Cast/{name}/drives.md"), (0, 0)))
    return out


def _new_agents():
    return [NewAgent(name, copy.deepcopy(fields))
            for name, fields in FIXTURES.items()]


def _tick_all(agents, mod, elapsed=1, dawdle=True, fail=False):
    for a in agents:
        mod.tick(a, elapsed, dawdle, fail)


def test_tick_and_selection_parity():
    la, na = _legacy_agents(), _new_agents()
    _tick_all(la, legacy_tick)
    _tick_all(na, new_tick)

    for l, n in zip(la, na):
        assert l.fields["clock"] == n.fields["clock"], n.name
        assert l.fields["state"] == n.fields["state"], n.name
        assert l.advanced == n.advanced and l.transitioned == n.transitioned
        assert l.became_full == n.became_full
        assert legacy_tick.priority(l) == new_tick.priority(n), n.name

    lsel = sorted((a for a in la if legacy_tick.changed(a)),
                  key=lambda a: (-legacy_tick.priority(a), a.name))
    nsel = sorted((a for a in na if new_tick.changed(a)),
                  key=lambda a: (-new_tick.priority(a), a.name))
    assert [a.name for a in lsel] == [a.name for a in nsel]


def test_collision_parity_minus_player_rule():
    la, na = _legacy_agents(), _new_agents()
    _tick_all(la, legacy_tick)
    _tick_all(na, new_tick)

    lix = legacy_tick.detect_interactions(la)
    nix = new_tick.detect_interactions(na)

    def keyset(ix):
        return [(it.kind, tuple(sorted([it.a.name, it.b.name if it.b else "?"])), it.over)
                for it in ix if it.kind != "player-pressure"]

    assert keyset(lix) == keyset(nix), (keyset(lix), keyset(nix))
    # neither fixture targets the player, so the lists are fully identical here
    assert keyset(lix) == [(it.kind,
                            tuple(sorted([it.a.name, it.b.name if it.b else "?"])),
                            it.over) for it in nix]


def test_ledger_pressure_parity():
    pressures = {"mara": 9.0, "vance": 3.0, "bryce": 2.0}
    ll = legacy_ledger.Ledger("harbor-council", total=10)
    nl = new_ledger.Ledger("harbor-council", total=10)
    lr = legacy_ledger.apply_pressure(ll, dict(pressures), day=5)
    nr = new_ledger.apply_pressure(nl, dict(pressures), day=5)
    assert lr == nr, (lr, nr)
    assert ll.control == nl.control and ll.holder == nl.holder
    assert ll.history == nl.history and ll.phase() == nl.phase()


def test_social_graph_and_firewall_parity():
    la, na = _legacy_agents(), _new_agents()
    lg, _ = legacy_social.build_graph(agents=la)
    ng, _ = new_social.build_graph(na)
    assert lg == ng, (lg, ng)

    lgraph, lby = legacy_social.build_graph(agents=la)
    ngraph, nby = new_social.build_graph(na)
    ll = legacy_social.who_learns(lgraph, ["mara"], max_hops=2, by_name=lby)
    nl = new_social.who_learns(ngraph, ["mara"], max_hops=2, by_name=nby)
    assert ll == nl, (ll, nl)

    # firewall: a headline echoing sabine's secret success must be rejected by both
    lforb = legacy_social._forbidden_texts(la)
    nforb = new_social.forbidden_texts(na)
    assert set(lforb) == set(nforb)
    leak = "keeps Daniel-the-bridge hers without revealing the cult to the court"
    assert legacy_social.safe_headline(leak, lforb) == new_social.safe_headline(leak, nforb)
    assert not new_social.safe_headline(leak, nforb)
    safe = "has been quietly pursuing aims of their own lately"
    assert legacy_social.safe_headline(safe, lforb) == new_social.safe_headline(safe, nforb)
    assert new_social.safe_headline(safe, nforb)


if __name__ == "__main__":
    test_tick_and_selection_parity()
    test_collision_parity_minus_player_rule()
    test_ledger_pressure_parity()
    test_social_graph_and_firewall_parity()
    print("parity self-test: OK")
