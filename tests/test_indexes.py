"""Tests for the BM25 / FAISS index code (Step 6).

Small tests use a tiny temporary DuckDB file and a fake hash-based encoder, so
no model download is needed. The last two tests check the REAL built indexes
and are skipped until you have built them.
"""

import zlib

import duckdb
import numpy as np
import pytest

from recipebot.retrieval.common import (
    BM25_PATH,
    FAISS_PATH,
    MAX_INGREDIENTS_IN_TEXT,
    doc_tokens,
    embedding_text,
    ids_fingerprint,
    load_corpus,
    tokenize,
)

RECIPES = [
    (0, "a:1", "Garlic Bread", ["garlic", "butter", "bread", "garlic"]),
    (1, "a:2", "Tomato Soup", ["tomato", "onion", "water"]),
    (2, "a:3", "Peanut Cookies", ["peanut butter", "sugar", "egg"]),
    (3, "a:4", "Plain Rice", ["rice", "water"]),
]


def make_db(path, recipes=RECIPES):
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE recipes (id VARCHAR, row_idx INTEGER, title VARCHAR)")
    con.execute(
        "CREATE TABLE recipe_ingredient (recipe_id VARCHAR, row_idx INTEGER, "
        "position INTEGER, name_index INTEGER, canonical VARCHAR)"
    )
    for row_idx, rid, title, ings in recipes:
        con.execute("INSERT INTO recipes VALUES (?, ?, ?)",
                    [rid, row_idx, title])
        for pos, canon in enumerate(ings):
            con.execute(
                "INSERT INTO recipe_ingredient VALUES (?, ?, ?, 0, ?)",
                [rid, row_idx, pos, canon],
            )
    con.close()
    return path


@pytest.fixture()
def db_path(tmp_path):
    return make_db(tmp_path / "test.duckdb")


def fake_encoder(texts):
    """Deterministic bag-of-words hashing encoder (256 dims, L2-normalized)."""
    out = np.zeros((len(texts), 256), dtype="float32")
    for i, text in enumerate(texts):
        for tok in tokenize(text):
            out[i, zlib.crc32(tok.encode()) % 256] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return out / norms


# ---- tokenization and text builders --------------------------------------
def test_tokenize_basic():
    assert tokenize("Tomatoes and Garlic!") == ["tomato", "garlic"]


def test_tokenize_empty_and_stopwords():
    assert tokenize("") == []
    assert tokenize("the and of") == []


def test_doc_tokens_combines_title_and_ingredients():
    assert doc_tokens("Garlic Bread", ["garlic", "peanut butter"]) == [
        "garlic", "bread", "garlic", "peanut", "butter",
    ]


def test_embedding_text_format():
    assert embedding_text(
        "Soup", ["tomato", "onion"]) == "Soup. Ingredients: tomato, onion"
    assert embedding_text("Soup", []) == "Soup"


def test_embedding_text_caps_ingredients():
    names = [f"item{i}" for i in range(MAX_INGREDIENTS_IN_TEXT + 5)]
    text = embedding_text("X", names)
    assert f"item{MAX_INGREDIENTS_IN_TEXT - 1}" in text
    assert f"item{MAX_INGREDIENTS_IN_TEXT}" not in text


# ---- corpus loading ---------------------------------------------------------
def test_load_corpus_order_and_distinct(db_path):
    corpus = load_corpus(db_path)
    assert corpus.ids == ["a:1", "a:2", "a:3", "a:4"]
    assert corpus.titles[0] == "Garlic Bread"
    assert corpus.ingredients[0] == [
        "garlic", "butter", "bread"]  # garlic once


def test_load_corpus_rejects_gap(tmp_path):
    bad = make_db(tmp_path / "bad.duckdb",
                  recipes=[RECIPES[0], RECIPES[2]])  # row_idx 0, 2
    with pytest.raises(ValueError):
        load_corpus(bad)


# ---- BM25 ------------------------------------------------------------------------
def test_bm25_ranking(db_path, tmp_path):
    pytest.importorskip("rank_bm25")
    from recipebot.retrieval.bm25 import Bm25Index, build_bm25

    out = tmp_path / "bm25.pkl"
    stats = build_bm25(db_path, out)
    assert stats["n_docs"] == 4
    index = Bm25Index.load(out)
    assert index.top_k("garlic bread", k=3)[0][0] == 0
    assert index.top_k("tomato", k=3)[0][0] == 1
    assert index.top_k("peanut butter", k=3)[0][0] == 2


