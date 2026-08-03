from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Updated to relative import for package context
from .settings import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models using relative import so metadata registers correctly
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def migrate_db() -> None:
    """Idempotent schema migrations for columns added after initial table creation."""
    migrations = [
        "ALTER TABLE pole_states ADD COLUMN IF NOT EXISTS last_power_restored_seq INTEGER",
        "ALTER TABLE pole_states ADD COLUMN IF NOT EXISTS last_power_restored_at TIMESTAMPTZ",
        "ALTER TABLE pole_states ADD COLUMN IF NOT EXISTS last_boot_seq INTEGER",
        "ALTER TABLE pole_states ADD COLUMN IF NOT EXISTS last_boot_at TIMESTAMPTZ",
    ]
    with engine.begin() as conn:
        for sql in migrations:
            conn.execute(__import__('sqlalchemy').text(sql))
