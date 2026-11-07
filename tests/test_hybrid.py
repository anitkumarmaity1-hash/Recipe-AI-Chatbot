"""Tests for hybrid retrieval (Step 7): RRF, hard-constraint masks, the retriever.

Small tests use a tiny temporary DuckDB file, a fake hash-based encoder and an
inline allergen taxonomy, so no model download and no real data are needed.
The last test uses the REAL built indexes and is skipped until they exist.
"""

import zlib

import duckdb
import numpy as np
import pytest

from recipebot.normalization.allergens import AllergenMatcher
from recipebot.retrieval.bm25 import Bm25Index, build_bm25
from recipebot.retrieval.common import BM25_PATH, FAISS_PATH, ids_fingerprint, tokenize
from recipebot.retrieval.embeddings import SemanticIndex, build_embeddings
from recipebot.retrieval.hybrid import HybridRetriever, format_result, rrf_fuse
from recipebot.retrieval.masks import (
    AllergenFlags,
    Constraints,
    compute_flags,
    taxonomy_hash,
)
from recipebot.tools.stats import RecipeStats, UnknownIngredientError

pytest.importorskip("faiss")
pytest.importorskip("rank_bm25")

TAXONOMY = {
    "dairy": {"include": ["milk", "butter", "cream", "cheese"],
              "exceptions": ["peanut butter", "coconut milk"]},
    "egg": {"include": ["egg"], "exceptions": []},
    "peanut": {"include": ["peanut"], "exceptions": []},
}

# row_idx, id, title, cleaned lines, canonical names, n_steps
RECIPES = [
    (0, "a:1", "Garlic Bread", ["2 cloves garlic", "1/2 cup butter", "1 loaf bread"],
     ["garlic", "butter", "bread"], 3),
    (1, "a:2", "Tomato Soup", ["4 tomatoes", "1 onion", "2 cups water"],
     ["tomato", "onion", "water"], 4),
    (2, "a:3", "Peanut Cookies", ["1 cup peanut butter", "1 cup sugar", "1 egg"],
     ["peanut butter", "sugar", "egg"], 5),
    (3, "a:4", "Plain Rice", ["1 cup rice",
     "2 cups water"], ["rice", "water"], 0),
    (4, "a:5", "Garlic Tomato Pasta", ["2 cloves garlic", "3 tomatoes", "8 oz pasta"],
     ["garlic", "tomato", "pasta"], 6),
    (5, "a:6", "Coconut Curry", ["1 can coconut milk", "2 tomatoes", "1 onion"],
     ["coconut milk", "tomato", "onion"], 8),
]


def make_db(path):
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE recipes (id VARCHAR, row_idx INTEGER, title VARCHAR, "
                "ingredients_clean VARCHAR[])")
    con.execute("CREATE TABLE recipe_stats (row_idx INTEGER, id VARCHAR, "
                "n_ingredients INTEGER, n_lines INTEGER, n_steps INTEGER)")
    con.execute("CREATE TABLE recipe_ingredient (recipe_id VARCHAR, row_idx INTEGER, "
                "position INTEGER, name_index INTEGER, canonical VARCHAR)")
    for row_idx, rid, title, lines, names, steps in RECIPES:
        con.execute("INSERT INTO recipes VALUES (?, ?, ?, ?)",
                    [rid, row_idx, title, lines])
        con.execute("INSERT INTO recipe_stats VALUES (?, ?, ?, ?, ?)",
                    [row_idx, rid, len(names), len(lines), steps])
        for pos, canon in enumerate(names):
            con.execute("INSERT INTO recipe_ingredient VALUES (?, ?, ?, 0, ?)",
                        [rid, row_idx, pos, canon])
    con.close()
    return path


def fake_encoder(texts):
    """Deterministic bag-of-words hashing encoder (256 dims, L2-normalized)."""
    out = np.zeros((len(texts), 256), dtype="float32")
    for i, text in enumerate(texts):
        for tok in tokenize(text):
            out[i, zlib.crc32(tok.encode()) % 256] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return out / norms


