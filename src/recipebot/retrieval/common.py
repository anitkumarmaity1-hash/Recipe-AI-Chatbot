"""Shared pieces for the BM25 and FAISS indexes (Step 6).

Both indexes must list recipes in the SAME order as recipes.row_idx.
Everything that decides document text or tokenization lives here, so the
build code and the query code cannot drift apart.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from recipebot import config
from recipebot.db import connect
from recipebot.normalization.ingredients import singularize

# ---- file locations (data/index is git-ignored) -------------------------
INDEX_DIR: Path = config.INDEX_DIR
BM25_PATH: Path = INDEX_DIR / "bm25.pkl"
FAISS_PATH: Path = INDEX_DIR / "recipes.faiss"
EMB_META_PATH: Path = INDEX_DIR / "embeddings_meta.json"
ALLERGEN_FLAGS_PATH: Path = INDEX_DIR / "allergen_flags.npz"   # NEW: cache, Step 7

# ---- tunable settings (edit here; rebuild the index afterwards) ---------
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MAX_SEQ_LENGTH = 128
ENCODE_BATCH = 64
SHARD_SIZE = 10_000
MAX_INGREDIENTS_IN_TEXT = 15
TEXT_FORMAT_VERSION = "title+ingredients-v1"

BM25_K1 = 1.5
BM25_B = 0.75
TOKENIZER_VERSION = "v1"

# NEW: hybrid retrieval (Step 7). Change a value here and rerun; no rebuild needed.
RRF_K = 60            # NEW: RRF constant from the original paper; larger = flatter fusion
BM25_WEIGHT = 1.0     # NEW: weight of the lexical ranking inside RRF
SEMANTIC_WEIGHT = 1.0  # NEW: weight of the embedding ranking inside RRF
POOL_SIZE = 200       # NEW: candidates kept from EACH retriever before fusion

STOPWORDS = frozenset(
    {"a", "an", "and", "or", "the", "with", "of", "in", "for", "to", "on",
     "my", "me", "i", "some", "recipe", "recipes"}
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@lru_cache(maxsize=100_000)
def _norm_token(token: str) -> str:
    return singularize(token)


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords, singularize."""
    return [
        _norm_token(tok)
        for tok in _TOKEN_RE.findall((text or "").lower())
        if tok not in STOPWORDS
    ]


def doc_tokens(title: str, ingredients: list[str]) -> list[str]:
    """BM25 document = title tokens + tokens of each canonical ingredient."""
    tokens = tokenize(title)
    for name in ingredients:
        tokens.extend(tokenize(name))
    return tokens


def embedding_text(title: str, ingredients: list[str]) -> str:
    """Text that is embedded for one recipe (no instructions)."""
    names = ingredients[:MAX_INGREDIENTS_IN_TEXT]
    if not names:
        return title
    return f"{title}. Ingredients: {', '.join(names)}"


def ids_fingerprint(ids: list[str]) -> str:
    """Short hash of the ordered recipe IDs; detects a changed database."""
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()[:16]


@dataclass
class Corpus:
    """Recipes in row_idx order (position in each list == row_idx)."""

    ids: list[str]
    titles: list[str]
    ingredients: list[list[str]]  # distinct canonical names, in recipe order


def load_corpus(db_path: Path | str | None = None) -> Corpus:
    """Read the corpus from DuckDB, ordered by row_idx."""
    con = connect(read_only=True, path=db_path)
    try:
        rows = con.execute(
            "SELECT row_idx, id, title FROM recipes ORDER BY row_idx"
        ).fetchall()
        ing_rows = con.execute(
            "SELECT row_idx, canonical FROM recipe_ingredient "
            "ORDER BY row_idx, position, name_index"
        ).fetchall()
    finally:
        con.close()

    n = len(rows)
    if [r[0] for r in rows] != list(range(n)):
        raise ValueError("recipes.row_idx is not contiguous 0..N-1")

    ingredients: list[list[str]] = [[] for _ in range(n)]
    for row_idx, canonical in ing_rows:
        names = ingredients[row_idx]
        if canonical not in names:
            names.append(canonical)

    return Corpus(
        ids=[r[1] for r in rows],
        titles=[r[2] for r in rows],
        ingredients=ingredients,
    )