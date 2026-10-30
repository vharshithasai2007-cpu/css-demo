"""SQLAlchemy 2.x engine and session factory for the portal SQLite database.

This database is separate from REVA's databases. The parent directory is
created on import, and every connection enables WAL mode and foreign keys.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .categories import CATEGORY_VALUES
from .config import settings
from .request_types import REQUEST_TYPE_VALUES

settings.db_path.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{settings.db_path.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    future=True,
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    """Enable WAL journaling and foreign-key enforcement per connection."""

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    """Yield a session and always close it."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _request_table_columns(bind) -> dict[str, dict]:  # noqa: ANN001
    inspector = inspect(bind)
    if "portal_requests" not in inspector.get_table_names():
        return {}
    return {column["name"]: column for column in inspector.get_columns("portal_requests")}


def _rebuild_portal_requests(bind, columns: dict[str, dict]) -> None:  # noqa: ANN001
    """Rebuild ``portal_requests`` with a nullable category and request_type.

    SQLite cannot drop a NOT NULL constraint in place. This follows the
    documented table-rebuild procedure: foreign keys are disabled for the
    swap, every existing row is copied unchanged, child rows keep their
    ``request_id`` values, and ``PRAGMA foreign_key_check`` runs before commit.
    """

    # Imported here because models imports Base from this module.
    from .models import PORTAL_STATUSES

    category_sql = ", ".join(f"'{value}'" for value in CATEGORY_VALUES)
    request_type_sql = ", ".join(f"'{value}'" for value in REQUEST_TYPE_VALUES)
    status_sql = ", ".join(f"'{value}'" for value in PORTAL_STATUSES)

    create_sql = f"""
        CREATE TABLE portal_requests_migrated (
            id INTEGER NOT NULL,
            reference_id VARCHAR(32) NOT NULL,
            user_id INTEGER,
            request_type VARCHAR(32),
            category VARCHAR(48),
            subject VARCHAR(240) NOT NULL,
            description TEXT NOT NULL,
            institution_name VARCHAR(240) NOT NULL,
            state VARCHAR(80),
            status VARCHAR(32) NOT NULL,
            department VARCHAR(160) NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            next_step_at DATETIME,
            PRIMARY KEY (id),
            CONSTRAINT uq_portal_requests_reference_id UNIQUE (reference_id),
            CONSTRAINT ck_portal_requests_request_type
                CHECK (request_type IS NULL OR request_type IN ({request_type_sql})),
            CONSTRAINT ck_portal_requests_category
                CHECK (category IS NULL OR category IN ({category_sql})),
            CONSTRAINT ck_portal_requests_status
                CHECK (status IN ({status_sql})),
            UNIQUE (reference_id),
            FOREIGN KEY(user_id) REFERENCES portal_users (id) ON DELETE SET NULL
        )
    """

    copy_columns = ["id", "reference_id", "user_id"]
    if "request_type" in columns:
        copy_columns.append("request_type")
    copy_columns.extend(
        [
            "category",
            "subject",
            "description",
            "institution_name",
            "state",
            "status",
            "department",
            "created_at",
            "updated_at",
            "next_step_at",
        ]
    )
    copy_columns = [name for name in copy_columns if name in columns]
    column_list = ", ".join(copy_columns)
    copy_sql = (
        f"INSERT INTO portal_requests_migrated ({column_list}) "
        f"SELECT {column_list} FROM portal_requests"
    )

    raw = bind.raw_connection()
    cursor = raw.cursor()
    try:
        # PRAGMA foreign_keys is a no-op inside a transaction, so disable it
        # before beginning the rebuild.
        cursor.execute("PRAGMA foreign_keys=OFF")
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DROP TABLE IF EXISTS portal_requests_migrated")
            cursor.execute(create_sql)
            cursor.execute(copy_sql)
            cursor.execute("DROP TABLE portal_requests")
            cursor.execute(
                "ALTER TABLE portal_requests_migrated RENAME TO portal_requests"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_portal_requests_user_id "
                "ON portal_requests (user_id)"
            )
            cursor.execute("PRAGMA foreign_key_check")
            violations = cursor.fetchall()
            if violations:
                raise RuntimeError(
                    "portal_requests migration left foreign-key violations: "
                    f"{violations!r}"
                )
            cursor.execute("COMMIT")
        except Exception:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            # The pooled connection must not return with foreign keys disabled.
            cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
        raw.close()


def migrate_portal_requests(bind=engine) -> bool:  # noqa: ANN001
    """Apply the additive request-type / nullable-category migration once.

    Returns ``True`` when the table was rebuilt and ``False`` when the schema
    was already current. Existing rows are never deleted, renumbered or
    backfilled.

    Startup assumes a single mock-css process. ``BEGIN IMMEDIATE`` serialises
    concurrent writers, but the schema snapshot is taken before the lock. Two
    workers starting at the same time could both decide to rebuild, and the
    later rebuild would use a stale column list. Run one process, or add an
    in-transaction schema re-check before enabling multiple workers.
    """

    columns = _request_table_columns(bind)
    if not columns:
        return False

    needs_rebuild = (
        "request_type" not in columns or not columns["category"]["nullable"]
    )
    if not needs_rebuild:
        return False

    _rebuild_portal_requests(bind, columns)
    return True


def init_db() -> None:
    """Create every portal table and apply pending portal-only migrations."""

    # Import inside the function so the models are registered before create_all
    # while avoiding a circular import at module load time.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_portal_requests(engine)
