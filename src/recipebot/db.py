"""Database access helper. The app always opens DuckDB read-only (only one writer allowed)."""
from __future__ import annotations

from pathlib import Path

import duckdb

from recipebot import config


def connect(read_only: bool = True, path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """Open the recipes database. Raises FileNotFoundError if it has not been built yet."""
    db_path = Path(path) if path else config.DB_PATH
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} not found. Build it with: python -m recipebot.build_db")
    return duckdb.connect(str(db_path), read_only=read_only)
