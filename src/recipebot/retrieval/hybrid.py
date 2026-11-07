"""Hybrid retrieval (Step 7): hard-constraint mask + BM25 + FAISS + RRF.

Flow for one query:
  1. Build the ALLOWED mask from the hard constraints (SQL + allergen flags).
  2. BM25 ranking, restricted to allowed recipes.
  3. Semantic (FAISS) ranking, restricted to allowed recipes.
  4. Fuse both rankings with Reciprocal Rank Fusion (RRF).
Hard constraints are applied BEFORE ranking and are never relaxed. Neither
retriever understands negation, so "without eggs" must arrive here as
Constraints(exclude=("egg",)), not inside the query text.

Try it (project root, venv active):
    python -m recipebot.retrieval.hybrid "penne pasta" --exclude-allergen dairy -k 5
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from recipebot import config
from recipebot.db import connect
from recipebot.normalization.allergens import AllergenMatcher, load_allergens
from recipebot.retrieval.bm25 import Bm25Index
from recipebot.retrieval.common import (
    BM25_WEIGHT,
    POOL_SIZE,
    RRF_K,
    SEMANTIC_WEIGHT,
    ids_fingerprint,
)
from recipebot.retrieval.embeddings import SemanticIndex
from recipebot.retrieval.masks import AllergenFlags, Constraints, build_sql_mask
from recipebot.tools.stats import RecipeStats, UnknownIngredientError

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Reciprocal Rank Fusion
# ----------------------------------------------------------------------
def rrf_fuse(
    rankings: Sequence[Sequence[int]],
    k: int = RRF_K,
    weights: Sequence[float] | None = None,
) -> list[tuple[int, float]]:
    """Fuse ranked lists of row_idx. score(d) = sum over lists of w / (k + rank).

    rank starts at 1. A recipe missing from a list gets nothing from that list.
    Ties are broken by lower row_idx, so the output is deterministic.
    """
    weights = list(weights) if weights is not None else [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("weights and rankings must have the same length")
    scores: dict[int, float] = defaultdict(float)
    for weight, ranking in zip(weights, rankings):
        seen: set[int] = set()
        rank = 0
        for row_idx in ranking:
            if row_idx in seen:      # a duplicate must not count twice
                continue
            seen.add(row_idx)
            rank += 1
            scores[row_idx] += weight / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


# ----------------------------------------------------------------------
# Result objects
# ----------------------------------------------------------------------
@dataclass
class Hit:
    """One recommended recipe with the evidence for its rank."""

    row_idx: int
    id: str
    title: str
    rrf_score: float
    bm25_rank: int | None = None        # 1-based; None = not in the BM25 pool
    bm25_score: float | None = None
    semantic_rank: int | None = None    # 1-based; None = not in the FAISS pool
    semantic_score: float | None = None


@dataclass
class HybridResult:
    query: str
    constraints: dict
    n_total: int                 # all usable recipes
    n_allowed: int               # recipes that pass the hard constraints
    hits: list[Hit]
    note: str = ""
    mask_sql: str = ""
    timings_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {**self.__dict__, "hits": [h.__dict__ for h in self.hits]}


# ----------------------------------------------------------------------
# The retriever
# ----------------------------------------------------------------------
class HybridRetriever:
    """Combines the mask, BM25, FAISS and RRF. Position in every structure == row_idx."""

    def __init__(
        self,
        con,
        bm25: Bm25Index,
        semantic: SemanticIndex,
        stats: RecipeStats,
        allergen_flags: AllergenFlags | Callable[[], AllergenFlags],
        matcher: AllergenMatcher,
        *,
        rrf_k: int = RRF_K,
        bm25_weight: float = BM25_WEIGHT,
        semantic_weight: float = SEMANTIC_WEIGHT,
        pool_size: int = POOL_SIZE,
    ):
        self.con = con
        self.bm25 = bm25
        self.semantic = semantic
        self.stats = stats
        self._flags = allergen_flags   # object, or a function that builds it on first use
        self.matcher = matcher
        self.rrf_k = rrf_k
        self.bm25_weight = bm25_weight
        self.semantic_weight = semantic_weight
        self.pool_size = pool_size
        self.n = len(bm25.ids)
        self._check_alignment()

    # -- construction ----------------------------------------------------
    @classmethod
    def from_disk(cls, con, **kwargs) -> "HybridRetriever":
        """Load BM25, FAISS, allergen flags and the statistics helper."""
        bm25 = Bm25Index.load()
        semantic = SemanticIndex.load()
        taxonomy = load_allergens()
        ids = [r[0] for r in con.execute(
            "SELECT id FROM recipes ORDER BY row_idx").fetchall()]
        fingerprint = ids_fingerprint(ids)
        # Lazy: the allergen scan (slow the first time, then cached) only runs
        # when a query actually uses an allergen constraint.
        return cls(con, bm25, semantic, RecipeStats(con),
                   lambda: AllergenFlags.load_or_build(
                       con, taxonomy, fingerprint),
                   AllergenMatcher(taxonomy), **kwargs)

    def _check_alignment(self) -> None:
        """BM25, FAISS and the database must describe the same recipes in the same order."""
        db_ids = [r[0] for r in self.con.execute(
            "SELECT id FROM recipes ORDER BY row_idx").fetchall()]
        if db_ids != list(self.bm25.ids):
            raise RuntimeError(
                "BM25 index does not match the database (different recipes or "
                "order). Rebuild: python -m recipebot.build_indexes bm25")
        fingerprint = ids_fingerprint(db_ids)
        if self.semantic.meta.get("fingerprint") != fingerprint:
            raise RuntimeError(
                "FAISS index does not match the database. Rebuild: "
                "python -m recipebot.build_indexes embeddings --force")
        if self.semantic.index.ntotal != len(db_ids):
            raise RuntimeError(
                "FAISS vector count differs from the recipe count.")

    @property
    def flags(self) -> AllergenFlags:
        if callable(self._flags):
            self._flags = self._flags()
        return self._flags

    # -- hard constraints ---------------------------------------------------
    def allowed_mask(self, constraints: Constraints) -> tuple[np.ndarray, str]:
        """True = recipe may be returned. Returns (mask, sql used)."""
        mask, sql, _ = build_sql_mask(self.stats, self.n, constraints)
        for allergen in constraints.exclude_allergens:
            # raises on unknown allergen
            mask &= ~self.flags.contains(allergen)
        return mask, sql

    # -- retrieval ------------------------------------------------------------
    def _semantic_ranking(self, query: str, allowed: np.ndarray) -> list[tuple[int, float]]:
        """Exact semantic top-N among ALLOWED recipes.

        FAISS IndexFlatIP is exact and cheap to search in full, so we ask for
        every vector, drop the forbidden ones and keep the first `pool_size`.
        This is simple and cannot lose a good allowed recipe when the
        constraint is restrictive.
        """
        everything = self.semantic.search(query, k=self.semantic.index.ntotal)
        kept = [(i, s) for i, s in everything if allowed[i]]
        return kept[: self.pool_size]

    def search(
        self, query: str, constraints: Constraints | None = None, k: int = 10
    ) -> HybridResult:
        constraints = constraints or Constraints()
        timings: dict[str, float] = {}

        t0 = time.perf_counter()
        allowed, sql = self.allowed_mask(constraints)
        timings["mask"] = 1000 * (time.perf_counter() - t0)
        n_allowed = int(allowed.sum())

        def result(hits: list[Hit], note: str = "") -> HybridResult:
            return HybridResult(
                query=query, constraints=constraints.describe(),
                n_total=self.n, n_allowed=n_allowed, hits=hits, note=note,
                mask_sql=sql, timings_ms=timings,
            )

        if n_allowed == 0:
            return result([], "No recipe satisfies the hard constraints; "
                              "nothing was relaxed.")
        if not query.strip():
            return result([], "Empty query: there is nothing to rank by.")

        t0 = time.perf_counter()
        bm25_hits = self.bm25.top_k(query, k=self.pool_size, allowed=allowed)
        timings["bm25"] = 1000 * (time.perf_counter() - t0)

        t0 = time.perf_counter()
        sem_hits = self._semantic_ranking(query, allowed)
        timings["semantic"] = 1000 * (time.perf_counter() - t0)

        fused = rrf_fuse(
            [[r for r, _ in bm25_hits], [r for r, _ in sem_hits]],
            k=self.rrf_k,
            weights=[self.bm25_weight, self.semantic_weight],
        )[:k]

        bm25_info = {r: (rank, s) for rank, (r, s) in enumerate(bm25_hits, 1)}
        sem_info = {r: (rank, s) for rank, (r, s) in enumerate(sem_hits, 1)}
        titles = self._titles([r for r, _ in fused])
        hits = []
        for row_idx, score in fused:
            b = bm25_info.get(row_idx, (None, None))
            s = sem_info.get(row_idx, (None, None))
            hits.append(Hit(
                row_idx=row_idx, id=self.bm25.ids[row_idx],
                title=titles[row_idx], rrf_score=score,
                bm25_rank=b[0], bm25_score=b[1],
                semantic_rank=s[0], semantic_score=s[1],
            ))
        return result(hits)

    def _titles(self, row_idxs: list[int]) -> dict[int, str]:
        if not row_idxs:
            return {}
        marks = ",".join("?" * len(row_idxs))
        rows = self.con.execute(
            f"SELECT row_idx, title FROM recipes WHERE row_idx IN ({marks})",
            row_idxs).fetchall()
        return {r: t for r, t in rows}

    # -- independent check ----------------------------------------------------
    def verify(self, hits: Sequence[Hit], constraints: Constraints) -> list[str]:
        """Re-check returned recipes WITHOUT using the mask. [] means no violation.

        Allergens are re-detected line by line, steps and ingredients are read
        from the database again. Used by tests now and by the output guard later.
        """
        problems: list[str] = []
        include = [set(self.stats.resolve(t).names)
                   for t in constraints.include]
        exclude = {
            n for t in constraints.exclude for n in self.stats.resolve(t).names}
        for hit in hits:
            lines, n_steps = self.con.execute(
                "SELECT r.ingredients_clean, rs.n_steps FROM recipes r "
                "JOIN recipe_stats rs ON rs.row_idx = r.row_idx WHERE r.row_idx = ?",
                [hit.row_idx]).fetchone()
            names = {r[0] for r in self.con.execute(
                "SELECT canonical FROM recipe_ingredient WHERE row_idx = ?",
                [hit.row_idx]).fetchall()}
            for allergen in constraints.exclude_allergens:
                for line in lines or []:
                    terms = self.matcher.matches(line, allergen)
                    if terms:
                        problems.append(
                            f"{hit.id}: {allergen} ({terms[0]}) in '{line}'")
                        break
            for bad in sorted(names & exclude):
                problems.append(
                    f"{hit.id}: excluded ingredient '{bad}' present")
            for term, wanted in zip(constraints.include, include):
                if not (names & wanted):
                    problems.append(
                        f"{hit.id}: required ingredient '{term}' missing")
            if constraints.max_steps is not None and not (1 <= n_steps <= constraints.max_steps):
                problems.append(f"{hit.id}: {n_steps} steps violates max_steps="
                                f"{constraints.max_steps}")
        return problems


# ----------------------------------------------------------------------
# Command-line demo
# ----------------------------------------------------------------------
def format_result(res: HybridResult) -> str:
    lines = [
        f"query        : {res.query!r}",
        f"constraints  : {res.constraints}",
        f"allowed      : {res.n_allowed} of {res.n_total} recipes pass the hard constraints",
        "timings (ms) : " +
        ", ".join(f"{k}={v:.0f}" for k, v in res.timings_ms.items()),
    ]
    if res.note:
        lines.append(f"note         : {res.note}")
    for pos, h in enumerate(res.hits, 1):
        bm = f"#{h.bm25_rank} ({h.bm25_score:.1f})" if h.bm25_rank else "-"
        se = f"#{h.semantic_rank} ({h.semantic_score:.2f})" if h.semantic_rank else "-"
        lines.append(f"{pos:>2}. {h.title}  [{h.id}]  rrf={h.rrf_score:.4f}  "
                     f"bm25={bm}  semantic={se}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    config.setup_logging(logging.WARNING)
    logging.getLogger("recipebot").setLevel(
        logging.INFO)  # show the one-time allergen scan
    parser = argparse.ArgumentParser(
        description="Hybrid recipe search (BM25 + FAISS + RRF).")
    parser.add_argument("query")
    parser.add_argument("--include", nargs="*", default=[])
    parser.add_argument("--exclude", nargs="*", default=[])
    parser.add_argument("--exclude-allergen", nargs="*", default=[])
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args(argv)

    constraints = Constraints(
        include=args.include, exclude=args.exclude,
        exclude_allergens=args.exclude_allergen, max_steps=args.max_steps)
    con = connect(read_only=True)
    try:
        retriever = HybridRetriever.from_disk(con)
        result = retriever.search(args.query, constraints, k=args.k)
        print(format_result(result))
        problems = retriever.verify(result.hits, constraints)
    except (UnknownIngredientError, ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}")
        return 2
    finally:
        con.close()
    print("verification : " + ("OK, no hard-constraint violation" if not problems
                               else "VIOLATIONS: " + "; ".join(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
