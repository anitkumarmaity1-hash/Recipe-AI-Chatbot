"""Deterministic statistics over the recipe database (Step 5).

No LLM is used here. Every public method returns a StatsResult that states
the value, the number of recipes analyzed, the filters, the definition of
"contains", and the exact SQL, so any answer can be audited.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from recipebot import config
from recipebot.db import connect

logger = logging.getLogger(__name__)

VARIANTS_PATH: Path = config.TAXONOMY_DIR / "ingredient_variants.yaml"

CONTAINS_DEFINITION = (
    "A recipe 'contains' an ingredient if at least one row of "
    "recipe_ingredient for that recipe has a canonical name equal to the "
    "ingredient or to one of its listed variants "
    "(data/taxonomy/ingredient_variants.yaml). All names on a line count "
    "('salt and pepper' counts both); names after 'or' (alternatives) do "
    "NOT count. Matching uses normalized canonical names, not free text."
)

STEP_RULE = (
    "One step = one sentence of the cleaned instructions (split with pysbd). "
    "Recipes with 0 steps (no usable instructions) are excluded from "
    "'fewest steps' rankings unless min_steps is set to 0. "
    "Ties are broken by recipe ID."
)

# Attributes the dataset does not contain: the chatbot must refuse, not guess.
UNSUPPORTED_KEYWORDS = (
    "cooking time", "cook time", "prep time", "how long",
    "calorie", "nutrition", "nutritional", "carbs", "cholesterol",
)


def unsupported_attribute(question: str) -> str | None:
    """Return a refusal message if the question needs data we do not have."""
    q = question.lower()
    for word in UNSUPPORTED_KEYWORDS:
        if word in q:
            return (
                "The Recipe Box dataset has no cooking-time or nutrition "
                "fields, so I cannot answer this from the data "
                f"(matched: '{word}')."
            )
    return None


class UnknownIngredientError(ValueError):
    """Raised when an ingredient name is not in the canonical vocabulary."""

    def __init__(self, term: str, suggestions: list[str]):
        self.term = term
        self.suggestions = suggestions
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        super().__init__(
            f"Ingredient '{term}' is not in the dataset vocabulary.{hint}")


@dataclass(frozen=True)
class Filter:
    """Conditions on recipes. All parts are combined with AND.

    all_of:  recipe must contain EVERY listed ingredient
    any_of:  recipe must contain AT LEAST ONE listed ingredient
    none_of: recipe must contain NONE of the listed ingredients
    """

    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    none_of: tuple[str, ...] = ()
    max_steps: int | None = None
    min_steps: int | None = None

    def __post_init__(self) -> None:
        # Accept lists from callers, store tuples (hashable, immutable).
        for name in ("all_of", "any_of", "none_of"):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    def describe(self) -> dict[str, Any]:
        return {
            "all_of": list(self.all_of),
            "any_of": list(self.any_of),
            "none_of": list(self.none_of),
            "max_steps": self.max_steps,
            "min_steps": self.min_steps,
        }


@dataclass
class StatsResult:
    """One auditable answer."""

    name: str
    value: Any
    n_analyzed: int
    filters: dict[str, Any]
    definition: str
    sql: str
    params: list[Any] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "n_analyzed": self.n_analyzed,
            "filters": self.filters,
            "definition_of_contains": self.definition,
            "sql": self.sql,
            "params": self.params,
            "details": self.details,
        }


def load_variants(path: Path | None = None) -> dict[str, list[str]]:
    """Load the variant map; a missing file means 'no variants'."""
    path = path or VARIANTS_PATH
    if not path.exists():
        logger.warning("Variants file not found: %s (using no variants)", path)
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _clean_variants(data)


def _clean_variants(data: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        str(base).strip().lower(): [str(v).strip().lower() for v in (vs or [])]
        for base, vs in data.items()
    }


@dataclass
class ResolvedTerm:
    term: str
    base: str
    names: list[str]  # base first, then variants that exist in the dataset


class RecipeStats:
    """Statistics tool. Pass an open DuckDB connection (read-only is fine)."""

    def __init__(self, con, variants: dict[str, list[str]] | None = None):
        self.con = con
        self.variants = load_variants() if variants is None else _clean_variants(variants)
        self._vocab: dict[str, int] | None = None

    # ------------------------------------------------------------------
    # Vocabulary and term resolution
    # ------------------------------------------------------------------
    @property
    def vocab(self) -> dict[str, int]:
        """canonical name -> number of recipes containing it (loaded once)."""
        if self._vocab is None:
            rows = self.con.execute(
                "SELECT canonical, COUNT(DISTINCT row_idx) "
                "FROM recipe_ingredient GROUP BY canonical"
            ).fetchall()
            self._vocab = {name: n for name, n in rows}
        return self._vocab

    @staticmethod
    def _candidates(term: str) -> list[str]:
        t = " ".join(term.lower().split())
        cands = [t]
        if t.endswith("ies"):
            cands.append(t[:-3] + "y")
        if t.endswith("es"):
            cands.append(t[:-2])
        if t.endswith("s"):
            cands.append(t[:-1])
        return cands

    def resolve(self, term: str) -> ResolvedTerm:
        """Map a user term to canonical names (base + existing variants)."""
        vocab = self.vocab
        for cand in self._candidates(term):
            if cand in vocab:
                names = [cand] + [
                    v for v in self.variants.get(cand, []) if v in vocab and v != cand
                ]
                return ResolvedTerm(term=term, base=cand, names=names)
        t = " ".join(term.lower().split())
        close = [n for n in vocab if t and t in n]
        close.sort(key=lambda n: -vocab[n])
        raise UnknownIngredientError(term, close[:8])

    # ------------------------------------------------------------------
    # SQL building
    # ------------------------------------------------------------------
    @staticmethod
    def _exists(names: list[str], negate: bool) -> tuple[str, list[str]]:
        placeholders = ",".join("?" * len(names))
        sql = (
            f"{'NOT ' if negate else ''}EXISTS (SELECT 1 FROM recipe_ingredient ri "
            f"WHERE ri.row_idx = rs.row_idx AND ri.canonical IN ({placeholders}))"
        )
        return sql, list(names)

    def _union_names(self, terms: tuple[str, ...]) -> list[str]:
        seen: list[str] = []
        for term in terms:
            for name in self.resolve(term).names:
                if name not in seen:
                    seen.append(name)
        return seen

    def _conditions(self, *filters: Filter) -> tuple[list[str], list[Any]]:
        """Build WHERE conditions (alias rs = recipe_stats) for AND-ed filters."""
        conds: list[str] = []
        params: list[Any] = []
        for f in filters:
            for term in f.all_of:
                sql, p = self._exists(self.resolve(term).names, negate=False)
                conds.append(sql)
                params += p
            if f.any_of:
                sql, p = self._exists(
                    self._union_names(f.any_of), negate=False)
                conds.append(sql)
                params += p
            if f.none_of:
                sql, p = self._exists(
                    self._union_names(f.none_of), negate=True)
                conds.append(sql)
                params += p
            if f.max_steps is not None:
                conds.append("rs.n_steps <= ?")
                params.append(int(f.max_steps))
            if f.min_steps is not None:
                conds.append("rs.n_steps >= ?")
                params.append(int(f.min_steps))
        return conds, params

    @staticmethod
    def _where(conds: list[str]) -> str:
        return " AND ".join(conds) if conds else "TRUE"

    def _terms_resolved(self, *filters: Filter) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for f in filters:
            for term in (*f.all_of, *f.any_of, *f.none_of):
                out[term] = self.resolve(term).names
        return out

    def _total(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM recipe_stats").fetchone()[0]

    def _count(self, *filters: Filter) -> tuple[int, str, list[Any]]:
        conds, params = self._conditions(*filters)
        sql = f"SELECT COUNT(*) FROM recipe_stats rs WHERE {self._where(conds)}"
        return self.con.execute(sql, params).fetchone()[0], sql, params

    # ------------------------------------------------------------------
    # Public tools
    # ------------------------------------------------------------------
    def count(self, flt: Filter | None = None) -> StatsResult:
        """How many recipes satisfy the filter (out of all usable recipes)."""
        flt = flt or Filter()
        n, sql, params = self._count(flt)
        return StatsResult(
            name="count",
            value=n,
            n_analyzed=self._total(),
            filters=flt.describe(),
            definition=CONTAINS_DEFINITION,
            sql=sql,
            params=params,
            details={"terms_resolved": self._terms_resolved(flt)},
        )

    def percentage(self, of: Filter, among: Filter | None = None) -> StatsResult:
        """Percent of recipes in `among` (default: all) that also satisfy `of`.

        value = 100 * numerator / denominator.
        """
        among = among or Filter()
        den, den_sql, den_params = self._count(among)
        num, num_sql, num_params = self._count(among, of)
        value = (100.0 * num / den) if den else None
        return StatsResult(
            name="percentage",
            value=value,
            n_analyzed=den,
            filters={"of": of.describe(), "among": among.describe()},
            definition=CONTAINS_DEFINITION,
            sql=f"numerator: {num_sql} | denominator: {den_sql}",
            params=[num_params, den_params],
            details={
                "numerator": num,
                "denominator": den,
                "calculation": f"{num} / {den} x 100" if den else "denominator is 0",
                "terms_resolved": self._terms_resolved(among, of),
            },
        )

    def ingredient_count_stats(self, flt: Filter | None = None) -> StatsResult:
        """Mean / median / min / max of n_ingredients (from recipe_stats)."""
        flt = flt or Filter()
        conds, params = self._conditions(flt)
        sql = (
            "SELECT COUNT(*), AVG(rs.n_ingredients), MEDIAN(rs.n_ingredients), "
            "MIN(rs.n_ingredients), MAX(rs.n_ingredients) "
            f"FROM recipe_stats rs WHERE {self._where(conds)}"
        )
        n, mean, median, lo, hi = self.con.execute(sql, params).fetchone()
        value = None
        if n:
            value = {"mean": float(mean), "median": float(
                median), "min": lo, "max": hi}
        return StatsResult(
            name="ingredient_count_stats",
            value=value,
            n_analyzed=n,
            filters=flt.describe(),
            definition=CONTAINS_DEFINITION,
            sql=sql,
            params=params,
            details={
                "metric": "n_ingredients as stored in recipe_stats "
                "(count of cleaned ingredient lines per recipe, excluding lines "
                "recognised as notes such as 'Special equipment:')",
                "terms_resolved": self._terms_resolved(flt),
            },
        )

    def top_common_ingredients(
        self,
        flt: Filter | None = None,
        k: int = 10,
        exclude_names: tuple[str, ...] = (),
    ) -> StatsResult:
        """Most common canonical ingredients among recipes matching the filter.

        Counts recipes (COUNT DISTINCT row_idx), not lines. Variants are NOT
        merged here: 'butter' and 'unsalted butter' are listed separately.
        """
        flt = flt or Filter()
        k = int(k)
        conds, params = self._conditions(flt)
        sql = (
            "SELECT ri.canonical, COUNT(DISTINCT ri.row_idx) AS n_recipes "
            "FROM recipe_ingredient ri "
            f"WHERE ri.row_idx IN (SELECT rs.row_idx FROM recipe_stats rs WHERE {self._where(conds)})"
        )
        all_params = list(params)
        if exclude_names:
            sql += f" AND ri.canonical NOT IN ({','.join('?' * len(exclude_names))})"
            all_params += [n.lower() for n in exclude_names]
        sql += f" GROUP BY ri.canonical ORDER BY n_recipes DESC, ri.canonical LIMIT {k}"
        rows = self.con.execute(sql, all_params).fetchall()
        n_analyzed, _, _ = self._count(flt)
        return StatsResult(
            name="top_common_ingredients",
            value=[{"ingredient": name, "n_recipes": n} for name, n in rows],
            n_analyzed=n_analyzed,
            filters={**flt.describe(), "k": k,
                     "exclude_names": list(exclude_names)},
            definition=CONTAINS_DEFINITION,
            sql=sql,
            params=all_params,
            details={"terms_resolved": self._terms_resolved(flt)},
        )

    def fewest_steps(
        self, flt: Filter | None = None, k: int = 5, min_steps: int = 1
    ) -> StatsResult:
        """The k recipes with the fewest steps among those matching the filter."""
        flt = flt or Filter()
        k = int(k)
        step_floor = Filter(min_steps=min_steps)
        conds, params = self._conditions(flt, step_floor)
        sql = (
            "SELECT rs.id, r.title, rs.n_steps "
            "FROM recipe_stats rs JOIN recipes r ON r.row_idx = rs.row_idx "
            f"WHERE {self._where(conds)} "
            f"ORDER BY rs.n_steps, rs.id LIMIT {k}"
        )
        rows = self.con.execute(sql, params).fetchall()
        n_analyzed, _, _ = self._count(flt, step_floor)
        return StatsResult(
            name="fewest_steps",
            value=[{"id": i, "title": t, "n_steps": s} for i, t, s in rows],
            n_analyzed=n_analyzed,
            filters={**flt.describe(), "k": k, "min_steps": min_steps},
            definition=CONTAINS_DEFINITION,
            sql=sql,
            params=params,
            details={"step_rule": STEP_RULE,
                     "terms_resolved": self._terms_resolved(flt)},
        )


# ----------------------------------------------------------------------
# Command-line demo: python -m recipebot.tools.stats <action> [options]
# ----------------------------------------------------------------------
def format_result(res: StatsResult) -> str:
    lines = [
        f"[{res.name}]",
        f"value        : {json.dumps(res.value, indent=2, default=str)}",
        f"n_analyzed   : {res.n_analyzed}",
        f"filters      : {json.dumps(res.filters)}",
        f"definition   : {res.definition}",
        f"sql          : {res.sql}",
        f"params       : {res.params}",
        f"details      : {json.dumps(res.details, indent=2, default=str)}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recipe statistics (deterministic).")
    parser.add_argument("action", choices=[
                        "count", "percent", "summary", "top", "steps"])
    parser.add_argument("--all-of", nargs="*", default=[])
    parser.add_argument("--any-of", nargs="*", default=[])
    parser.add_argument("--none-of", nargs="*", default=[])
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args(argv)

    flt = Filter(
        all_of=args.all_of, any_of=args.any_of, none_of=args.none_of,
        max_steps=args.max_steps,
    )
    con = connect(read_only=True)
    try:
        tool = RecipeStats(con)
        if args.action == "count":
            res = tool.count(flt)
        elif args.action == "percent":
            res = tool.percentage(flt)
        elif args.action == "summary":
            res = tool.ingredient_count_stats(flt)
        elif args.action == "top":
            res = tool.top_common_ingredients(flt, k=args.k)
        else:
            res = tool.fewest_steps(flt, k=args.k)
    except UnknownIngredientError as exc:
        print(exc)
        return 2
    finally:
        con.close()
    print(format_result(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
