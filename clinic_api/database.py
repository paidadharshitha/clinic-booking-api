"""SQLAlchemy sessions, explicit SQLite transactions, and versioned initialization."""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import ConnectionPoolEntry, NullPool

from clinic_api.errors import DomainError
from clinic_api.models import Base

SCHEMA_VERSION = 2


def configure_connection(connection: sqlite3.Connection, record: ConnectionPoolEntry) -> None:
    connection.execute("PRAGMA foreign_keys = ON")


class Database:
    def __init__(self, path: str | Path, *, timeout: float = 5.0) -> None:
        if str(path) == ":memory:":
            raise ValueError("Use a file-backed database; each operation has its own connection.")
        self.path = Path(path).resolve()
        self.timeout = timeout
        self.engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(self.path)),
            connect_args={"timeout": timeout, "isolation_level": None, "check_same_thread": False},
            poolclass=NullPool,
            hide_parameters=True,
        )
        event.listen(self.engine, "connect", configure_connection)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._initialize_once()
                return
            except DomainError as error:
                # Concurrent WAL initialization can return BUSY without waiting.
                remaining = deadline - time.monotonic()
                if error.code != "DATABASE_BUSY" or remaining <= 0:
                    raise
                time.sleep(min(0.05, remaining))

    def _initialize_once(self) -> None:
        with self.connection() as connection:
            if connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() != "wal":
                connection.exec_driver_sql("PRAGMA journal_mode = WAL")
            # Lock before reading the version: competing workers must not migrate twice.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
                if version not in (0, 1, SCHEMA_VERSION):
                    raise RuntimeError(f"Unsupported database schema version: {version}")
                if version == 0:
                    Base.metadata.create_all(connection)
                elif version == 1:
                    # Additive migration: original IDs, UTC values, and history stay intact.
                    connection.exec_driver_sql(
                        "ALTER TABLE clinics ADD COLUMN address VARCHAR(300)"
                    )
                    connection.exec_driver_sql(
                        "ALTER TABLE bookings ADD COLUMN patient_name VARCHAR(120)"
                    )
                    connection.exec_driver_sql(
                        "ALTER TABLE bookings ADD COLUMN patient_email VARCHAR(254)"
                    )
                    for table in Base.metadata.sorted_tables:
                        for index in table.indexes:
                            index.create(connection, checkfirst=True)
                connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        try:
            with self.engine.connect() as connection:
                yield connection
        except OperationalError as error:
            code = getattr(error.orig, "sqlite_errorcode", 0) & 0xFF
            if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise DomainError(
                    503, "DATABASE_BUSY", "The database is busy. Retry the request shortly."
                ) from error
            raise DomainError(
                503, "DATABASE_UNAVAILABLE", "The database is temporarily unavailable."
            ) from error

    @contextmanager
    def session(self, *, write: bool = False) -> Iterator[Session]:
        with (
            self.connection() as connection,
            Session(bind=connection, expire_on_commit=False) as session,
        ):
            # DBAPI implicit BEGIN is disabled. Explicit BEGIN protects reads too;
            # writers acquire SQLite's lock before any state or current-time check.
            session.execute(text("BEGIN IMMEDIATE" if write else "BEGIN"))
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def dispose(self) -> None:
        self.engine.dispose()
