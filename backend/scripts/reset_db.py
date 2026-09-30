"""DEV ONLY: drop and recreate the schema (including the append-only audit table) and stored files.

Usage (from backend/):  python -m scripts.reset_db --yes
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings


def reset(database_url: str | None = None, *, wipe_storage: bool = True) -> None:
    settings = get_settings()
    if settings.is_prod:
        sys.exit("Refusing to reset a production database (APP_ENV=prod).")
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    if database_url:
        cfg.attributes["database_url"] = database_url
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    storage = Path(settings.storage_dir)
    if wipe_storage and storage.exists() and storage.name == "storage":
        shutil.rmtree(storage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirm that all data will be deleted")
    args = parser.parse_args()
    if not args.yes:
        sys.exit("This deletes every document, answer log and audit event. Re-run with --yes to confirm.")
    reset()
    print("Database reset to an empty schema.")


if __name__ == "__main__":
    main()