@pytest.fixture()
def env(tmp_path):
    """Tiny database + real BM25/FAISS indexes built from it (fake encoder)."""
    db_path = make_db(tmp_path / "t.duckdb")
    idx_dir = tmp_path / "idx"
    build_bm25(db_path, idx_dir / "bm25.pkl")
    build_embeddings(db_path, idx_dir, encoder=fake_encoder, shard_size=4)
    con = duckdb.connect(str(db_path), read_only=True)
    ids = [r[1] for r in RECIPES]
    flags = AllergenFlags.load_or_build(
        con, TAXONOMY, ids_fingerprint(ids), tmp_path / "flags.npz")
    retriever = HybridRetriever(
        con,
        Bm25Index.load(idx_dir / "bm25.pkl"),
        SemanticIndex.load(idx_dir, encoder=fake_encoder),
        RecipeStats(con, variants={}),
        flags,
        AllergenMatcher(TAXONOMY),
        pool_size=50,
    )
    yield retriever, con, tmp_path, ids
    con.close()


# ---- RRF -------------------------------------------------------------------
def test_rrf_scores_match_formula():
    fused = dict(rrf_fuse([[10, 20, 30], [20, 10]], k=60))
    assert fused[10] == pytest.approx(1 / 61 + 1 / 62)
    assert fused[20] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[30] == pytest.approx(1 / 63)


def test_rrf_document_in_both_lists_beats_first_in_one():
    fused = rrf_fuse([[1, 2, 3], [4, 2, 5]], k=60)
    assert fused[0][0] == 2      # rank 2 in both beats rank 1 in only one list


def test_rrf_ties_broken_by_row_idx_and_deterministic():
    assert [d for d, _ in rrf_fuse([[7], [3]], k=60)] == [3, 7]


def test_rrf_weights_and_duplicates():
    heavy = rrf_fuse([[1], [2]], k=60, weights=[1.0, 3.0])
    assert heavy[0][0] == 2
    dup = dict(rrf_fuse([[5, 5, 6]], k=60))
    assert dup[5] == pytest.approx(1 / 61)
    assert dup[6] == pytest.approx(1 / 62)   # duplicate did not push 6 down
    with pytest.raises(ValueError):
        rrf_fuse([[1]], weights=[1.0, 2.0])


# ---- allergen flags ------------------------------------------------------------
def test_compute_flags_uses_full_line_and_exceptions():
    matcher = AllergenMatcher(TAXONOMY)
    rows = [(i, r[3]) for i, r in enumerate(RECIPES)]
    flags = compute_flags(rows, matcher, len(RECIPES), log_every=0)
    assert flags["dairy"].tolist() == [True, False, False, False, False, False]
    assert flags["peanut"].tolist() == [False, False, True,
                                        False, False, False]
    assert flags["egg"].tolist() == [False, False, True, False, False, False]


def test_allergen_cache_roundtrip_and_invalidation(env):
    _, con, tmp_path, ids = env
    path = tmp_path / "flags.npz"
    assert path.exists()
    again = AllergenFlags.load_or_build(
        con, TAXONOMY, ids_fingerprint(ids), path)
    assert again.contains("dairy").tolist() == [
        True, False, False, False, False, False]
    # A changed taxonomy must NOT reuse the old cache.
    changed = {**TAXONOMY, "dairy": {"include": ["milk"], "exceptions": []}}
    assert taxonomy_hash(changed) != taxonomy_hash(TAXONOMY)
    rebuilt = AllergenFlags.load_or_build(
        con, changed, ids_fingerprint(ids), path)
    assert rebuilt.contains("dairy").tolist() == [
        False, False, False, False, False, True]


def test_unknown_allergen_raises(env):
    retriever, *_ = env
    with pytest.raises(ValueError):
        retriever.search("soup", Constraints(exclude_allergens=("gluten",)))


# ---- masks ----------------------------------------------------------------------
def test_mask_exclude_include_and_max_steps(env):
    retriever, *_ = env
    mask, _ = retriever.allowed_mask(Constraints(exclude=("egg",)))
    assert mask.tolist() == [True, True, False, True, True, True]
    mask, _ = retriever.allowed_mask(Constraints(include=("garlic", "tomato")))
    assert mask.tolist() == [False, False, False, False, True, False]
    mask, _ = retriever.allowed_mask(Constraints(max_steps=5))
    # recipe 3 has 0 steps (unknown length) and must NOT pass "max 5 steps"
    assert mask.tolist() == [True, True, True, False, False, False]


