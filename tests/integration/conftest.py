"""Integration test configuration.

All tests in this directory are automatically marked with @pytest.mark.integration.
These tests exercise real I/O paths: public API capture functions (with injected
sessions), local filesystem artifact reads/writes, SQLite/alembic schema, and
end-to-end replay gate routing through the signal factory status module.

Run with:  make test-integration
"""

import pytest


# Auto-mark every test collected under tests/integration/ as an integration test.
def pytest_collection_modifyitems(items):
    integration_marker = pytest.mark.integration
    for item in items:
        if "tests/integration/" in str(item.fspath):
            item.add_marker(integration_marker)
