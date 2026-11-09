"""Ingredient matching, Task 2 (Step 10). Deterministic: no LLM, no embeddings.

Input : the ingredients the user HAS, plus the hard constraints (a Step 7 mask).
Output: existing recipes ranked by how well they fit, each with the evidence:
        matched / missing / extra-needed ingredients and the step count.

Vocabulary used in the answer (the assignment's M, N, E):
  matched  (M)  you have it AND the recipe uses it
  missing  (N)  you have it, the recipe does NOT use it
  extra    (E)  the recipe needs it, you did not list it (pantry staples excluded)

How the matching works
  * Your words are normalized like dataset lines (quantity stripped, plural removed,
    synonyms applied) and resolved with RecipeStats.resolve, so "contains" has the
    same definition as in the statistics answers.
  * Forms follow the variant map (data/taxonomy/ingredient_variants.yaml): "butter"
    and "unsalted butter" are ONE ingredient here (recipe_ingredient.canonical_base).
    Other forms stay different: "garlic" != "garlic powder", "milk" != "coconut milk".
  * A recipe line "butter or margarine" is satisfied by either name (alternatives).
  * Matching is done in ONE SQL query over recipe_ingredient; the hard constraints
    come from a boolean mask; the score is computed here with the weights from config.
  * Recipes with 0 steps (no instructions) are not ranked.
  * Step 10b: an ingredient the user lists is also dropped (and reported) when it is
    covered by an excluded ALLERGEN ("eggs" while "no egg" is active), not only when it
    is an excluded ingredient. Otherwise it would count as "missing" in every result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import yaml

from recipebot import config
from recipebot.normalization.allergens import AllergenMatcher
from recipebot.normalization.ingredients import (
    IngredientNormalizer,
    load_extra_descriptors,
    load_synonyms,
)
from recipebot.retrieval.masks import Constraints
from recipebot.tools.stats import RecipeStats, UnknownIngredientError

logger = logging.getLogger(__name__)

QUANTITY_NOTE = ("Ingredient names match, but quantity sufficiency could not be "
                 "verified from the dataset.")

REQUIRED_COLUMNS = {"canonical", "canonical_base", "alternatives"}


# ----------------------------------------------------------------------
# Small data classes
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class MatchSettings:
    """Scoring weights. Defaults come from config.py; tests pass their own."""

    w_coverage: float = config.MATCH_W_COVERAGE
    w_extra: float = config.MATCH_W_EXTRA
    w_steps: float = config.MATCH_W_STEPS
    step_cap: int = config.MATCH_STEP_CAP
    min_matched: int = config.MATCH_MIN_MATCHED

    def describe(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class Term:
    """One ingredient the user has, resolved to dataset names."""

    text: str                 # what the user typed ("2 eggs")
    base: str                 # variant-map base ("egg", "butter")
    names: tuple[str, ...]    # every canonical form counted as this ingredient


@dataclass
class MatchHit:
    """One ranked recipe with the evidence for its rank."""

    row_idx: int
    id: str
    title: str
    score: float
    coverage: float           # matched / ingredients listed by the user
    extra_ratio: float        # extra needed / ingredients the recipe needs
    n_steps: int
    n_matched: int
    n_core: int               # ingredients the recipe needs, pantry staples not counted
    n_extra: int
    matched: list[str] = field(default_factory=list)
    # "missing" in the assignment's words
    unused: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    # assumed at home, not scored
    staples: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    terms: list[str]                   # base names actually used
    unknown: list[dict[str, Any]]      # [{"term": ..., "suggestions": [...]}]
    dropped: list[str]                 # listed by the user but also excluded
    constraints: dict[str, Any]
    n_total: int                       # all usable recipes
    n_candidates: int                  # recipes that use at least one of the ingredients
    # candidates that pass the hard filters and have steps
    n_eligible: int
    hits: list[MatchHit]
    settings: dict[str, Any]
    note: str = ""
    sql: str = ""
    mask_sql: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "hits": [h.__dict__ for h in self.hits]}


# ----------------------------------------------------------------------
# Pantry staples
# ----------------------------------------------------------------------
def load_staples(path: Path | str | None = None) -> list[str]:
    """Read data/taxonomy/pantry_staples.yaml (empty list, with a warning, if missing)."""
    path = Path(path) if path else config.PANTRY_STAPLES_PATH
    if not path.exists():
        logger.warning(
            "Pantry staples file not found: %s (no staples assumed)", path)
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(x).strip().lower() for x in (data.get("staples") or []) if str(x).strip()]


# ----------------------------------------------------------------------
# The matcher
# ----------------------------------------------------------------------
class RecipeMatcher:
    def __init__(
        self,
        con,
        stats: RecipeStats,
        *,
        staples: Iterable[str] | None = None,
        normalizer: IngredientNormalizer | None = None,
        settings: MatchSettings | None = None,
        allergen_matcher: AllergenMatcher | None = None,
    ):
        self.con = con
        self.stats = stats
        self.settings = settings or MatchSettings()
        # used only to drop listed ingredients that an excluded allergen covers
        self.allergen_matcher = allergen_matcher
        self.normalizer = normalizer or IngredientNormalizer(
            load_synonyms(), load_extra_descriptors())
        self._require_columns()
        self.base_of: dict[str, str] = {
            v: base for base, vs in stats.variants.items() for v in vs}
        self.staples: frozenset[str] = self._expand_staples(
            load_staples() if staples is None else staples)

    # -- setup -------------------------------------------------------------
    def _require_columns(self) -> None:
        rows = self.con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'recipe_ingredient'").fetchall()
        missing = REQUIRED_COLUMNS - {r[0] for r in rows}
        if missing:
            raise RuntimeError(
                f"recipe_ingredient has no column(s) {sorted(missing)}. Rebuild the normalized "
                "tables: python -m recipebot.build_normalized")

    def _forms(self, base: str) -> list[str]:
        """Base first, then its variants that exist in the dataset."""
        vocab = self.stats.vocab
        return [base] + [v for v in self.stats.variants.get(base, [])
                         if v in vocab and v != base]

    def _expand_staples(self, names: Iterable[str]) -> frozenset[str]:
        """Staples plus their variant-map base and forms (so 'olive oil' covers its variants)."""
        out: set[str] = set()
        for name in names:
            name = name.strip().lower()
            if name not in self.stats.vocab:
                logger.warning(
                    "Pantry staple '%s' is not a canonical name in the dataset", name)
            base = self.base_of.get(name, name)
            out.update([name, base, *self._forms(base)])
        return frozenset(out)

    # -- reading the user's words --------------------------------------------
    def _resolve_term(self, raw: str) -> Term:
        """'2 eggs' -> Term(base='egg'). Raises UnknownIngredientError."""
        text = " ".join(raw.lower().split())
        attempts = [c for c in (self.normalizer.canonical(text), text) if c]
        error: UnknownIngredientError | None = None
        for candidate in dict.fromkeys(attempts):
            try:
                resolved = self.stats.resolve(candidate)
            except UnknownIngredientError as exc:
                error = exc
                continue
            base = self.base_of.get(resolved.base, resolved.base)
            names = tuple(dict.fromkeys(
                [base, resolved.base, *self._forms(base)]))
            return Term(text=raw, base=base, names=names)
        assert error is not None
        raise error

    def _excluded_bases(self, excluded: Iterable[str]) -> set[str]:
        bases: set[str] = set()
        for term in excluded:
            for name in self.stats.resolve(term).names:
                bases.add(self.base_of.get(name, name))
        return bases

    def _allergen_hit(self, term: Term, allergens: Sequence[str],
                      matcher: AllergenMatcher | None) -> str | None:
        """The excluded allergen that covers this ingredient ("egg" for egg), else None.

        Uses the same whole-word taxonomy as the recipe filter, on the term's base name and
        on every form of it ("butter", "unsalted butter"), so "coconut milk" is not dairy.
        """
        if not allergens:
            return None
        if matcher is None:
            raise ValueError(
                "An allergen matcher is required when allergens are excluded.")
        for allergen in allergens:
            for text in dict.fromkeys([term.base, *term.names]):
                if matcher.matches(text, allergen):
                    return allergen
        return None

    def prepare_terms(
        self, available: Sequence[str], excluded: Iterable[str] = (),
        excluded_allergens: Sequence[str] = (),
        allergen_matcher: AllergenMatcher | None = None,
    ) -> tuple[list[Term], list[dict[str, Any]], list[str]]:
        """Returns (terms, unknown, dropped). Nothing is ignored silently.

        A listed ingredient is dropped (and named in `dropped`) when it is an excluded
        ingredient OR is covered by an excluded allergen.
        """
        matcher = allergen_matcher or self.allergen_matcher
        banned = self._excluded_bases(excluded)
        terms: list[Term] = []
        unknown: list[dict[str, Any]] = []
        dropped: list[str] = []
        for raw in available:
            try:
                term = self._resolve_term(raw)
            except UnknownIngredientError as exc:
                unknown.append({"term": raw, "suggestions": exc.suggestions})
                continue
            if term.base in banned or self._allergen_hit(term, excluded_allergens, matcher):
                if term.base not in dropped:
                    dropped.append(term.base)
            elif all(term.base != t.base for t in terms):
                terms.append(term)
        return terms, unknown, dropped

    # -- the one SQL query ------------------------------------------------------
    def _candidate_query(self, terms: list[Term]) -> tuple[str, list[Any]]:
        """Per recipe that uses at least one of the ingredients:
        row_idx, n_core, n_extra, n_matched, n_steps.

        req = one row per (recipe, required ingredient), where an ingredient is a
        canonical_base. 'covered' = the user has it (directly or as an alternative
        in "A or B"); 'is_staple' = a pantry staple.
        """
        staples = sorted(self.staples) or [""]
        user_bases = [t.base for t in terms]
        user_names = sorted({n for t in terms for n in t.names})
        params: list[Any] = [staples, staples, user_bases, user_names]
        term_columns = []
        for i, term in enumerate(terms):
            term_columns.append(
                f"bool_or(ri.canonical_base = ? OR coalesce(list_has_any(ri.alternatives, ?), false)) AS t{i}")
            params += [term.base, list(term.names)]
        matched_sum = " + ".join(
            f"CAST(bool_or(t{i}) AS INTEGER)" for i in range(len(terms)))
        sql = (
            "WITH req AS (SELECT ri.row_idx, ri.canonical_base AS base, "
            "bool_or(list_contains(?, ri.canonical) OR list_contains(?, ri.canonical_base)) AS is_staple, "
            "bool_or(list_contains(?, ri.canonical_base) OR coalesce(list_has_any(ri.alternatives, ?), false)) AS covered, "
            + ", ".join(term_columns) +
            " FROM recipe_ingredient ri GROUP BY ri.row_idx, ri.canonical_base) "
            "SELECT req.row_idx, "
            "count(*) FILTER (WHERE NOT is_staple OR covered) AS n_core, "
            "count(*) FILTER (WHERE NOT is_staple AND NOT covered) AS n_extra, "
            f"({matched_sum}) AS n_matched, rs.n_steps "
            "FROM req JOIN recipe_stats rs ON rs.row_idx = req.row_idx "
            "GROUP BY req.row_idx, rs.n_steps HAVING bool_or(covered)"
        )
        return sql, params

    # -- ranking -------------------------------------------------------------------
    def match(
        self,
        available: Sequence[str],
        constraints: Constraints,
        allowed: np.ndarray,
        mask_sql: str = "",
        k: int = 5,
        allergen_matcher: AllergenMatcher | None = None,
    ) -> MatchResult:
        """Rank recipes. `allowed` is the hard-constraint mask (True = may be returned)."""
        cfg = self.settings
        terms, unknown, dropped = self.prepare_terms(
            available, constraints.exclude, constraints.exclude_allergens, allergen_matcher)

        def result(hits: list[MatchHit], n_candidates=0, n_eligible=0, note="", sql="") -> MatchResult:
            return MatchResult(
                terms=[t.base for t in terms], unknown=unknown, dropped=dropped,
                constraints=constraints.describe(), n_total=len(allowed),
                n_candidates=n_candidates, n_eligible=n_eligible, hits=hits,
                settings=cfg.describe(), note=note, sql=sql, mask_sql=mask_sql)

        if not terms:
            return result([], note="None of your ingredients could be used "
                                   "(unknown names or excluded ingredients).")
        sql, params = self._candidate_query(terms)
        rows = self.con.execute(sql, params).fetchall()
        n_candidates = len(rows)
        if not rows:
            return result([], 0, 0, "No recipe uses any of your ingredients.", sql)

        # row_idx, n_core, n_extra, n_matched, n_steps
        data = np.array(rows, dtype=np.int64)
        keep = (allowed[data[:, 0]] & (data[:, 4] >= 1)
                & (data[:, 3] >= cfg.min_matched))
        data = data[keep]
        n_eligible = len(data)
        if n_eligible == 0:
            return result([], n_candidates, 0,
                          "No recipe uses your ingredients and satisfies the hard constraints; "
                          "nothing was relaxed.", sql)

        coverage = data[:, 3] / len(terms)
        extra_ratio = data[:, 2] / np.maximum(data[:, 1], 1)
        score = (cfg.w_coverage * coverage - cfg.w_extra * extra_ratio
                 - cfg.w_steps * np.minimum(data[:, 4], cfg.step_cap))
        # best score first; ties: fewer steps, then build order (row_idx). Deterministic.
        order = np.lexsort((data[:, 0], data[:, 4], -np.round(score, 9)))[:k]
        hits = self._build_hits(terms, data[order], coverage[order],
                                extra_ratio[order], score[order])
        return result(hits, n_candidates, n_eligible, sql=sql)

    # -- evidence for the top k ---------------------------------------------------
    def _build_hits(self, terms, data, coverage, extra_ratio, score) -> list[MatchHit]:
        row_idxs = [int(r) for r in data[:, 0]]
        marks = ",".join("?" * len(row_idxs))
        info = {r: (rid, title) for r, rid, title in self.con.execute(
            f"SELECT row_idx, id, title FROM recipes WHERE row_idx IN ({marks})", row_idxs).fetchall()}
        lines: dict[int, list[tuple]] = {r: [] for r in row_idxs}
        for row_idx, canonical, base, alternatives in self.con.execute(
                "SELECT row_idx, canonical, canonical_base, alternatives FROM recipe_ingredient "
                f"WHERE row_idx IN ({marks}) ORDER BY row_idx, position, name_index", row_idxs).fetchall():
            lines[row_idx].append((canonical, base, list(alternatives or [])))

        hits = []
        for i, row_idx in enumerate(row_idxs):
            matched, unused, extra, staples = self.explain(
                terms, lines[row_idx])
            hits.append(MatchHit(
                row_idx=row_idx, id=info[row_idx][0], title=info[row_idx][1],
                score=float(score[i]), coverage=float(coverage[i]),
                extra_ratio=float(extra_ratio[i]), n_steps=int(data[i, 4]),
                n_matched=int(data[i, 3]), n_core=int(data[i, 1]), n_extra=int(data[i, 2]),
                matched=matched, unused=unused, extra=extra, staples=staples))
        return hits

    def explain(self, terms: list[Term], rows: list[tuple]) -> tuple[list[str], list[str], list[str], list[str]]:
        """Python version of the SQL logic for ONE recipe: (matched, unused, extra, staples).

        rows = [(canonical, canonical_base, alternatives), ...] in recipe order.
        Used for the answer text; verify() checks it against the SQL numbers.
        """
        required: dict[str, dict[str, Any]] = {}
        for canonical, base, alternatives in rows:
            entry = required.setdefault(
                base, {"staple": False, "terms": set()})
            if canonical in self.staples or base in self.staples:
                entry["staple"] = True
            for i, term in enumerate(terms):
                if base == term.base or set(alternatives) & set(term.names):
                    entry["terms"].add(i)
        used = sorted({i for e in required.values() for i in e["terms"]})
        matched = [terms[i].base for i in used]
        unused = [t.base for i, t in enumerate(terms) if i not in used]
        extra = [b for b, e in required.items() if not e["terms"]
                 and not e["staple"]]
        staples = [b for b, e in required.items() if not e["terms"]
                   and e["staple"]]
        return matched, unused, extra, staples

    # -- independent check -----------------------------------------------------------
    def verify(self, res: MatchResult) -> list[str]:
        """The SQL numbers and the Python lists must agree. [] means consistent."""
        problems = []
        for h in res.hits:
            if len(h.matched) != h.n_matched:
                problems.append(
                    f"{h.id}: {h.n_matched} matched by SQL but {len(h.matched)} listed")
            if len(h.extra) != h.n_extra:
                problems.append(
                    f"{h.id}: {h.n_extra} extra by SQL but {len(h.extra)} listed")
            if h.n_steps < 1:
                problems.append(f"{h.id}: has no instructions but was ranked")
            if sorted(h.matched + h.unused) != sorted(res.terms):
                problems.append(
                    f"{h.id}: matched + unused do not add up to your ingredients")
        return problems