def test_bm25_allowed_mask(db_path, tmp_path):
    pytest.importorskip("rank_bm25")
    from recipebot.retrieval.bm25 import Bm25Index, build_bm25

    out = tmp_path / "bm25.pkl"
    build_bm25(db_path, out)
    index = Bm25Index.load(out)
    allowed = np.array([False, True, True, True])
    rows = [r for r, _ in index.top_k("garlic bread", k=4, allowed=allowed)]
    assert 0 not in rows


def test_bm25_empty_query(db_path, tmp_path):
    pytest.importorskip("rank_bm25")
    from recipebot.retrieval.bm25 import Bm25Index, build_bm25

    out = tmp_path / "bm25.pkl"
    build_bm25(db_path, out)
    assert Bm25Index.load(out).top_k("the and", k=3) == []


def test_bm25_ids_match_db(db_path, tmp_path):
    pytest.importorskip("rank_bm25")
    from recipebot.retrieval.bm25 import Bm25Index, build_bm25

    out = tmp_path / "bm25.pkl"
    build_bm25(db_path, out)
    index = Bm25Index.load(out)
    assert index.ids == load_corpus(db_path).ids
    assert index.fingerprint == ids_fingerprint(index.ids)


# ---- FAISS / embeddings (fake encoder) ---------------------------------------
def test_embeddings_build_and_search(db_path, tmp_path):
    pytest.importorskip("faiss")
    from recipebot.retrieval.embeddings import SemanticIndex, build_embeddings

    idx_dir = tmp_path / "idx"
    stats = build_embeddings(
        db_path, idx_dir, encoder=fake_encoder, shard_size=2)
    assert stats["n_vectors"] == 4
    assert stats["shards_total"] == 2
    sem = SemanticIndex.load(idx_dir, encoder=fake_encoder)
    assert sem.index.ntotal == 4
    assert sem.search("garlic bread", k=2)[0][0] == 0


def test_embeddings_resume_skips_shards(db_path, tmp_path):
    pytest.importorskip("faiss")
    from recipebot.retrieval.embeddings import build_embeddings

    idx_dir = tmp_path / "idx"
    build_embeddings(db_path, idx_dir, encoder=fake_encoder, shard_size=2)
    calls = []

    def counting_encoder(texts):
        calls.append(len(texts))
        return fake_encoder(texts)

    stats = build_embeddings(
        db_path, idx_dir, encoder=counting_encoder, shard_size=2)
    assert calls == []
    assert stats["shards_skipped"] == 2


def test_embeddings_settings_mismatch_raises(db_path, tmp_path):
    pytest.importorskip("faiss")
    from recipebot.retrieval.embeddings import build_embeddings

    idx_dir = tmp_path / "idx"
    build_embeddings(db_path, idx_dir, encoder=fake_encoder, shard_size=2)
    with pytest.raises(RuntimeError):
        build_embeddings(db_path, idx_dir, encoder=fake_encoder, shard_size=3)
    # --force discards the old shards and works
    build_embeddings(db_path, idx_dir, encoder=fake_encoder,
                     shard_size=3, force=True)


# ---- REAL indexes (skipped until built) --------------------------------------
@pytest.mark.skipif(not BM25_PATH.exists(), reason="real BM25 index not built")
def test_real_bm25_aligned_with_db():
    from recipebot.retrieval.bm25 import Bm25Index

    index = Bm25Index.load()
    corpus = load_corpus()
    assert index.ids == corpus.ids
    assert index.top_k("garlic bread", k=5)  # returns something


@pytest.mark.skipif(not FAISS_PATH.exists(), reason="real FAISS index not built")
def test_real_faiss_aligned_with_db():
    pytest.importorskip("faiss")
    from recipebot.retrieval.embeddings import SemanticIndex

    sem = SemanticIndex.load()
    corpus = load_corpus()
    assert sem.index.ntotal == len(corpus.ids)
    assert sem.meta["fingerprint"] == ids_fingerprint(corpus.ids)
