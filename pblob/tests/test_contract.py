"""SQL registration, arity, type, NULL, and format-contract tests."""

from __future__ import annotations

from collections.abc import Callable
import re
import sqlite3

import pytest


Scalar = Callable[[str, tuple[object, ...]], object]

FORMATS = ("<f2", ">f2", "<f4", ">f4")


def test_registered_sql_variants(db: sqlite3.Connection) -> None:
    rows = db.execute(
        """
        SELECT name, narg
        FROM pragma_function_list
        WHERE name IN ('pblob_pack', 'pblob_unpack')
        ORDER BY name, narg
        """
    ).fetchall()

    assert rows == [
        ("pblob_pack", 1),
        ("pblob_pack", 2),
        ("pblob_unpack", 1),
    ]


@pytest.mark.parametrize(
    ("sql", "expected_type"),
    [
        ("SELECT typeof(pblob_pack('[]'))", "blob"),
        ("SELECT typeof(pblob_pack('[]', '<f2'))", "blob"),
        ("SELECT typeof(pblob_unpack(pblob_pack('[]')))", "text"),
    ],
    ids=["pack-default", "pack-explicit", "unpack"],
)
def test_sql_result_types(
    scalar: Scalar,
    sql: str,
    expected_type: str,
) -> None:
    assert scalar(sql) == expected_type


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pblob_pack(NULL)",
        "SELECT pblob_pack(NULL, '<f2')",
        "SELECT pblob_unpack(NULL)",
    ],
    ids=["pack-default", "pack-explicit", "unpack"],
)
def test_null_propagation(
    scalar: Scalar,
    sql: str,
) -> None:
    assert scalar(sql) is None


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (1, "pblob_pack() JSON argument must be TEXT"),
        (1.25, "pblob_pack() JSON argument must be TEXT"),
        (sqlite3.Binary(b"[]"), "pblob_pack() JSON argument must be TEXT"),
    ],
    ids=["integer", "real", "blob"],
)
def test_pack_rejects_non_text_json_argument(
    scalar: Scalar,
    value: object,
    message: str,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=rf"^{re.escape(message)}$",
    ):
        scalar("SELECT pblob_pack(?)", (value,))


@pytest.mark.parametrize(
    "value",
    [1, 1.25, "not-a-blob"],
    ids=["integer", "real", "text"],
)
def test_unpack_rejects_non_blob_argument(
    scalar: Scalar,
    value: object,
) -> None:
    message = "pblob_unpack() argument must be BLOB"

    with pytest.raises(
        sqlite3.OperationalError,
        match=rf"^{re.escape(message)}$",
    ):
        scalar("SELECT pblob_unpack(?)", (value,))


@pytest.mark.parametrize("format_", FORMATS)
def test_all_explicit_formats_are_accepted(
    scalar: Scalar,
    format_: str,
) -> None:
    result = scalar(
        "SELECT pblob_pack('[1]', ?)",
        (format_,),
    )

    assert isinstance(result, bytes)


@pytest.mark.parametrize(
    "format_",
    [
        "",
        "f2",
        "f4",
        "<F2",
        ">F4",
        "=f2",
        "|f2",
        "<f8",
        ">f8",
        "<f16",
        "<f2 ",
        " <f2",
        "<f2\x00",
        "junk",
    ],
)
def test_invalid_format_string_reports_exact_error(
    scalar: Scalar,
    format_: str,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^invalid pblob format$",
    ):
        scalar(
            "SELECT pblob_pack('[1]', ?)",
            (format_,),
        )


@pytest.mark.parametrize(
    "format_value",
    [1, 1.5, sqlite3.Binary(b"<f2")],
    ids=["integer", "real", "blob"],
)
def test_non_text_format_reports_exact_error(
    scalar: Scalar,
    format_value: object,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^pblob format must be TEXT$",
    ):
        scalar(
            "SELECT pblob_pack('[1]', ?)",
            (format_value,),
        )


def test_null_explicit_format_reports_exact_error(
    scalar: Scalar,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^pblob format must not be NULL$",
    ):
        scalar("SELECT pblob_pack('[1]', NULL)")


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        (
            "SELECT pblob_pack()",
            "wrong number of arguments to function pblob_pack()",
        ),
        (
            "SELECT pblob_pack('[]', '<f2', 1)",
            "wrong number of arguments to function pblob_pack()",
        ),
        (
            "SELECT pblob_unpack()",
            "wrong number of arguments to function pblob_unpack()",
        ),
        (
            "SELECT pblob_unpack(X'01010101', 1)",
            "wrong number of arguments to function pblob_unpack()",
        ),
    ],
    ids=["pack-zero", "pack-three", "unpack-zero", "unpack-two"],
)
def test_invalid_arity_is_rejected_by_sqlite(
    scalar: Scalar,
    sql: str,
    message: str,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=rf"^{re.escape(message)}$",
    ):
        scalar(sql)
