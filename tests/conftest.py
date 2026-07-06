import shutil
from pathlib import Path

import pytest

from predmarket.config import Config, ForecastingConfig, GlobalConfig, PortfolioConfig, VenuesConfig

# --- N+1 query detection ---
# Enable SQLAlchemy query counting to surface N+1 patterns during tests.
# The fixture tracks total queries per test; tests using the DB can assert
# reasonable query counts. Set ``query_counter`` on a test to access it.


class QueryCounter:
    """Counts SQL queries executed during a test to detect N+1 patterns."""

    def __init__(self) -> None:
        self.count = 0
        self.statements: list[str] = []

    def reset(self) -> None:
        self.count = 0
        self.statements = []

    def before_cursor_execute(
        self, conn, cursor, statement, parameters, context, executemany
    ) -> None:
        self.count += 1
        self.statements.append(statement)


@pytest.fixture
def query_counter():
    """Fixture that counts SQL queries. Use to detect N+1 patterns.

    Example::

        def test_no_n_plus_one(query_counter, test_data_dir):
            store = PointInTimeStore(test_data_dir / "database.sqlite")
            for i in range(10):
                store.add_record(...)
            assert query_counter.count < 20  # flag if too many queries
    """
    counter = QueryCounter()

    try:
        from sqlalchemy import event

        from predmarket.store import PointInTimeStore

        # Attach to new SQLite engines created by PointInTimeStore
        original_init = PointInTimeStore.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            if hasattr(self, "engine"):
                event.listen(self.engine, "before_cursor_execute", counter.before_cursor_execute)

        PointInTimeStore.__init__ = patched_init
    except ImportError:
        pass

    yield counter
    counter.reset()

    try:
        from predmarket.store import PointInTimeStore

        PointInTimeStore.__init__ = original_init  # type: ignore[name-defined]
    except (NameError, ImportError):
        pass


@pytest.fixture(autouse=True)
def setup_api_key_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-token")


@pytest.fixture
def test_data_dir(tmp_path):
    # Create temporary data directory for tests to ensure no state pollution
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "raw").mkdir()
    (data_dir / "processed").mkdir()

    # Run Alembic migrations programmatically on the test database
    from alembic.config import Config as AlembicConfig

    from alembic import command

    db_path = data_dir / "database.sqlite"
    project_root = Path(__file__).resolve().parents[1]
    ini_path = project_root / "alembic.ini"
    alembic_cfg = AlembicConfig(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")

    yield data_dir
    shutil.rmtree(data_dir)


@pytest.fixture
def mock_config(test_data_dir):
    venues = VenuesConfig()
    venues.polymarket.enabled = False
    venues.kalshi.enabled = False
    venues.kalshi.execution_enabled = False
    venues.kalshi.api_key = ""
    venues.kalshi.api_secret = ""

    return Config(
        global_cfg=GlobalConfig(
            environment="wsl2",
            data_dir=test_data_dir,
            log_level="DEBUG",
            dashboard_host="127.0.0.1",
            dashboard_port=9090,
        ),
        venues=venues,
        forecasting=ForecastingConfig(),
        portfolio=PortfolioConfig(),
    )
