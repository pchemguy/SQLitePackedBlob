"""pblob_unpack() decoding, trailer validation, and malformed-BLOB tests."""

from __future__ import annotations

from collections.abc import Callable
import json
import math
import sqlite3
import struct

import pytest


Scalar = Callable[[str, tuple[object, ...]], object]

FORMAT_CASES = [
    ("<f2", "<e", 0x01),
    (">f2", ">e", 0x03),
    ("<f4", "<f", 0x05),
    (">f4", ">f", 0x07),
]


@pytest.mark.parametrize(
    ("format_", "struct_format", "tag"),
    FORMAT_CASES,
    ids=[case[0] for case in FORMAT_CASES],
)
def test_unpack_external_ieee_payload(
    scalar: Scalar,
    format_: str,
    struct_format: str,
    tag: int,
) -> None:
    source_values = [0.0, -0.0, 1.0, -2.0, 0.1, 1.0 / 3.0, 123.25]
    payload = b"".join(
        struct.pack(struct_format, x)
        for x in source_values
    )
    blob = payload + bytes([tag]) * 4

    text = scalar(
        "SELECT pblob_unpack(?)",
        (sqlite3.Binary(blob),),
    )

    observed = json.loads(text)
    expected = [
        struct.unpack(
            struct_format,
            struct.pack(struct_format, x),
        )[0]
        for x in source_values
    ]

    assert observed == expected
    assert math.copysign(1.0, observed[1]) == -1.0


@pytest.mark.parametrize(
    "tag",
    [0x01, 0x03, 0x05, 0x07],
    ids=["f2-le", "f2-be", "f4-le", "f4-be"],
)
def test_unpack_trailer_only_blob_returns_empty_array(
    scalar: Scalar,
    tag: int,
) -> None:
    blob = bytes([tag]) * 4

    assert scalar(
        "SELECT pblob_unpack(?)",
        (sqlite3.Binary(blob),),
    ) == "[]"


def test_unpack_result_is_json_text_with_array_subtype_semantics(
    scalar: Scalar,
) -> None:
    assert scalar(
        "SELECT json_type(pblob_unpack(pblob_pack('[1,2,3]', '<f4')))"
    ) == "array"


@pytest.mark.parametrize(
    "blob",
    [
        b"",
        b"\x01",
        b"\x01\x01",
        b"\x01\x01\x01",
    ],
)
def test_unpack_rejects_blob_shorter_than_trailer(
    scalar: Scalar,
    blob: bytes,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^pblob BLOB is too short$",
    ):
        scalar(
            "SELECT pblob_unpack(?)",
            (sqlite3.Binary(blob),),
        )


@pytest.mark.parametrize(
    "trailer",
    [
        b"\x01\x01\x01\x03",
        b"\x03\x03\x01\x03",
        b"\x05\x07\x05\x05",
        b"\x07\x07\x07\x05",
    ],
)
def test_unpack_rejects_non_repeated_trailer(
    scalar: Scalar,
    trailer: bytes,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^invalid pblob format trailer$",
    ):
        scalar(
            "SELECT pblob_unpack(?)",
            (sqlite3.Binary(trailer),),
        )


@pytest.mark.parametrize(
    "tag",
    [0x00, 0x02, 0x04, 0x06, 0x08, 0x09, 0xFF],
)
def test_unpack_rejects_unknown_repeated_tag(
    scalar: Scalar,
    tag: int,
) -> None:
    blob = bytes([tag]) * 4

    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^invalid pblob format metadata$",
    ):
        scalar(
            "SELECT pblob_unpack(?)",
            (sqlite3.Binary(blob),),
        )


@pytest.mark.parametrize(
    "blob",
    [
        b"\x00" + b"\x01" * 4,          # 1-byte payload for f2
        b"\x00\x00\x00" + b"\x01" * 4, # 3-byte payload for f2
        b"\x00" + b"\x05" * 4,          # 1-byte payload for f4
        b"\x00\x00" + b"\x07" * 4,     # 2-byte payload for f4
    ],
    ids=["f2-one-byte", "f2-three-byte", "f4-one-byte", "f4-two-byte"],
)
def test_unpack_rejects_payload_size_not_divisible_by_element_size(
    scalar: Scalar,
    blob: bytes,
) -> None:
    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^invalid pblob payload size$",
    ):
        scalar(
            "SELECT pblob_unpack(?)",
            (sqlite3.Binary(blob),),
        )


@pytest.mark.parametrize(
    ("payload", "tag"),
    [
        (struct.pack("<H", 0x7C00), 0x01),     # +Inf f16 LE
        (struct.pack(">H", 0xFC00), 0x03),     # -Inf f16 BE
        (struct.pack("<H", 0x7E00), 0x01),     # NaN f16 LE
        (struct.pack(">I", 0x7F800000), 0x07), # +Inf f32 BE
        (struct.pack("<I", 0xFF800000), 0x05), # -Inf f32 LE
        (struct.pack(">I", 0x7FC00000), 0x07), # NaN f32 BE
    ],
    ids=[
        "f16-pos-inf",
        "f16-neg-inf",
        "f16-nan",
        "f32-pos-inf",
        "f32-neg-inf",
        "f32-nan",
    ],
)
def test_unpack_rejects_non_finite_external_payload(
    scalar: Scalar,
    payload: bytes,
    tag: int,
) -> None:
    blob = payload + bytes([tag]) * 4

    with pytest.raises(
        sqlite3.OperationalError,
        match=r"^pblob contains non-finite value$",
    ):
        scalar(
            "SELECT pblob_unpack(?)",
            (sqlite3.Binary(blob),),
        )
