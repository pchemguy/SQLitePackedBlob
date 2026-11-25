"""Shared fixtures and helpers for pblob SQLite-surface tests."""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable, Iterator
from contextlib import closing

import pytest


Scalar = Callable[[str, tuple[object, ...]], object]


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    """Return an isolated in-memory SQLite database with pblob registered.

    The test environment is expected to use the customized SQLite build in
    which the pblob auto-extension is already registered.  No loadable
    extension is loaded here: all tests exercise the same SQL surface that
    production callers use.
    """
    with closing(sqlite3.connect(":memory:")) as connection:
        try:
            connection.execute(
                "EXPLAIN SELECT pblob_pack(NULL), pblob_pack(NULL, NULL), pblob_unpack(NULL)"
            )
        except sqlite3.OperationalError as exc:
            pytest.fail(
                f"{sys.executable} (SQLite {sqlite3.sqlite_version}) could not resolve "
                f"the pblob SQL functions: {exc}. See pblob/tests/README.md.",
                pytrace=False,
            )
        yield connection


@pytest.fixture
def scalar(db: sqlite3.Connection) -> Scalar:
    """Return a helper executing scalar SQL against the test database."""

    def execute(
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> object:
        row = db.execute(sql, parameters).fetchone()
        assert row is not None
        return row[0]

    return execute
