"""Central configuration for the NOSH recipe chatbot.

Every other module imports paths and settings from here, so nothing is
hardcoded elsewhere. Secrets come from environment variables (loaded from
a local .env file) and are never written to code, logs or Git.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# src/recipebot/config.py -> parents[2] is the repository root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# Load variables from <root>/.env if it exists (silently does nothing otherwise).
load_dotenv(PROJECT_ROOT / ".env")

# ---- Paths -----------------------------------------------------------------
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"            # the 3 original JSON files (not committed)
DB_PATH: Path = DATA_DIR / "db" / "recipes.duckdb"
INDEX_DIR: Path = DATA_DIR / "index"        # BM25 pickle, FAISS index, row map
SAMPLE_DIR: Path = DATA_DIR / "sample"      # small committed sample for tests
TAXONOMY_DIR: Path = DATA_DIR / "taxonomy"  # allergens, synonyms, pantry YAML files

# ---- LLM settings (values come from .env) ------------------------------------
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "")

VALID_BACKENDS: tuple[str, ...] = ("gemini", "lora")
UNDERSTANDING_BACKEND: str = os.getenv("UNDERSTANDING_BACKEND", "gemini").strip().lower()
if UNDERSTANDING_BACKEND not in VALID_BACKENDS:
    raise ValueError(
        f"UNDERSTANDING_BACKEND must be one of {VALID_BACKENDS}, got {UNDERSTANDING_BACKEND!r}"
    )


def setup_logging(level: int = logging.INFO) -> None:
    """Configure console logging once. Call this from scripts and the app entry points.

    Never log GEMINI_API_KEY or any other secret.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
