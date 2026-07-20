"""SQLite connection utilities for Volcanes."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from volcanoes.config import config


def get_connection(
    database_path: Path | None = None,
) -> sqlite3.Connection:
    """Create a configured SQLite connection."""

    path = database_path or config.database_path

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")

    return connection


@contextmanager
def database_session(
    database_path: Path | None = None,
) -> Iterator[sqlite3.Connection]:
    """Provide a transactional SQLite session."""

    connection = get_connection(database_path)

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
