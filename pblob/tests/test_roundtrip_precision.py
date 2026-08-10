"""Round-trip correctness and precision-loss characterization tests."""

from __future__ import annotations

from collections.abc import Callable
import json
import math
import struct

import pytest


Scalar = Callable[[str, tuple[object, ...]], object]

FORMAT_CASES = [
    ("<f2", "<e", 2.0**-11 + 2.0**-24),
    (">f2", ">e", 2.0**-11 + 2.0**-24),
    ("<f4", "<f", 2.0**-24),
    (">f4", ">f", 2.0**-24),
]

PRECISION_VALUES = [
    math.pi,
    math.e,
    1.0 / 3.0,
    -123.456789,
    0.00123456789,
    12345.6789,
]

EXACT_VALUES = [
    0.0,
    -0.0,
    0.5,
    -0.5,
    1.0,
    -2.0,
    8.0,
    1024.0,
]


def roundtrip(
    scalar: Scalar,
    values: list[float],
    format_: str,
) -> list[float]:
    text = json.dumps(values, separators=(",", ":"))
    result = scalar(
        "SELECT pblob_unpack(pblob_pack(?, ?))",
        (text, format_),
    )
    return json.loads(result)


@pytest.mark.parametrize(
    "format_",
    ["<f2", ">f2", "<f4", ">f4"],
)
def test_roundtrip_preserves_vector_length_and_order(
    scalar: Scalar,
    format_: str,
) -> None:
    source = [-10.5, -1.25, 0.0, 0.25, 1.5, 37.75]
    observed = roundtrip(scalar, source, format_)

    assert len(observed) == len(source)
    assert observed == source


@pytest.mark.parametrize(
    "format_",
    ["<f2", ">f2", "<f4", ">f4"],
)
def test_exactly_representable_values_are_lossless(
    scalar: Scalar,
    format_: str,
) -> None:
    observed = roundtrip(scalar, EXACT_VALUES, format_)

    assert observed == EXACT_VALUES
    assert math.copysign(1.0, observed[1]) == -1.0


@pytest.mark.parametrize(
    ("format_", "struct_format", "_relative_bound"),
    FORMAT_CASES,
    ids=[case[0] for case in FORMAT_CASES],
)
@pytest.mark.parametrize(
    "value",
    PRECISION_VALUES,
    ids=[
        "pi",
        "e",
        "one-third",
        "negative-123",
        "small-decimal",
        "large-decimal",
    ],
)
def test_roundtrip_matches_independent_ieee_reference_exactly(
    scalar: Scalar,
    format_: str,
    struct_format: str,
    _relative_bound: float,
    value: float,
) -> None:
    observed = roundtrip(scalar, [value], format_)[0]
    expected = struct.unpack(
        struct_format,
        struct.pack(struct_format, value),
    )[0]

    assert observed == expected


@pytest.mark.parametrize(
    ("format_", "_struct_format", "relative_bound"),
    FORMAT_CASES,
    ids=[case[0] for case in FORMAT_CASES],
)
@pytest.mark.parametrize(
    "value",
    PRECISION_VALUES,
    ids=[
        "pi",
        "e",
        "one-third",
        "negative-123",
        "small-decimal",
        "large-decimal",
    ],
)
def test_observed_relative_precision_loss_is_within_binary_format_bound(
    scalar: Scalar,
    format_: str,
    _struct_format: str,
    relative_bound: float,
    value: float,
) -> None:
    observed = roundtrip(scalar, [value], format_)[0]
    relative_error = abs(observed - value) / abs(value)

    assert relative_error <= relative_bound, (
        f"{format_}: relative error {relative_error:.17g} exceeds "
        f"expected bound {relative_bound:.17g} for {value!r}; "
        f"observed={observed!r}"
    )


@pytest.mark.parametrize(
    "format_",
    ["<f2", ">f2"],
)
def test_f16_precision_loss_is_consistent_with_11_significand_bits(
    scalar: Scalar,
    format_: str,
) -> None:
    observed = roundtrip(scalar, PRECISION_VALUES, format_)

    errors = [
        abs(actual - original) / abs(original)
        for original, actual in zip(PRECISION_VALUES, observed, strict=True)
    ]

    assert max(errors) <= 2.0**-11 + 2.0**-24
    assert any(error > 2.0**-24 for error in errors)


@pytest.mark.parametrize(
    "format_",
    ["<f4", ">f4"],
)
def test_f32_precision_loss_is_consistent_with_24_significand_bits(
    scalar: Scalar,
    format_: str,
) -> None:
    observed = roundtrip(scalar, PRECISION_VALUES, format_)

    errors = [
        abs(actual - original) / abs(original)
        for original, actual in zip(PRECISION_VALUES, observed, strict=True)
    ]

    assert max(errors) <= 2.0**-24
    assert any(error > 0.0 for error in errors)


@pytest.mark.parametrize(
    ("f16_format", "f32_format"),
    [
        ("<f2", "<f4"),
        (">f2", ">f4"),
    ],
    ids=["little-endian", "big-endian"],
)
def test_f16_has_no_better_precision_than_f32_for_same_inputs(
    scalar: Scalar,
    f16_format: str,
    f32_format: str,
) -> None:
    f16 = roundtrip(scalar, PRECISION_VALUES, f16_format)
    f32 = roundtrip(scalar, PRECISION_VALUES, f32_format)

    f16_errors = [
        abs(actual - original)
        for original, actual in zip(PRECISION_VALUES, f16, strict=True)
    ]
    f32_errors = [
        abs(actual - original)
        for original, actual in zip(PRECISION_VALUES, f32, strict=True)
    ]

    assert all(
        half_error >= single_error
        for half_error, single_error in zip(
            f16_errors,
            f32_errors,
            strict=True,
        )
    )
    assert any(
        half_error > single_error
        for half_error, single_error in zip(
            f16_errors,
            f32_errors,
            strict=True,
        )
    )


@pytest.mark.parametrize(
    ("format_", "struct_format", "values"),
    [
        (
            "<f2",
            "<e",
            [2.0**-24, 2.0**-23, 2.0**-14, 65504.0],
        ),
        (
            ">f2",
            ">e",
            [2.0**-24, 2.0**-23, 2.0**-14, 65504.0],
        ),
        (
            "<f4",
            "<f",
            [2.0**-149, 2.0**-126, 1.0, 3.4028234663852886e38],
        ),
        (
            ">f4",
            ">f",
            [2.0**-149, 2.0**-126, 1.0, 3.4028234663852886e38],
        ),
    ],
    ids=["f16-le", "f16-be", "f32-le", "f32-be"],
)
def test_roundtrip_ieee_boundary_values(
    scalar: Scalar,
    format_: str,
    struct_format: str,
    values: list[float],
) -> None:
    observed = roundtrip(scalar, values, format_)
    expected = [
        struct.unpack(
            struct_format,
            struct.pack(struct_format, value),
        )[0]
        for value in values
    ]

    assert observed == expected


@pytest.mark.parametrize(
    "format_",
    ["<f2", ">f2", "<f4", ">f4"],
)
def test_large_vector_roundtrip(
    scalar: Scalar,
    format_: str,
) -> None:
    values = [(i - 256) / 37.0 for i in range(512)]
    observed = roundtrip(scalar, values, format_)

    assert len(observed) == 512

    type_char = "e" if format_.endswith("2") else "f"
    prefix = "<" if format_.startswith("<") else ">"
    reference_format = prefix + type_char

    expected = [
        struct.unpack(
            reference_format,
            struct.pack(reference_format, value),
        )[0]
        for value in values
    ]

    assert observed == expected
