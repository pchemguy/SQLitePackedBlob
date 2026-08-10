# pblob SQLite-Surface Pytest Suite

This suite tests `pblob` exclusively through SQL executed by Python's `sqlite3` module against an in-memory database.

## Runtime requirement

The Python process must be linked to / loading the customized SQLite build where `pblob` is already registered as an auto-extension. The fixture does not load a separate extension library.

Run:

```text
python -m pytest -q
```

## Coverage

The suite verifies:

- registration of `pblob_pack/1`, `pblob_pack/2`, and `pblob_unpack/1`;
- SQL types and NULL propagation;
- every supported format: `<f2`, `>f2`, `<f4`, `>f4`;
- default `pblob_pack(JSON)` behavior (`>f2`);
- exact packed payload bytes against Python `struct` IEEE `e`/`f` reference encodings;
- all four trailer encodings and trailer-only empty vectors;
- strict JSON array and numeric-element requirements;
- rejection of JSON5 input;
- malformed JSON;
- invalid SQL argument types, formats, and arities;
- malformed/unknown trailers and invalid payload lengths;
- finite-value overflow rejection and externally supplied NaN/Infinity rejection;
- signed zero, normal/subnormal boundaries, and maximum finite values;
- direct external-BLOB decoding independent of `pblob_pack()`;
- exact round-trip agreement with Python's IEEE conversion reference;
- quantitative precision loss:
    - binary32 relative error bounded by `2^-24` for tested normal values;
    - binary16 relative error bounded by `2^-11 + 2^-24`, accounting for the implementation's `double -> float -> half` conversion chain;
- comparison demonstrating that f16 does not outperform f32 precision for the same source values;
- a 512-element vector round-trip.
