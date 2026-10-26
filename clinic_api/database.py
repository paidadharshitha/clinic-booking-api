"""Short-lived SQLite connections and explicit transaction boundaries."""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

from clinic_api.errors import DomainError


class Database:
    def __init__(self, path: str | Path, *, timeout: float = 5.0) -> None:
        self.path = Path(path)
        self.timeout = timeout
        if str(path) == ":memory:":
            raise ValueError("Use a file-backed database; each operation has its own connection.")

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._initialize_once()
                return
            except DomainError as error:
                # Concurrent first startup may race when changing journal mode.
                # SQLite can return BUSY here without honoring its busy timeout.
                remaining = deadline - time.monotonic()
                if error.code != "DATABASE_BUSY" or remaining <= 0:
                    raise
                time.sleep(min(0.05, remaining))

    def _initialize_once(self) -> None:
        with self.connection() as connection:
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                connection.execute("PRAGMA journal_mode = WAL")
            # One versioned, transactional schema for this initial release.
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(f"Unsupported database schema version: {version}")
            if version == 1:
                return
            schema = files("clinic_api").joinpath("schema.sql").read_text(encoding="utf-8")
            connection.executescript(
                f"BEGIN IMMEDIATE;\n{schema}\nPRAGMA user_version = 1;\nCOMMIT;"
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        except sqlite3.OperationalError as error:
            # Extended codes retain the primary error code in the low byte.
            if getattr(error, "sqlite_errorcode", 0) & 0xFF in (
                sqlite3.SQLITE_BUSY,
                sqlite3.SQLITE_LOCKED,
            ):
                raise DomainError(
                    503, "DATABASE_BUSY", "The database is busy. Retry the request shortly."
                ) from error
            raise
        finally:
            if connection is not None:
                connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as connection:
            # Acquire the writer lock BEFORE reading state; works across processes.
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
