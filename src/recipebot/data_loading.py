"""Helpers for locating and reading the three raw Recipe Box JSON files.

Each raw file is a JSON *object* keyed by a hash (not an array), so a recipe's
identity inside a file is its key. Later steps build stable IDs as
``{source}:{key}``; this module only reads the files and never modifies them.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from recipebot import config

logger = logging.getLogger(__name__)

# Short source code -> expected file name inside data/raw/.
SOURCES: dict[str, str] = {
    "ar": "recipes_raw_nosource_ar.json",
    "epi": "recipes_raw_nosource_epi.json",
    "fn": "recipes_raw_nosource_fn.json",
}

# Short source code -> human-readable website name (for reports).
SOURCE_LABELS: dict[str, str] = {
    "ar": "AllRecipes",
    "epi": "Epicurious",
    "fn": "Food Network",
}


def raw_file_path(source: str, raw_dir: Path = config.RAW_DIR) -> Path:
    """Return the expected path of the raw JSON file for a source code."""
    if source not in SOURCES:
        raise KeyError(
            f"Unknown source {source!r}; expected one of {sorted(SOURCES)}")
    return raw_dir / SOURCES[source]


def load_raw_file(path: Path) -> dict[str, Any]:
    """Load one raw file and return its {hash_key: record} mapping.

    Raises:
        FileNotFoundError: if the file is missing (run scripts/download_data.py).
        ValueError: if the top-level JSON value is not an object.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. Run `python scripts/download_data.py` first."
        )
    logger.info("Loading %s", path.name)
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(
            f"{path.name}: expected a JSON object keyed by hash, got {type(data).__name__}"
        )
    return data
