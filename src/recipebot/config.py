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
# the 3 original JSON files (not committed)
RAW_DIR: Path = DATA_DIR / "raw"
DB_PATH: Path = DATA_DIR / "db" / "recipes.duckdb"
INDEX_DIR: Path = DATA_DIR / "index"        # BM25 pickle, FAISS index, row map
SAMPLE_DIR: Path = DATA_DIR / "sample"      # small committed sample for tests
# allergens, synonyms, pantry YAML files
TAXONOMY_DIR: Path = DATA_DIR / "taxonomy"

# ---- LLM settings (values come from .env) ------------------------------------
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "")
GEMINI_TIMEOUT_SECONDS: float = float(
    os.getenv("GEMINI_TIMEOUT_SECONDS", "30"))  # NEW
# NEW: extra tries on 429/5xx
GEMINI_MAX_RETRIES: int = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

# ---- Agent settings (Step 9): change a value here and rerun ------------------
# recipes shown per search when the user gives no number
DEFAULT_RESULT_K: int = 5
MAX_RESULT_K: int = 20           # upper limit for "show me N recipes"
# "most common ingredients" when the user gives no number
DEFAULT_TOP_K: int = 10
CONVERSATION_DIR: Path = PROJECT_ROOT / "docs" / "conversations"

# ---- Ingredient matching, Task 2 (Step 10): change a value and rerun ----------
# Score = W_COVERAGE * coverage - W_EXTRA * extra_ratio - W_STEPS * min(steps, STEP_CAP)
#   coverage    = matched / number of ingredients the user listed
#   extra_ratio = extra needed / ingredients the recipe needs (pantry staples not counted)
# The weights are design choices, not measured values; see docs/MATCHING.md.
MATCH_W_COVERAGE: float = 4.0
MATCH_W_EXTRA: float = 2.0
MATCH_W_STEPS: float = 0.1
# steps beyond this add no further penalty (a 286-step outlier must not dominate)
MATCH_STEP_CAP: int = 30
# a recipe must use at least this many of the user's ingredients
MATCH_MIN_MATCHED: int = 1
PANTRY_STAPLES_PATH: Path = TAXONOMY_DIR / "pantry_staples.yaml"

# ---- Substitution evidence, Task 3 (Step 11): change a value and rerun ---------
# Dish similarity = Jaccard overlap of the two recipes' "core" ingredients (the
# ingredient being replaced and pantry staples are left out of both sets).
# a recipe this similar is "related" (indirect evidence)
SUB_RELATED_MIN_SIM: float = 0.30
# ...and this similar AND sharing a title word = same dish family (direct)
SUB_NEIGHBOR_MIN_SIM: float = 0.50
# title words (generic ones ignored) shared with the original
SUB_MIN_TITLE_OVERLAP: int = 1
# recipes that must use a substitute before it counts as evidence
SUB_MIN_SUPPORT: int = 2
# same-dish-family recipes needed for the label "direct"
SUB_MIN_DIRECT_SUPPORT: int = 2
# share of ingredient-free recipes using it minus share of the others
SUB_MIN_ENRICHMENT: float = 0.02
# most similar recipes kept per group (speed; reported when it cuts)
SUB_POOL_SIZE: int = 3000
SUB_MAX_CANDIDATES: int = 5          # substitutes returned
SUB_MAX_CITED: int = 5               # recipe ids cited per substitute
# A recipe that shares at least this many (non-generic) title words with the original is
# "related" even when its ingredient overlap is low, and counts as the same dish family.
# Example: "Country Banana Bread" and "Banana Bread" share 2 words (banana, bread).
SUB_TITLE_MATCH_MIN_WORDS: int = 2
# An adapted recipe is only BUILT from a substitute with level "direct", or level "indirect"
# supported by at least this many recipes. Weaker evidence is shown, but never turned into a recipe.
SUB_ADAPT_MIN_SUPPORT: int = 3
# words that describe a recipe's style, not its dish; ignored when comparing titles
SUB_GENERIC_TITLE_WORDS: tuple[str, ...] = (
    "easy", "best", "classic", "quick", "simple", "homemade", "perfect", "favorite",
    "old", "fashioned", "fast", "delicious", "great", "basic", "style", "my", "mom",
    "grandma", "grandmother", "moist", "healthy", "low", "fat", "free", "light",
    "traditional", "ultimate", "super", "good", "no",
)
INGREDIENT_ROLES_PATH: Path = TAXONOMY_DIR / "ingredient_roles.yaml"

VALID_BACKENDS: tuple[str, ...] = ("gemini", "lora")
UNDERSTANDING_BACKEND: str = os.getenv(
    "UNDERSTANDING_BACKEND", "gemini").strip().lower()
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
