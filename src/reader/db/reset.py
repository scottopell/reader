"""Reset database (development only)."""

from reader.config import get_settings
from reader.db.migrate import migrate


def reset() -> None:
    """Delete and recreate the database."""
    settings = get_settings()
    db_path = settings.db_path

    if db_path.exists():
        db_path.unlink()
        print(f"✓ Deleted {db_path}")

    # Also delete WAL and SHM files if they exist
    wal_path = db_path.with_suffix(".db-wal")
    shm_path = db_path.with_suffix(".db-shm")
    if wal_path.exists():
        wal_path.unlink()
    if shm_path.exists():
        shm_path.unlink()

    # Recreate with migrations
    migrate()
    print("✓ Database reset complete")


if __name__ == "__main__":
    reset()