def test_empty_constraints_allow_everything(env):
    retriever, *_ = env
    mask, sql = retriever.allowed_mask(Constraints())
    assert mask.all() and "no SQL" in sql


def test_unknown_ingredient_is_not_silently_ignored(env):
    retriever, *_ = env
    with pytest.raises(UnknownIngredientError):
        retriever.search("soup", Constraints(exclude=("unicornfruit",)))


# ---- search -----------------------------------------------------------------------
def test_search_finds_the_obvious_recipe(env):
    retriever, *_ = env
    res = retriever.search("garlic bread", k=3)
    assert res.hits[0].id == "a:1"
    assert res.n_allowed == res.n_total == 6
    assert res.hits[0].bm25_rank == 1 and res.hits[0].semantic_rank is not None


def test_hard_constraints_are_never_violated(env):
    retriever, *_ = env
    cases = [
        Constraints(exclude_allergens=("dairy",)),
        Constraints(exclude_allergens=("egg", "peanut")),
        Constraints(exclude=("garlic",), max_steps=6),
        Constraints(include=("tomato",), exclude_allergens=("dairy",)),
    ]
    for constraints in cases:
        for query in ("garlic bread", "tomato", "cookies sugar", "pasta"):
            res = retriever.search(query, constraints, k=6)
            assert retriever.verify(res.hits, constraints) == []
            allowed, _ = retriever.allowed_mask(constraints)
            assert all(allowed[h.row_idx] for h in res.hits)


def test_dairy_allergen_removes_butter_but_keeps_coconut_milk(env):
    retriever, *_ = env
    res = retriever.search("garlic", Constraints(
        exclude_allergens=("dairy",)), k=6)
    ids = [h.id for h in res.hits]
    assert "a:1" not in ids          # garlic bread has butter
    assert "a:5" in ids              # garlic tomato pasta is dairy-free
    res = retriever.search("curry", Constraints(exclude_allergens=("dairy",)))
    assert "a:6" in [h.id for h in res.hits]   # coconut milk is an exception


def test_no_eligible_recipe_says_so_and_relaxes_nothing(env):
    retriever, *_ = env
    res = retriever.search("tomato", Constraints(
        include=("garlic",), exclude=("garlic",)))
    assert res.hits == [] and res.n_allowed == 0
    assert "nothing was relaxed" in res.note


def test_empty_query_returns_note_not_random_recipes(env):
    retriever, *_ = env
    res = retriever.search("   ")
    assert res.hits == [] and "Empty query" in res.note


def test_result_reports_denominator_and_sql(env):
    retriever, *_ = env
    res = retriever.search("soup", Constraints(exclude=("egg",)))
    assert res.n_allowed == 5 and res.n_total == 6
    assert "recipe_stats" in res.mask_sql
    assert set(res.timings_ms) >= {"mask", "bm25", "semantic"}


def test_format_result_shows_constraints_denominator_and_ranks(env):
    retriever, *_ = env
    text = format_result(retriever.search(
        "garlic bread", Constraints(exclude=("egg",)), k=2))
    assert "allowed      : 5 of 6" in text
    assert "Garlic Bread" in text and "bm25=#1" in text


def test_verify_detects_a_violation(env):
    retriever, *_ = env
    res = retriever.search("peanut cookies", k=3)
    problems = retriever.verify(
        res.hits, Constraints(exclude_allergens=("peanut",)))
    assert any("a:3" in p and "peanut" in p for p in problems)


# ---- fusion with stub retrievers (control the two rankings exactly) --------------------
class StubBm25:
    def __init__(self, ids, ranking):
        self.ids, self._ranking = ids, ranking

    def top_k(self, query, k=10, allowed=None):
        rows = [r for r in self._ranking if allowed is None or allowed[r]]
        return [(r, 10.0 - i) for i, r in enumerate(rows[:k])]


