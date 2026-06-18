-- Ant Farm SQLite schema — the live runtime store for the living world.
--
-- State that used to live in markdown (Cast/<name>/drives.md, Game/plots.md,
-- Game/ledgers.md, …) lives here. Structured sub-objects (resources, mood,
-- relationships, FSM) are child tables; db/loader.py reassembles them into the
-- `.fields` dict the deterministic engine reads, so the ported algorithms run
-- unchanged. Prose blobs (profile/secrets/sheet/drives prose) ride as columns.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS worlds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    game          TEXT NOT NULL DEFAULT 'v20',     -- m20 | v20 | w20
    edition       TEXT DEFAULT '20th Anniversary',
    crossover     TEXT,                            -- JSON list of splats, or NULL
    play_mode     TEXT DEFAULT 'dramatist',
    tone          TEXT,
    premise       TEXT,
    lethality     TEXT DEFAULT 'medium',
    calendar      TEXT,
    current_day   INTEGER NOT NULL DEFAULT 1,
    gm_secrets_md TEXT DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS locations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id    INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    x           REAL NOT NULL DEFAULT 0.5,         -- schematic map coords, 0..1
    y           REAL NOT NULL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS agents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id      INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,                   -- stable entity id (unique per world)
    display_name  TEXT,
    kind          TEXT NOT NULL DEFAULT 'npc',     -- npc | faction
    living        INTEGER NOT NULL DEFAULT 1,
    state         TEXT,
    clock_filled  INTEGER NOT NULL DEFAULT 0,
    clock_total   INTEGER NOT NULL DEFAULT 0,
    advances_when TEXT DEFAULT 'dawdle',
    salience      INTEGER NOT NULL DEFAULT 1,
    group_id      TEXT,
    goal_pursue   TEXT,
    goal_target   TEXT,
    goal_success  TEXT,
    location_id   INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    -- prose blobs (GM split: profile is actor-safe; the rest are GM-only)
    profile_md    TEXT DEFAULT '',                 -- actor-safe: who they are, how they talk
    secrets_md    TEXT DEFAULT '',                 -- GM-only
    sheet_md      TEXT DEFAULT '',                 -- GM-only
    drives_prose_md TEXT DEFAULT '',               -- GM-only (Agenda / Reflection notes)
    UNIQUE (world_id, name)
);

CREATE TABLE IF NOT EXISTS agent_resources (
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    key      TEXT NOT NULL,
    value    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (agent_id, key)
);

CREATE TABLE IF NOT EXISTS agent_mood (
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    key      TEXT NOT NULL,
    value    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (agent_id, key)
);

CREATE TABLE IF NOT EXISTS relationships (
    agent_id   INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    target_ref TEXT NOT NULL,                      -- entity id (agent name / faction / location)
    tie        TEXT NOT NULL,
    weight     INTEGER NOT NULL DEFAULT 0,
    note       TEXT,
    PRIMARY KEY (agent_id, target_ref)
);

CREATE TABLE IF NOT EXISTS fsm_transitions (
    agent_id   INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    from_state TEXT NOT NULL,
    to_state   TEXT NOT NULL,
    guard      TEXT NOT NULL DEFAULT 'always',
    PRIMARY KEY (agent_id, from_state)
);

CREATE TABLE IF NOT EXISTS plots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id     INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    plot_key     TEXT NOT NULL,
    title        TEXT NOT NULL,
    participants TEXT DEFAULT '',
    stakes       TEXT DEFAULT '',
    state        TEXT DEFAULT 'forming',           -- forming | rising | climax | resolved
    clock_filled INTEGER DEFAULT 0,
    clock_total  INTEGER DEFAULT 0,
    surface      TEXT DEFAULT 'hidden',
    arc          TEXT,
    body_md      TEXT DEFAULT '',
    opened_day   INTEGER,
    closed_day   INTEGER,
    UNIQUE (world_id, plot_key)
);

CREATE TABLE IF NOT EXISTS developments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id  INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    day       INTEGER,
    agent     TEXT,
    headline  TEXT NOT NULL,
    body      TEXT DEFAULT '',
    surface   TEXT DEFAULT 'hidden',               -- now | soon | hidden
    escalate  INTEGER NOT NULL DEFAULT 0,
    drained   INTEGER NOT NULL DEFAULT 0,
    source    TEXT DEFAULT '',
    arc       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ledgers (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    entity   TEXT NOT NULL,
    total    INTEGER NOT NULL DEFAULT 10,
    holder   TEXT,
    phase    TEXT DEFAULT 'forming',
    UNIQUE (world_id, entity)
);

CREATE TABLE IF NOT EXISTS ledger_control (
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
    claimant  TEXT NOT NULL,                       -- agent name, or '_neutral'
    points    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ledger_id, claimant)
);

CREATE TABLE IF NOT EXISTS ledger_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
    day       INTEGER,
    text      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    day      INTEGER,
    text     TEXT NOT NULL
);

-- actor-safe "what I've learned about others" — written by social.propagate.
CREATE TABLE IF NOT EXISTS memory_observations (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    day      INTEGER,
    about    TEXT,
    text     TEXT NOT NULL,
    hops     INTEGER,
    UNIQUE (agent_id, text)                        -- idempotent propagation
);

CREATE TABLE IF NOT EXISTS timeline (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    day      INTEGER,
    text     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cost_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id     INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    day          INTEGER,
    templated    INTEGER DEFAULT 0,
    sonnet_beats INTEGER DEFAULT 0,
    opus_beats   INTEGER DEFAULT 0,
    notes        TEXT DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
