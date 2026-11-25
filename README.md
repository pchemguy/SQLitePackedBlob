---
url: https://chatgpt.com/c/6a79cc83-25dc-83eb-944c-5d819e7af573
---

# SQLite Packed Blob (`pblob`)

`pblob` is a SQLite C auto-extension for storing embedding vectors and similar one-dimensional numeric arrays. It converts JSON text to a compact BLOB of IEEE binary16 or binary32 values in either byte order, and converts the BLOB back to JSON text.

[SQL API](#sql-api) · [Packed BLOB format](#packed-blob-format) · [Build on Windows](#build-on-windows) · [Testing](#testing)

> [!IMPORTANT]
> 
> **AI-Assisted Development Disclosure**
> 
> This project has been developed with extensive generative-AI assistance. Assistance covered project exploration, design discussion, specification development, implementation, testing, technical review, and documentation. See [AI_DISCLOSURE.md](AI_DISCLOSURE.md) for further details. Responsibility for the published software remains with the maintainer.

## SQL API

`pblob` provides three scalar-function signatures:

```sql
pblob_pack(json_vector, format) -> BLOB
pblob_pack(json_vector)         -> BLOB
pblob_unpack(blob_data)         -> TEXT
```

The one-argument form of `pblob_pack` defaults to `>f2` (big-endian binary16). The two-argument form accepts exactly `<f2`, `>f2`, `<f4`, or `>f4` as SQL TEXT.

### Example

```sql
SELECT hex(pblob_pack('[1.0,-2.0]'));                 -- 3C00C00003030303
SELECT pblob_unpack(X'3C00C00003030303');              -- [1.0,-2.0]
SELECT json_array(pblob_unpack(X'3C00C00003030303'));  -- [[1.0,-2.0]]
```

The first four bytes, `3C00 C000`, encode the two binary16 values. The remaining `03 03 03 03` identify their format. The last query shows how SQLite's JSON functions treat the unpacker's TEXT result as an array when used directly in a SQL expression.

## Input

`pblob_pack()` accepts SQL TEXT containing a one-dimensional JSON array of ordinary, finite numbers, for example `[0.125,-1.5,2,3.14159265]`. It rejects JSONB input, malformed JSON, JSON5 syntax, and elements such as strings, booleans, JSON `null`, objects, and nested arrays. A number that overflows to infinity in the requested format raises a SQL error. Underflow can produce a subnormal value or signed zero.

`pblob_unpack()` accepts a SQL BLOB. It checks the trailer and payload length and rejects IEEE infinities and NaNs in externally constructed BLOBs.

A SQL `NULL` first argument returns SQL `NULL` for either function, including `pblob_pack(NULL, NULL)`. For a TEXT first argument, an explicitly NULL format raises `pblob format must not be NULL`.

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

The test suite compares decoded values with Python's `struct` encodings. Near a binary16 midpoint, rounding to binary32 first can change which binary16 value is stored. For the normal values in the precision tests, the relative-error bounds are `2^-24` for binary32 and `2^-11 + 2^-24` for the two-stage binary16 conversion.

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

[`src/pblob.c`](src/pblob.c) uses SQLite's private JSON parser and text writer. The build includes it after the JSON implementation in the same amalgamation. The FP16 dependency supplies headers for floating-point conversion. SQLite calls `sqlite3PblobInit` through the generated auto-extension dispatcher on each new connection. Applications can use both SQL functions immediately. The repository builds the integrated extension only.

## Build on Windows

Run the commands from the repository root in a path without spaces. Install Visual C++ Build Tools with a Windows SDK. The bundled Python bootstrap targets x64. The MSVC helper can discover an installed x64 toolchain or reuse an initialized x86 or x64 developer prompt. For x86, start in an x86 developer prompt, activate a matching x86 Conda environment, and use a separate copy of the harness. The primary reference for the shared Windows build scripts, cache layout, and switches is the [upstream SQLite MSVC build guide](https://github.com/pchemguy/SQLite-ICU-MinGW/blob/master/Current/MSVC/README.md).

### 1. Prepare the environment

If you already have an active Conda environment with architecture-matched ICU headers, import libraries, runtime DLLs, and pytest, continue to step 2. To create the project's x64 environment, open a clean `cmd.exe /d /e:on /v:on` at the repository root with `CONDA_PREFIX` unset and neither `python.exe` nor `conda.bat` on `PATH`.

The first bootstrap can replace the user's pip and uv cache directories with junctions and remove an existing `%APPDATA%\mamba` directory. The local manifests install pytest on a full run. Use `PKGS` to request ICU explicitly for this preset. [Conda Bootstrap for Windows](https://github.com/pchemguy/Conda-Bootstrap#windows-harness) · [Cache and filesystem changes](https://github.com/pchemguy/Conda-Bootstrap/blob/main/windows/Anaconda.md#cache-and-filesystem-changes)

```cmd
set "PKGS=icu"
call pyenv\Anaconda.bat
set "PKGS="
call pyenv\conda_far.bat /batch
```

The bootstrap creates `pyenv\Anaconda` and exits early when its `python.exe` already exists. In later clean CMD sessions, run only the activation command. The launcher checks MSVC before activating Conda. The SQLite builder checks the compiler, Microsoft linker, and ICU architecture again in the activated environment. To add missing packages to an existing activated prefix, use `conda install -c conda-forge icu pytest`.

### 2. Build the checkout

The [PBLOB hook](sqlite_ext_pblob.bat) reads `out\cache\SQLitePackedBlob\src\pblob.c`. On a cache miss it downloads the file from the repository's `main` branch. To build this checkout, including a branch or uncommitted edits, copy the local source into that cache before running the preset. Start with a fresh `out\build` so NMake regenerates `sqlite3.c`.

```cmd
if not exist "out\cache\SQLitePackedBlob\src" mkdir "out\cache\SQLitePackedBlob\src"
copy /b /y "src\pblob.c" "out\cache\SQLitePackedBlob\src\pblob.c"
cmd /d /c sqlite_msbuild_bare_icu_ext_extra.bat
```

The [single project preset](sqlite_msbuild_bare_icu_ext_extra.bat) runs the [NMake build](sqlite_msbuild.bat) with `USE_ICU=1`, `USE_ZLIB=1`, `SQLITE_EXTRA=1`, `USE_EXTRAS=1`, and `SQLITE_ENABLE_PBLOB=1`. The stock `ext/misc` stage supplies the auto-extension dispatcher. PBLOB is the only project hook shipped here. It adds `pblob.c` and the header-only FP16 dependency. ICU and ZLIB belong to the wider preset.

On a cache miss the harness downloads a SQLite source snapshot into `out\cache\sqlite.zip`. Later builds reuse both the archives and the extracted sources. When editing `pblob.c` again, move the previous `out\build` aside and repeat the copy and build commands. Use a fresh build base when changing architecture, SQLite snapshot, or ICU installation.

### 3. Verify the packaged shell

```cmd
out\bin\sqlite3.exe -init NUL :memory: "SELECT hex(pblob_pack('[1,-2]')), json_array(pblob_unpack(pblob_pack('[1,-2]')));"
```

Expected output is `3C00C00003030303|[[1.0,-2.0]]`. The second column checks that SQLite recognizes the result as JSON when nesting it in another array.

| Packaged files | Directory |
| --- | --- |
| `sqlite3.exe`, `sqlite3.dll`, versioned ICU DLLs, `zlib1.dll` | `out\bin` |
| SQLite headers | `out\include` |
| `sqlite3.lib` (DLL import library), `sqlite3.def` | `out\lib\import` |
| `libsqlite3.lib` (static library) | `out\lib\static` |

## Testing

The pytest suite calls the SQL functions through Python's `sqlite3` module on a fresh in-memory database per test. The MSVC build packages `out\bin\sqlite3.dll` separately from Conda's copy. To test the freshly built DLL with the bundled Windows Python, run this from the repository root in the activated environment. It loads the DLL for this process before pytest imports `sqlite3`.

```cmd
python -c "import ctypes, os; dll = ctypes.CDLL(os.path.abspath(r'out\bin\sqlite3.dll')); import pytest; raise SystemExit(pytest.main(['-q', 'pblob/tests']))"
```

If Python already uses a PBLOB-enabled SQLite library, run `python -m pytest` from the repository root. The suite covers SQL registration, byte layout, precision, JSON composition, and invalid inputs. [Test coverage and runtime diagnostics](pblob/tests/README.md)

## Project Structure

| Path | Purpose |
| --- | --- |
| [`src/pblob.c`](src/pblob.c) | Extension implementation and SQL function registration |
| [`pyenv/`](pyenv/) | Windows bootstrap, package manifests, and activation scripts |
| [`sqlite_msbuild.bat`](sqlite_msbuild.bat), [`sqlite_ext_pblob.bat`](sqlite_ext_pblob.bat), [`tool/`](tool/) | SQLite build, PBLOB source staging, and amalgamation helpers |
| [`pyproject.toml`](pyproject.toml), [`pblob/tests/`](pblob/tests/) | Root pytest configuration, fixtures, and SQL tests |

## Project Basis

This project is based on the [SQLite C Extension Template](https://github.com/pchemguy/SQLiteExtensionTemplate). It adopts the template's extended-amalgamation build and tests PBLOB through its public SQL interface. The [SQLite MSVC Build field note](https://github.com/pchemguy/Field-Notes/tree/main/notes/11-sqlite-msvc-build) describes the integration technique.
