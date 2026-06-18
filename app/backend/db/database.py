"""SQLite connection + schema init for the Ant Farm.

Raw `sqlite3` (stdlib) keeps the engine dependency-light and faithful to the
campaign tool's pure-stdlib ethos. `row_factory = sqlite3.Row` so callers index
columns by name. Foreign keys are enforced per-connection.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_SCHEMA = Path(__file__).with_name("schema.sql")

DEFAULT_DB = os.environ.get(
    "ANTFARM_DB",
    str(Path(__file__).resolve().parents[2] / "antfarm.db"),
)


def connect(db_path=None):
    """Open a connection with row access by name and FKs enforced."""
    conn = sqlite3.connect(db_path or DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    """Create tables if they don't exist (idempotent)."""
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def get_db(db_path=None):
    """Connect and ensure the schema exists."""
    conn = connect(db_path)
    init_db(conn)
    return conn
