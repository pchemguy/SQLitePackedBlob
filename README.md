---
url: https://chatgpt.com/c/6a79cc83-25dc-83eb-944c-5d819e7af573
---

# SQLite Packed Blob (`pblob`)

`pblob` is a small SQLite C extension for converting one-dimensional numeric JSON arrays to and from compact packed floating-point BLOBs.

It is intended primarily for storing embedding vectors and similar numeric arrays where:

* JSON is convenient for inspection and interchange;
* a packed binary representation is preferable for compact storage;
* binary16 (`f2`) or binary32 (`f4`) precision is sufficient;
* explicit little- or big-endian representation is desirable.

The extension is integrated directly into a customized SQLite amalgamation and registered as an auto-extension.

## SQL API

`pblob` provides three scalar-function signatures:

```sql
pblob_pack(json_vector, format) -> BLOB
pblob_pack(json_vector)         -> BLOB
pblob_unpack(blob_data)         -> TEXT
```

The explicit `format` argument accepts exactly:

```text
<f2    IEEE binary16, little-endian
>f2    IEEE binary16, big-endian
<f4    IEEE binary32, little-endian
>f4    IEEE binary32, big-endian
```

The one-argument form:

```sql
pblob_pack(json_vector)
```

uses:

```text
>f2
```

by default.

### Example

```sql
SELECT hex(pblob_pack('[1.0, -2.0]', '>f2'));
```

returns:

```text
3C00C00003030303
```

The packed values occupy the beginning of the BLOB:

```text
3C00 C000
```

and the final four bytes:

```text
03 03 03 03
```

identify the payload as big-endian binary16.

The inverse operation:

```sql
SELECT pblob_unpack(pblob_pack('[1.0, -2.0]', '>f2'));
```

returns JSON text representing the decoded values.

## Input

`pblob_pack()` accepts a JSON text value containing a one-dimensional array of ordinary JSON numbers:

```json
[0.125, -1.5, 2, 3.14159265]
```

The top-level value must be an array, and every element must be a numeric value represented by SQLite's canonical JSON numeric forms.

The extension deliberately has a narrow input contract. It does not accept vector elements such as:

```text
null
true / false
strings
objects
nested arrays
JSON5 numeric forms
NaN
Infinity
```

This keeps the stored format limited to ordinary finite floating-point vectors.

SQL `NULL` propagates to SQL `NULL`.

## Packed BLOB Format

A packed vector consists of the floating-point payload followed by a fixed four-byte metadata trailer:

```text
[payload ...][format trailer]
```

The payload always begins at BLOB offset `0`.

No element count is stored. The number of elements is derived from:

```text
(blob size - 4) / element size
```

where the element size is obtained from the trailer.

### Trailer

The trailer contains four identical bytes.

Each byte uses the low three bits:

```text
bit 0     reserved, must be 1
bit 1     endian: 0 = little, 1 = big
bit 2     type:   0 = f2,     1 = f4
bits 3-7  reserved, must be 0
```

The valid encodings are:

| Format |    Tag | Trailer       |
| ------ | -----: | ------------- |
| `<f2`  | `0x01` | `01 01 01 01` |
| `>f2`  | `0x03` | `03 03 03 03` |
| `<f4`  | `0x05` | `05 05 05 05` |
| `>f4`  | `0x07` | `07 07 07 07` |

Thus:

```text
[payload ...][01 01 01 01]   <f2
[payload ...][03 03 03 03]   >f2
[payload ...][05 05 05 05]   <f4
[payload ...][07 07 07 07]   >f4
```

Repeating the metadata byte four times makes the trailer itself independent of host byte order and provides a simple integrity check: all four bytes must agree.

An empty vector is valid and consists only of its four-byte trailer.

## Floating-Point Representation

Payload elements use IEEE floating-point encodings:

```text
f2    IEEE 754 binary16, 2 bytes per element
f4    IEEE 754 binary32, 4 bytes per element
```

Byte order is explicit and does not depend on the native byte order of the machine running SQLite.

Conceptually, packing follows:

```text
JSON number
    ↓
double
    ↓
float
    ├── binary32 bit pattern
    └── binary16 bit pattern
    ↓
explicit LE/BE serialization
    ↓
BLOB payload
```

Unpacking performs the reverse transformation.

