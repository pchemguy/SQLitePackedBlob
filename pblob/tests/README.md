# pblob SQLite-Surface Pytest Suite

This suite tests `pblob` exclusively through SQL executed by Python's `sqlite3` module against an in-memory database.

## Run the suite

Run from the repository root with pytest installed in the interpreter that will execute the queries. For the bundled Windows environment, build and select the checkout's DLL as described in the [Windows build](../../README.md#build-on-windows) and [pytest command](../../README.md#testing). That command starts a fresh Python process and preloads the absolute path to `out\bin\sqlite3.dll`. It applies to Windows Python builds whose `_sqlite3.pyd` imports `sqlite3.dll`. Keep the matching ICU and ZLIB runtime DLLs alongside it in `out\bin`.

For a Python interpreter already using the desired SQLite build, run:

```cmd
python -m pytest
```

### Check which runtime Python uses

The packaged shell and Python can use different SQLite builds. In a fresh interactive `python` session, check the interpreter, the SQLite snapshot, and the functions available on a new connection.

```python
import sqlite3
import sys

db = sqlite3.connect(":memory:")
print(sys.executable, sqlite3.sqlite_version)
print(db.execute("SELECT sqlite_source_id()").fetchone()[0])
print(db.execute("""
    SELECT name, narg, flags FROM pragma_function_list
    WHERE name IN ('pblob_pack', 'pblob_unpack') ORDER BY name, narg
""").fetchall())
db.close()
```

Typical registration rows for the packaged build are

```text
[('pblob_pack', 1, 2099200), ('pblob_pack', 2, 2099200), ('pblob_unpack', 1, 2099200)]
```

An empty list means the interpreter has no PBLOB functions. The reported flags include `SQLITE_DETERMINISTIC` and `SQLITE_INNOCUOUS`. SQLite's normal pragma output omits `SQLITE_RESULT_SUBTYPE`, so the suite checks its effect by nesting `pblob_unpack()` in `json_array()` with an expression index. A strict shell reporting `misuse of sqlite3_result_subtype() by pblob_unpack()` is consistent with an older PBLOB build. Check the cached `pblob.c` and regenerate the amalgamation. The upstream [Windows DLL path helper](https://github.com/pchemguy/SQLite-ICU-MinGW/blob/master/Current/MSVC/tool/sqlite3_dll_path.py) identifies the separate `sqlite3.dll` loaded by an interpreter.

## Coverage

| Test module | SQL behavior exercised |
| --- | --- |
| [`test_contract.py`](test_contract.py) | The three registered scalar signatures, UTF-8 encoding, deterministic and innocuous flags, SQL result types, NULL propagation, arity, and exact errors for invalid argument types and formats |
| [`test_pack.py`](test_pack.py) | The default `>f2` format, all four width/byte-order combinations, exact bytes against Python `struct`, trailer-only empty vectors, signed zero, finite bounds, overflow and underflow, malformed JSON, JSON5 syntax, and invalid array elements |
| [`test_unpack.py`](test_unpack.py) | Independent IEEE payloads built with Python `struct`, empty arrays, invalid trailers and payload lengths, external NaNs and infinities, and JSON array composition with and without an expression index |
| [`test_roundtrip_precision.py`](test_roundtrip_precision.py) | Exact and rounded values, binary16 midpoint cases, normal and subnormal boundaries, maximum finite values, relative precision of binary16 and binary32, and order and length through a 512-element round trip |

For the normal values tested, relative error is bounded by `2^-24` for binary32 and `2^-11 + 2^-24` for binary16. The half-precision reference rounds to binary32 first, matching the specified conversion path.
