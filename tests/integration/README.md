# Integration Tests

Tests in this directory exercise I/O-bound paths that go beyond pure logic:

- **Public API capture** - Tests that call capture functions which would hit live
  Kalshi/Polymarket APIs. These use injected/fake HTTP sessions but exercise the
  real data-flow, pagination, error-handling, and artifact-writing logic.
- **Local DB artifacts** - Tests that create real SQLite databases via alembic
  migrations, read/write DuckDB analytical artifacts, or traverse manual-drop
  filesystem paths.
- **Replay gates** - Tests that exercise the signal factory status routing logic,
  reading multiple upstream artifacts and verifying gate decisions match expected
  pipeline states.

## Running

```bash
make test-integration   # run only integration tests
make test-unit          # run only unit tests (fast)
make test               # run the full suite
```

## When to Put a Test Here

A test belongs in `tests/integration/` when it:

1. Calls a function that would make real network requests (even if the test
   injects a fake session/client).
2. Writes artifacts to disk and verifies their structure (not just return values).
3. Loads and executes a standalone script module from `scripts/` that has its
   own `sys.path` manipulation.
4. Chains multiple pipeline stages together (e.g., signal factory status
   routing through multiple artifact files).

A test belongs in `tests/unit/` when it:

1. Tests a pure function with no I/O.
2. Uses only in-memory data structures.
3. Does not write files or databases beyond the shared `tmp_path` fixture.