Binary16 conversion is provided by the [FP16](https://github.com/Maratyszcza/FP16) library.

## Precision

Packing is intentionally lossy whenever the input number cannot be represented exactly in the selected destination format.

For `f4`, a JSON numeric value is narrowed from the intermediate C `double` to IEEE binary32.

For `f2`, conversion follows:

```text
double → binary32 → binary16
```

The test suite verifies the resulting values against Python's independent IEEE `struct` encodings and measures the observed loss relative to the original double-precision value.

For tested normal values, the suite verifies approximately:

```text
f4 relative error <= 2^-24
f2 relative error <= 2^-11 (ignoring lower order contribution due to the two-stage transformation)
```

Use `f2` where storage density is more important than precision and `f4` where substantially greater numeric precision is required.

## Storage Cost

Ignoring SQLite record overhead, the packed representation requires:

```text
f2: 2 × element_count + 4 bytes
f4: 4 × element_count + 4 bytes
```

For embedding-sized vectors, the fixed four-byte trailer is negligible.

For example, a 768-element vector requires:

```text
f2: 1540 bytes
f4: 3076 bytes
```

The format intentionally does not store dimensions, shape, labels, or other vector metadata.

## Scope

`pblob` is deliberately small.

It provides:

* JSON numeric array → packed floating-point BLOB conversion;
* packed BLOB → JSON numeric array conversion;
* binary16 and binary32 element formats;
* explicit little- and big-endian serialization;
* a self-describing four-byte trailer;
* validation of JSON input and packed BLOB structure.

It does **not** attempt to provide:

* multidimensional arrays or tensors;
* vector indexing or slicing;
* vector arithmetic;
* similarity search;
* distance functions;
* vector indexes;
* arbitrary numeric element types;
* binary64 (`f8`) storage;
* general-purpose binary serialization;
* SQLite JSONB as the persisted vector representation.

The objective is simply to provide a compact, deterministic representation for one-dimensional floating-point vectors while retaining straightforward conversion to and from inspectable JSON.

## SQLite Integration

`pblob` is designed as an integrated SQLite C auto-extension rather than as an independent loadable extension.

The implementation reuses SQLite's internal JSON parser and JSON text-generation machinery. This avoids introducing a separate JSON parser and keeps JSON behavior aligned with the SQLite build into which the extension is incorporated.

Because those JSON interfaces are internal SQLite implementation details, `pblob` is intended to be compiled together with SQLite as part of the extended amalgamation.

## Testing

The extension is tested exclusively through its public SQLite SQL surface using Pytest and Python's `sqlite3` module against isolated in-memory databases.

The suite covers:

* all four storage formats;
* default-format behavior;
* exact packed payload and trailer bytes;
* independent IEEE binary16/binary32 reference encodings;
* pack/unpack round trips;
* precision loss;
* normal, subnormal, boundary, and maximum finite values;
* empty and large vectors;
* invalid argument types and formats;
* malformed JSON;
* unsupported JSON elements;
* malformed trailers and payload sizes;
* non-finite values;
* SQL error messages.

See [`pblob/tests/README.md`](pblob/tests/README.md) for the detailed test-surface description.

## Project Structure

The extension itself is intentionally concentrated in a single C source module:

```text
src/
└── pblob.c
```

The SQL-surface test project is under:

```text
pblob/
├── pytest.ini
└── tests/
    ├── conftest.py
    ├── test_contract.py
    ├── test_pack.py
    ├── test_unpack.py
    └── test_roundtrip_precision.py
```

The repository also contains the SQLite build tooling used to construct the customized SQLite distribution containing the extension.

## Project Basis

This project is based on the [SQLite C Extension Template](https://github.com/pchemguy/SQLiteExtensionTemplate).

That repository provides the broader development pattern used here, including:

* integration of project C sources into a customized SQLite amalgamation;
* auto-extension registration;
* Windows/MSVC SQLite build tooling;
* Pytest-based testing through the SQLite SQL interface;
* infrastructure for direct C-level testing where an extension requires it.

`SQLitePackedBlob` applies that template to a concrete extension and intentionally focuses its tests on the SQLite-facing contract.

Detailed documentation of the underlying Windows/MSVC extended-amalgamation build process is maintained separately in the [SQLite MSVC Build field note](https://github.com/pchemguy/Field-Notes/tree/main/11-sqlite-msvc-build).
