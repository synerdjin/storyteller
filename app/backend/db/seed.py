"""Deterministic demo-world seeder — no model, no API key required.

Lets the whole app run end-to-end (map, inspector, ticks, ledgers, propagation,
god-hand) without the architect. It hand-builds a small colliding V20 world: two
rival brokers reaching for the same council seat, an ally, and a hunter-on-a-
grudge — enough tension that the metronome generates plot on the first tick.
The architect (directors/architect.py) is the real path; this is the offline one.
"""

from __future__ import annotations


def seed_demo_world(conn, name="Harbor of Ash (demo)"):
    """Create a small, colliding demo world; return its world_id."""
    wid = conn.execute(
        "INSERT INTO worlds (name, game, edition, play_mode, tone, premise, "
        "lethality, current_day, gm_secrets_md) VALUES (?,?,?,?,?,?,?,?,?)",
        (name, "v20", "20th Anniversary", "dramatist",
         "noir, slow-burn personal horror",
         "A harbor city's vampire court has an empty council seat; the Blood and "
         "the ambition around it are about to boil over.",
         "medium", 5,
         "GM ONLY: The old prince is already in torpor beneath the customs house; "
         "the 'empty seat' is emptier than anyone admits. Mara knows.")).lastrowid

    locs = {}
    for lname, desc, x, y in [
        ("The Customs House", "Seat of the court; the empty council chair.", 0.50, 0.30),
        ("The Salt Quarter", "Mara's territory of brokers and smugglers.", 0.25, 0.65),
        ("The Drylands", "Vance's muscle and the dockside gangs.", 0.75, 0.68),
        ("The Cistern", "Cold, forgotten, and not as empty as it looks.", 0.50, 0.85),
    ]:
        locs[lname] = conn.execute(
            "INSERT INTO locations (world_id, name, description, x, y) VALUES (?,?,?,?,?)",
            (wid, lname, desc, x, y)).lastrowid

    def agent(name, display, state, filled, total, aw, sal, group, pursue, target,
              success, loc, profile, secrets, resources, mood, rels, states):
        aid = conn.execute(
            "INSERT INTO agents (world_id, name, display_name, kind, living, state, "
            "clock_filled, clock_total, advances_when, salience, group_id, goal_pursue, "
            "goal_target, goal_success, location_id, profile_md, secrets_md, drives_prose_md) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wid, name, display, "npc", 1, state, filled, total, aw, sal, group,
             pursue, target, success, locs[loc], profile, secrets,
             f"Agenda: {success}")).lastrowid
        for k, v in resources.items():
            conn.execute("INSERT INTO agent_resources (agent_id, key, value) VALUES (?,?,?)",
                         (aid, k, v))
        for k, v in mood.items():
            conn.execute("INSERT INTO agent_mood (agent_id, key, value) VALUES (?,?,?)",
                         (aid, k, v))
        for tref, (tie, w, note) in rels.items():
            conn.execute(
                "INSERT INTO relationships (agent_id, target_ref, tie, weight, note) "
                "VALUES (?,?,?,?,?)", (aid, tref, tie, w, note))
        for frm, (to, guard) in states.items():
            conn.execute(
                "INSERT INTO fsm_transitions (agent_id, from_state, to_state, guard) "
                "VALUES (?,?,?,?)", (aid, frm, to, guard))
        return aid

    agent("mara", "Mara Vex", "scheming", 2, 4, "always", 4, "anarch",
          "control", "council-seat", "holds the swing vote before the festival",
          "The Salt Quarter",
          "Mara Vex runs the Salt Quarter's brokers with a velvet voice and an "
          "iron ledger. She speaks softly, never threatens twice, and remembers "
          "every debt. Openly: she wants a voice on the council.",
          "SECRET: Mara murdered her own sire for the seat and hid the body in "
          "the Cistern. She also knows the prince lies in torpor below.",
          {"influence": 3, "secrets": 4, "coin": 2}, {"confidence": 3, "desperation": 1},
          {"vance": ("rival", -4, "the one brute who can block the seat"),
           "bryce": ("ally", 3, "owes her, and means it"),
           "council-seat": ("wary", 1, "")},
          {"scheming": ("moving", "clock>=3"), "moving": ("confronting", "clock>=4")})

    agent("vance", "Aldous Vance", "scheming", 1, 4, "always", 3, "camarilla",
          "control", "council-seat", "takes the seat by force of presence",
          "The Drylands",
          "Aldous Vance is all shoulders and certainty, a Ventrue who confuses "
          "volume with authority. He runs the dockside gangs and believes the "
          "seat is his by right. Openly: he despises Mara's 'gutter politics.'",
          "SECRET: Vance is nearly bankrupt of Blood and leans on a ghoul "
          "lieutenant who is quietly selling him out.",
          {"muscle": 4, "coin": 1}, {"confidence": 4, "desperation": 2},
          {"mara": ("rival", -4, "gutter broker, beneath him"),
           "council-seat": ("wary", 1, "")},
          {"scheming": ("moving", "clock>=2"), "moving": ("confronting", "clock>=4")})

    agent("bryce", "Bryce Calloway", "watching", 0, 5, "dawdle", 2, "anarch",
          "protect", "mara", "keeps Mara alive and in play",
          "The Salt Quarter",
          "Bryce Calloway is Mara's fixer and conscience, a Brujah who'd rather "
          "talk than break a jaw but is very good at breaking jaws. Loyal, dry, tired.",
          "SECRET: Bryce suspects what Mara did to her sire and is terrified of "
          "the answer, so he never asks.",
          {"muscle": 3, "influence": 1}, {"confidence": 2, "desperation": 1},
          {"mara": ("ally", 4, "the only one who ever trusted him")},
          {"watching": ("moving", "clock>=3")})

    agent("calla", "Calla Renn", "hunting", 2, 3, "always", 4, None,
          "destroy", "vance", "puts Vance in the sun before he rises further",
          "The Drylands",
          "Calla Renn is a hunter who lost a brother to the dockside gangs and "
          "now moves through the harbor like a held breath. Quiet, patient, certain.",
          "SECRET: Calla is being fed information by Vance's own ghoul lieutenant, "
          "and doesn't know the lieutenant works for someone else again.",
          {"muscle": 2, "secrets": 3}, {"confidence": 3, "desperation": 3},
          {"vance": ("grudge", -5, "the face behind her brother's death")},
          {"hunting": ("striking", "clock>=3")})

    conn.commit()
    return wid