class StubSemantic:
    def __init__(self, n, ranking, fingerprint):
        self.meta = {"fingerprint": fingerprint}
        self._ranking = ranking
        self.index = type("Idx", (), {"ntotal": n})()

    def search(self, query, k=10):
        return [(r, 1.0 - 0.01 * i) for i, r in enumerate(self._ranking[:k])]


def stub_retriever(env, bm25_order, sem_order, **kwargs):
    _, con, tmp_path, ids = env
    flags = AllergenFlags.load_or_build(
        con, TAXONOMY, ids_fingerprint(ids), tmp_path / "flags.npz")
    return HybridRetriever(
        con, StubBm25(ids, bm25_order),
        StubSemantic(len(ids), sem_order, ids_fingerprint(ids)),
        RecipeStats(con, variants={}), flags, AllergenMatcher(TAXONOMY), **kwargs)


def test_fusion_promotes_recipe_found_by_both(env):
    r = stub_retriever(env, [0, 4, 1], [3, 4, 5])
    res = r.search("anything", k=3)
    assert res.hits[0].row_idx == 4
    assert (res.hits[0].bm25_rank, res.hits[0].semantic_rank) == (2, 2)


def test_semantic_only_recipe_is_kept_by_the_hybrid(env):
    r = stub_retriever(env, [0], [5, 0])
    res = r.search("anything", k=5)
    by_id = {h.row_idx: h for h in res.hits}
    assert by_id[5].bm25_rank is None and by_id[5].semantic_rank == 1


def test_restrictive_mask_still_finds_a_low_ranked_semantic_match(env):
    # Only recipe 0 is allowed, but it is the LAST in the semantic order.
    r = stub_retriever(env, [0], [5, 4, 3, 2, 1, 0])
    res = r.search("anything", Constraints(include=("butter",)), k=3)
    assert [h.row_idx for h in res.hits] == [0]
    assert res.hits[0].semantic_rank == 1   # rank among ALLOWED recipes


def test_weights_change_the_order(env):
    base = stub_retriever(env, [0, 1], [1, 0])
    assert base.search("x", k=2).hits[0].row_idx == 0   # tie broken by row_idx
    semantic_heavy = stub_retriever(env, [0, 1], [1, 0], semantic_weight=3.0)
    assert semantic_heavy.search("x", k=2).hits[0].row_idx == 1


# ---- alignment guard -----------------------------------------------------------------------
def test_misaligned_semantic_index_is_rejected(env):
    _, con, tmp_path, ids = env
    flags = AllergenFlags.load_or_build(
        con, TAXONOMY, ids_fingerprint(ids), tmp_path / "flags.npz")
    bad = StubSemantic(len(ids), [0], "wrongfingerprint")
    with pytest.raises(RuntimeError):
        HybridRetriever(con, StubBm25(ids, [0]), bad, RecipeStats(con, variants={}),
                        flags, AllergenMatcher(TAXONOMY))


def test_misaligned_bm25_is_rejected(env):
    _, con, tmp_path, ids = env
    flags = AllergenFlags.load_or_build(
        con, TAXONOMY, ids_fingerprint(ids), tmp_path / "flags.npz")
    wrong_ids = list(reversed(ids))
    with pytest.raises(RuntimeError):
        HybridRetriever(con, StubBm25(wrong_ids, [0]),
                        StubSemantic(len(ids), [0], ids_fingerprint(ids)),
                        RecipeStats(con, variants={}), flags, AllergenMatcher(TAXONOMY))


# ---- REAL indexes (skipped until built) ---------------------------------------------------------
@pytest.mark.skipif(not (BM25_PATH.exists() and FAISS_PATH.exists()),
                    reason="real indexes not built")
def test_real_hybrid_respects_sql_constraints():
    from recipebot.db import connect

    con = connect(read_only=True)
    try:
        r = HybridRetriever.from_disk(con)
        constraints = Constraints(exclude=("egg",), max_steps=8)
        res = r.search("banana bread", constraints, k=5)
        assert res.hits
        assert r.verify(res.hits, constraints) == []
        assert res.n_allowed < res.n_total
    finally:
        con.close()
