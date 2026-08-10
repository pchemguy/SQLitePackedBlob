"""pblob_pack() payload, trailer, JSON-validation, and boundary tests."""

from __future__ import annotations

from collections.abc import Callable
import json
import sqlite3
import struct

import pytest


Scalar = Callable[[str, tuple[object, ...]], object]

FORMAT_CASES = [
    ("<f2", "<e", 0x01, 2),
    (">f2", ">e", 0x03, 2),
    ("<f4", "<f", 0x05, 4),
    (">f4", ">f", 0x07, 4),
]


@pytest.mark.parametrize(
    ("format_", "struct_format", "tag", "element_size"),
    FORMAT_CASES,
    ids=[case[0] for case in FORMAT_CASES],
)
def test_pack_exact_payload_bytes_and_trailer(
    scalar: Scalar,
    format_: str,
    struct_format: str,
    tag: int,
    element_size: int,
) -> None:
    values = [0.0, -0.0, 1.0, -2.0, 1.5, 0.1, 123.25]
    text = json.dumps(values, separators=(",", ":"))

    observed = scalar(
        "SELECT pblob_pack(?, ?)",
        (text, format_),
    )

    expected_payload = b"".join(
        struct.pack(struct_format, value)
        for value in values
    )
    expected = expected_payload + bytes([tag]) * 4

    assert observed == expected
    assert len(observed) == len(values) * element_size + 4


@pytest.mark.parametrize(
    ("format_", "tag", "element_size"),
    [
        ("<f2", 0x01, 2),
        (">f2", 0x03, 2),
        ("<f4", 0x05, 4),
        (">f4", 0x07, 4),
    ],
)
def test_empty_vector_is_trailer_only(
    scalar: Scalar,
    format_: str,
    tag: int,
    element_size: int,
) -> None:
    observed = scalar(
        "SELECT pblob_pack('[]', ?)",
        (format_,),
    )

    assert observed == bytes([tag]) * 4
    assert len(observed) == 4
    assert (len(observed) - 4) % element_size == 0


def test_default_pack_format_is_big_endian_f16(
    scalar: Scalar,
) -> None:
    default_blob = scalar(
        "SELECT pblob_pack('[1.25,-2.5]')",
    )
    explicit_blob = scalar(
        "SELECT pblob_pack('[1.25,-2.5]', '>f2')",
    )

    assert default_blob == explicit_blob
    assert default_blob[-4:] == b"\x03\x03\x03\x03"


@pytest.mark.parametrize(
    "json_text",
    [
        "0",
        "1.25",
        '"text"',
        "{}",
        "true",
        "null",
    ],
)
def test_pack_requires_top_level_array(
    scalar: Scalar,
    json_text: str,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^pblob_pack\(\) expects a JSON array$",
    ):
        scalar(
            "SELECT pblob_pack(?)",
            (json_text,),
        )


@pytest.mark.parametrize(
    "json_text",
    [
        "[null]",
        "[true]",
        "[false]",
        '["1.0"]',
        "[{}]",
        "[[]]",
        "[1,[2],3]",
        '[1,{"x":2},3]',
    ],
)
def test_pack_rejects_non_numeric_array_elements(
    scalar: Scalar,
    json_text: str,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^JSON array must contain only ordinary numbers$",
    ):
        scalar(
            "SELECT pblob_pack(?)",
            (json_text,),
        )


@pytest.mark.parametrize(
    "json_text",
    [
        "[+1]",
        "[.5]",
        "[1.]",
        "[0x10]",
        "[1,2,]",
        "[1/*comment*/,2]",
        "[Infinity]",
        "[-Infinity]",
        "[NaN]",
    ],
)
def test_pack_rejects_json5_input(
    scalar: Scalar,
    json_text: str,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^pblob_pack\(\) requires canonical JSON$",
    ):
        scalar(
            "SELECT pblob_pack(?)",
            (json_text,),
        )


@pytest.mark.parametrize(
    "json_text",
    [
        "",
        "[",
        "[1",
        "[1,,2]",
        '{"x":',
        "not-json",
    ],
)
def test_malformed_json_reports_sqlite_json_error(
    scalar: Scalar,
    json_text: str,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^malformed JSON$",
    ):
        scalar(
            "SELECT pblob_pack(?)",
            (json_text,),
        )


@pytest.mark.parametrize(
    ("format_", "json_text"),
    [
        ("<f2", "[1e100]"),
        (">f2", "[-1e100]"),
        ("<f4", "[1e100]"),
        (">f4", "[-1e100]"),
    ],
)
def test_pack_rejects_values_that_narrow_to_non_finite(
    scalar: Scalar,
    format_: str,
    json_text: str,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^numeric value out of range for pblob format$",
    ):
        scalar(
            "SELECT pblob_pack(?, ?)",
            (json_text, format_),
        )


@pytest.mark.parametrize(
    ("format_", "struct_format", "value"),
    [
        ("<f2", "<e", 65504.0),
        (">f2", ">e", -65504.0),
        ("<f2", "<e", 2.0**-14),
        (">f2", ">e", 2.0**-24),
        ("<f4", "<f", 3.4028234663852886e38),
        (">f4", ">f", -3.4028234663852886e38),
    ],
    ids=[
        "f2-max",
        "f2-min-negative-max",
        "f2-min-normal",
        "f2-min-subnormal",
        "f4-max",
        "f4-negative-max",
    ],
)
def test_pack_finite_boundaries_match_python_ieee_reference(
    scalar: Scalar,
    format_: str,
    struct_format: str,
    value: float,
) -> None:
    blob = scalar(
        "SELECT pblob_pack(?, ?)",
        (json.dumps([value]), format_),
    )

    expected = struct.pack(struct_format, value)

    assert blob[:-4] == expected


@pytest.mark.parametrize(
    ("format_", "struct_format", "value"),
    [
        ("<f2", "<e", 1e-50),
        (">f2", ">e", -1e-50),
        ("<f4", "<f", 1e-100),
        (">f4", ">f", -1e-100),
    ],
)
def test_underflow_is_encoded_not_reported_as_error(
    scalar: Scalar,
    format_: str,
    struct_format: str,
    value: float,
) -> None:
    blob = scalar(
        "SELECT pblob_pack(?, ?)",
        (json.dumps([value]), format_),
    )

    assert blob[:-4] == struct.pack(struct_format, value)


@pytest.mark.parametrize(
    ("format_", "struct_format", "tag"),
    [
        ("<f2", "<e", 0x01),
        (">f2", ">e", 0x03),
        ("<f4", "<f", 0x05),
        (">f4", ">f", 0x07),
    ],
)
def test_pack_preserves_negative_zero_bit_pattern(
    scalar,
    format_: str,
    struct_format: str,
    tag: int,
) -> None:
    blob = scalar(
        "SELECT pblob_pack('[-0.0]', ?)",
        (format_,),
    )

    expected_payload = struct.pack(struct_format, -0.0)

    assert blob[:-4] == expected_payload
    assert blob[-4:] == bytes([tag]) * 4
