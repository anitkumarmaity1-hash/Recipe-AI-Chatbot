"""Semantic index: MiniLM embeddings stored in a FAISS IndexFlatIP.

The build is resumable: vectors are written in shards, so an interrupted run
continues where it stopped. Vectors are L2-normalized, so inner product ==
cosine similarity.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import time
from pathlib import Path
from typing import Callable

import numpy as np

from recipebot.retrieval.common import (
    EMB_META_PATH,
    EMBEDDING_MODEL,
    ENCODE_BATCH,
    FAISS_PATH,
    INDEX_DIR,
    MAX_INGREDIENTS_IN_TEXT,
    MAX_SEQ_LENGTH,
    SHARD_SIZE,
    TEXT_FORMAT_VERSION,
    embedding_text,
    ids_fingerprint,
    load_corpus,
)

logger = logging.getLogger(__name__)

Encoder = Callable[[list[str]], np.ndarray]


def default_encoder() -> Encoder:
    """Load the sentence-transformers model (downloads it on first use)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL)
    model.max_seq_length = MAX_SEQ_LENGTH

    def encode(texts: list[str]) -> np.ndarray:
        vecs = model.encode(
            texts,
            batch_size=ENCODE_BATCH,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    return encode


def _settings(fingerprint: str, n: int, shard_size: int) -> dict:
    return {
        "fingerprint": fingerprint,
        "n": n,
        "shard_size": shard_size,
        "model": EMBEDDING_MODEL,
        "max_seq_length": MAX_SEQ_LENGTH,
        "max_ingredients": MAX_INGREDIENTS_IN_TEXT,
        "text_format": TEXT_FORMAT_VERSION,
    }


def build_embeddings(
    db_path: Path | str | None = None,
    index_dir: Path | str | None = None,
    encoder: Encoder | None = None,
    shard_size: int = SHARD_SIZE,
    force: bool = False,
) -> dict:
    """Encode every recipe (resumable) and write the FAISS index. Returns stats."""
    import faiss

    index_dir = Path(index_dir) if index_dir else INDEX_DIR
    shard_dir = index_dir / "emb_shards"

    corpus = load_corpus(db_path)
    n = len(corpus.ids)
    texts = [embedding_text(t, i)
             for t, i in zip(corpus.titles, corpus.ingredients)]
    fingerprint = ids_fingerprint(corpus.ids)
    settings = _settings(fingerprint, n, shard_size)

    if force and shard_dir.exists():
        shutil.rmtree(shard_dir)
    shard_dir.mkdir(parents=True, exist_ok=True)
    settings_path = shard_dir / "shards_settings.json"
    if settings_path.exists():
        if json.loads(settings_path.read_text(encoding="utf-8")) != settings:
            raise RuntimeError(
                "Existing shards were built with different settings or data. "
                "Rerun with --force to discard them."
            )
    else:
        settings_path.write_text(json.dumps(
            settings, indent=2), encoding="utf-8")

    n_shards = math.ceil(n / shard_size)
    t0 = time.perf_counter()
    encoded = skipped = 0
    enc = encoder
    for s in range(n_shards):
        lo, hi = s * shard_size, min((s + 1) * shard_size, n)
        path = shard_dir / f"shard_{s:04d}.npy"
        if path.exists():
            existing = np.load(path)
            ok = existing.shape[0] == hi - lo
            del existing
            if ok:
                skipped += 1
                continue
            logger.warning("Shard %d has the wrong size; re-encoding", s)
        if enc is None:
            logger.info("Loading embedding model %s", EMBEDDING_MODEL)
            enc = default_encoder()
        vecs = np.asarray(enc(texts[lo:hi]), dtype=np.float32)
        if vecs.shape[0] != hi - lo:
            raise RuntimeError(
                f"Encoder returned {vecs.shape[0]} vectors for {hi - lo} texts")
        tmp = shard_dir / f"shard_{s:04d}.tmp.npy"
        np.save(tmp, vecs)
        os.replace(tmp, path)
        encoded += hi - lo
        elapsed = time.perf_counter() - t0
        logger.info(
            "Shard %d/%d done (%d recipes encoded this run, %.0f/s)",
            s + 1, n_shards, encoded, encoded / elapsed if elapsed else 0.0,
        )

    emb = np.ascontiguousarray(
        np.vstack(
            [np.load(shard_dir / f"shard_{s:04d}.npy") for s in range(n_shards)]),
        dtype=np.float32,
    )
    if emb.shape[0] != n:
        raise RuntimeError(f"Assembled {emb.shape[0]} vectors for {n} recipes")
    dim = int(emb.shape[1])

    index = faiss.IndexFlatIP(dim)
    index.add(emb)
    faiss_path = index_dir / FAISS_PATH.name
    tmp_index = index_dir / (FAISS_PATH.name + ".tmp")
    faiss.write_index(index, str(tmp_index))
    os.replace(tmp_index, faiss_path)
    meta = {**settings, "dim": dim}
    (index_dir / EMB_META_PATH.name).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "n_vectors": int(index.ntotal),
        "dim": dim,
        "seconds_this_run": time.perf_counter() - t0,
        "encoded_this_run": encoded,
        "shards_skipped": skipped,
        "shards_total": n_shards,
        "size_mb": faiss_path.stat().st_size / 1e6,
        "fingerprint": fingerprint,
        "model": EMBEDDING_MODEL,
        "path": str(faiss_path),
    }


class SemanticIndex:
    """Query wrapper. FAISS row position == recipes.row_idx."""

    def __init__(self, index, meta: dict, encoder: Encoder | None = None):
        self.index = index
        self.meta = meta
        self._encoder = encoder

    @classmethod
    def load(
        cls, index_dir: Path | str | None = None, encoder: Encoder | None = None
    ) -> "SemanticIndex":
        import faiss

        index_dir = Path(index_dir) if index_dir else INDEX_DIR
        faiss_path = index_dir / FAISS_PATH.name
        meta_path = index_dir / EMB_META_PATH.name
        if not faiss_path.exists() or not meta_path.exists():
            raise FileNotFoundError(
                f"FAISS index not found in {index_dir}. "
                "Run: python -m recipebot.build_indexes embeddings"
            )
        index = faiss.read_index(str(faiss_path))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if index.ntotal != meta["n"]:
            raise RuntimeError(
                "FAISS index size does not match its metadata; rebuild it.")
        return cls(index, meta, encoder)

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        """Top-k (row_idx, cosine similarity)."""
        if self._encoder is None:
            self._encoder = default_encoder()
        vec = np.ascontiguousarray(
            np.asarray(self._encoder([query]), dtype=np.float32)
        )
        scores, idx = self.index.search(vec, min(k, self.index.ntotal))
        return [
            (int(i), float(s)) for i, s in zip(idx[0], scores[0]) if i >= 0
        ]
