"""BM25 index (rank_bm25.BM25Okapi) over title + canonical ingredients."""

from __future__ import annotations

import logging
import os
import pickle
import time
from pathlib import Path

import numpy as np

from recipebot.retrieval.common import (
    BM25_B,
    BM25_K1,
    BM25_PATH,
    TOKENIZER_VERSION,
    doc_tokens,
    ids_fingerprint,
    load_corpus,
    tokenize,
)

logger = logging.getLogger(__name__)


def build_bm25(
    db_path: Path | str | None = None, out_path: Path | str | None = None
) -> dict:
    """Build the BM25 index from the database and pickle it. Returns stats."""
    from rank_bm25 import BM25Okapi

    out_path = Path(out_path) if out_path else BM25_PATH
    t0 = time.perf_counter()
    corpus = load_corpus(db_path)
    tokens = [doc_tokens(t, i)
              for t, i in zip(corpus.titles, corpus.ingredients)]
    logger.info("Tokenized %d documents; building BM25", len(tokens))
    bm25 = BM25Okapi(tokens, k1=BM25_K1, b=BM25_B)

    payload = {
        "bm25": bm25,
        "ids": corpus.ids,
        "fingerprint": ids_fingerprint(corpus.ids),
        "tokenizer": TOKENIZER_VERSION,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, out_path)

    return {
        "n_docs": len(corpus.ids),
        "vocab_size": len(bm25.idf),
        "avg_doc_tokens": float(bm25.avgdl),
        "seconds": time.perf_counter() - t0,
        "size_mb": out_path.stat().st_size / 1e6,
        "fingerprint": payload["fingerprint"],
        "path": str(out_path),
    }


class Bm25Index:
    """Query wrapper. Position in `ids` equals recipes.row_idx."""

    def __init__(self, bm25, ids: list[str], fingerprint: str = ""):
        self.bm25 = bm25
        self.ids = ids
        self.fingerprint = fingerprint

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Bm25Index":
        path = Path(path) if path else BM25_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"BM25 index not found: {path}. "
                "Run: python -m recipebot.build_indexes bm25"
            )
        with open(path, "rb") as fh:  # only load files you built yourself
            payload = pickle.load(fh)
        if payload.get("tokenizer") != TOKENIZER_VERSION:
            raise RuntimeError(
                "BM25 index was built with another tokenizer; rebuild it.")
        return cls(payload["bm25"], payload["ids"], payload.get("fingerprint", ""))

    def scores(self, query: str) -> np.ndarray:
        """BM25 score of every recipe (zeros if the query has no usable token)."""
        tokens = tokenize(query)
        if not tokens:
            return np.zeros(len(self.ids), dtype=np.float32)
        return np.asarray(self.bm25.get_scores(tokens), dtype=np.float32)

    def top_k(
        self, query: str, k: int = 10, allowed: np.ndarray | None = None
    ) -> list[tuple[int, float]]:
        """Top-k (row_idx, score) with score > 0.

        `allowed` is an optional boolean array over row_idx; recipes where it
        is False are never returned (this is how Step 7 enforces hard filters).
        Ties are broken by lower row_idx, so results are deterministic.
        """
        scores = self.scores(query).astype(np.float64)
        if allowed is not None:
            scores = np.where(allowed, scores, -np.inf)
        cand = np.flatnonzero(scores > 0)
        if cand.size == 0 or k <= 0:
            return []
        order = np.lexsort((cand, -scores[cand]))[:k]
        return [(int(cand[i]), float(scores[cand[i]])) for i in order]
