import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure the project root is on sys.path so we can import predmarket.config
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve sqlalchemy.url from the project's data_dir config if not running tests
if "PYTEST_CURRENT_TEST" not in os.environ:
    try:
        from predmarket.config import load_config

        app_config = load_config()
        db_path = app_config.global_cfg.data_dir / "database.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    except Exception:
        # Fallback to a sensible default if config loading fails
        fallback_db_path = Path("./data/database.sqlite")
        fallback_db_path.parent.mkdir(parents=True, exist_ok=True)
        config.set_main_option("sqlalchemy.url", f"sqlite:///{fallback_db_path}")

# target_metadata not used — this project uses raw SQLite, not SQLAlchemy ORM.
# Migrations are written manually.
target_metadata = None

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
