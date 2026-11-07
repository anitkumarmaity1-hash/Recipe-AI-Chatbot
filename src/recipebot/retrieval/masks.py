"""Hard-constraint masks for retrieval (Step 7).

A mask is a boolean numpy array with one entry per recipe, indexed by row_idx:
True = the recipe is ALLOWED, False = it is forbidden by a hard constraint.
The retrievers never return a recipe whose mask value is False.

Two sources of constraints:
  * SQL over recipe_stats / recipe_ingredient (required ingredients, excluded
    ingredients, maximum steps). Built by build_sql_mask().
  * Allergen categories (dairy, egg, ...). These are checked on the FULL
    cleaned ingredient line (not the canonical name), so they are computed in
    Python once per recipe and cached in a small .npz file (AllergenFlags).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from recipebot.normalization.allergens import AllergenMatcher
from recipebot.retrieval.common import ALLERGEN_FLAGS_PATH
from recipebot.tools.stats import Filter, RecipeStats

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Constraints:
    """Hard constraints. Every part is combined with AND and is never relaxed.

    include:           recipe must contain every listed ingredient
    exclude:           recipe must contain none of the listed ingredients
    exclude_allergens: allergen categories (see data/taxonomy/allergens.yaml)
    max_steps:         recipe must have between 1 and max_steps steps
                       (a recipe with 0 steps has unknown length, so it is
                       not eligible for a maximum-steps constraint)
    """

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    exclude_allergens: tuple[str, ...] = ()
    max_steps: int | None = None

    def __post_init__(self) -> None:
        for name in ("include", "exclude", "exclude_allergens"):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    def is_empty(self) -> bool:
        return not (self.include or self.exclude or self.exclude_allergens
                    or self.max_steps is not None)

    def describe(self) -> dict:
        return {
            "include": list(self.include),
            "exclude": list(self.exclude),
            "exclude_allergens": list(self.exclude_allergens),
            "max_steps": self.max_steps,
        }


def build_sql_mask(
    stats: RecipeStats, n: int, constraints: Constraints
) -> tuple[np.ndarray, str, list]:
    """Boolean mask for the SQL-based constraints. Returns (mask, sql, params).

    Reuses RecipeStats so "contains" has exactly the same definition as in the
    statistics answers (canonical names plus the variant map).
    Raises UnknownIngredientError for an ingredient not in the vocabulary
    (we never silently ignore a constraint).
    """
    flt = Filter(
        all_of=constraints.include,
        none_of=constraints.exclude,
        max_steps=constraints.max_steps,
        min_steps=1 if constraints.max_steps is not None else None,
    )
    conds, params = stats._conditions(flt)  # same package; see DESIGN.md
    if not conds:
        return np.ones(n, dtype=bool), "(no SQL constraints)", []
    sql = f"SELECT rs.row_idx FROM recipe_stats rs WHERE {stats._where(conds)}"
    rows = stats.con.execute(sql, params).fetchall()
    mask = np.zeros(n, dtype=bool)
    if rows:
        mask[np.fromiter((r[0] for r in rows), dtype=np.int64,
                         count=len(rows))] = True
    return mask, sql, params


def taxonomy_hash(taxonomy: dict) -> str:
    """Short hash of the allergen taxonomy; a changed YAML invalidates the cache."""
    blob = json.dumps(taxonomy, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def compute_flags(
    rows: Iterable[tuple[int, list[str] | None]],
    matcher: AllergenMatcher,
    n: int,
    log_every: int = 20_000,
) -> dict[str, np.ndarray]:
    """For each allergen: True where any cleaned ingredient line mentions it.

    Many recipes share identical lines ("1 cup milk"), so each distinct line
    is analysed once and remembered.
    """
    flags = {name: np.zeros(n, dtype=bool) for name in matcher.allergens}
    memo: dict[str, tuple[str, ...]] = {}
    t0 = time.perf_counter()
    for count, (row_idx, lines) in enumerate(rows, start=1):
        for line in lines or []:
            found = memo.get(line)
            if found is None:
                found = tuple(matcher.detect(line))
                memo[line] = found
            for allergen in found:
                flags[allergen][row_idx] = True
        if log_every and count % log_every == 0:
            logger.info("Allergen scan: %d recipes, %d distinct lines, %.0f s",
                        count, len(memo), time.perf_counter() - t0)
    return flags


class AllergenFlags:
    """Per-allergen 'recipe text mentions it' arrays, cached on disk."""

    def __init__(self, flags: dict[str, np.ndarray]):
        self._flags = flags

    @property
    def allergens(self) -> list[str]:
        return list(self._flags)

    def contains(self, allergen: str) -> np.ndarray:
        """Boolean array: True where the recipe's ingredient lines mention it."""
        if allergen not in self._flags:
            raise ValueError(
                f"Unknown allergen '{allergen}'. Known: {self.allergens}")
        return self._flags[allergen]

    @classmethod
    def load_or_build(
        cls,
        con,
        taxonomy: dict,
        fingerprint: str,
        path: Path | str | None = None,
    ) -> "AllergenFlags":
        """Use the cached file when it matches this database and taxonomy.

        Otherwise scan every recipe (slow the first time: it checks all
        ingredient lines) and write the cache atomically.
        """
        path = Path(path) if path else ALLERGEN_FLAGS_PATH
        wanted = taxonomy_hash(taxonomy)
        if path.exists():
            with np.load(path, allow_pickle=False) as data:
                if (str(data["fingerprint"]) == fingerprint
                        and str(data["taxonomy_hash"]) == wanted):
                    flags = {
                        key[len("flag_"):]: data[key]
                        for key in data.files if key.startswith("flag_")
                    }
                    logger.info("Loaded allergen flags from %s", path)
                    return cls(flags)
            logger.info("Allergen cache is outdated; rebuilding")

        n = con.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
        rows = con.execute(
            "SELECT row_idx, ingredients_clean FROM recipes ORDER BY row_idx"
        ).fetchall()
        logger.info("Scanning %d recipes for allergens (one-time, cached)", n)
        flags = compute_flags(rows, AllergenMatcher(taxonomy), n)

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.stem + ".tmp.npz")
        np.savez_compressed(
            tmp,
            fingerprint=np.array(fingerprint),
            taxonomy_hash=np.array(wanted),
            **{f"flag_{name}": arr for name, arr in flags.items()},
        )
        os.replace(tmp, path)
        return cls(flags)
