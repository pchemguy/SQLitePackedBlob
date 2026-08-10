"""Shared fixtures and helpers for pblob SQLite-surface tests."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator

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
    connection = sqlite3.connect(":memory:")

    try:
        connection.execute("SELECT pblob_unpack(pblob_pack('[]'))").fetchone()
    except sqlite3.Error as exc:
        connection.close()
        pytest.fail(
            "pblob SQL functions are not available in the sqlite3 runtime "
            f"used by this test process: {exc}"
        )

    try:
        yield connection
    finally:
        connection.close()


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
