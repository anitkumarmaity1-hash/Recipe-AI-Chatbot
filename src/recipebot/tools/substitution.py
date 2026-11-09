"""Substitution evidence mining, Task 3 (Step 11). Deterministic: no LLM, no embeddings.

Question answered: "The original recipe uses X. Which ingredients do OTHER recipes in the
dataset use instead, and which recipe ids prove it?" The answer is evidence, not a recipe:
writing the adapted recipe is Step 12.

How the evidence is found
  1. The original recipe is read from the database; the lines that contain X are located.
  2. Every other recipe gets a similarity to the original: the Jaccard overlap of the two
     "core" ingredient sets (X and pantry staples are left out of both sets).
  3. Two groups of related recipes (similarity >= SUB_RELATED_MIN_SIM) are formed:
       WITH    recipes that contain X        -> the baseline ("what recipes like this normally use")
       WITHOUT recipes that do NOT contain X -> where substitutes can be found
     Only the WITHOUT group is limited by the hard constraints (allergens, excluded
     ingredients, maximum steps) and by "has instructions"; every cited recipe obeys them.
     The WITH group is not limited, otherwise "no dairy" would empty the baseline when X is cream.
  4. Each WITHOUT recipe is labelled DIRECT (same dish family: similarity >= SUB_NEIGHBOR_MIN_SIM
     and a shared title word) or INDIRECT (related only).
  5. A candidate substitute must (a) appear in at least SUB_MIN_SUPPORT WITHOUT recipes,
     (b) be used more often there than in the WITH group (enrichment), (c) share a cooking role
     with X (data/taxonomy/ingredient_roles.yaml), (d) not be in the original recipe already, and
     (e) not break a hard constraint. Typical substitutes from the roles file are added too, but
     with their real dataset evidence (often "none").
  6. Evidence level of a candidate: direct (>= SUB_MIN_DIRECT_SUPPORT same-dish recipes),
     indirect (>= SUB_MIN_SUPPORT related recipes), none (cooking knowledge only).
Nothing here claims a substitution is medically safe.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import yaml

from recipebot import config
from recipebot.normalization.allergens import AllergenMatcher
from recipebot.retrieval.common import tokenize
from recipebot.retrieval.masks import Constraints
from recipebot.tools.stats import RecipeStats, UnknownIngredientError

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"canonical", "canonical_base", "raw_line", "position"}
LEVEL_RANK = {"direct": 0, "indirect": 1, "none": 2}
ROLE_SOURCE = ("general cooking knowledge (data/taxonomy/ingredient_roles.yaml), "
               "not evidence from the dataset")


class SubstitutionError(ValueError):
    """The request cannot be answered: unknown recipe, or the ingredient is not in that recipe."""


# ----------------------------------------------------------------------
# Settings and the roles file
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class SubstitutionSettings:
    """Thresholds. Defaults come from config.py; tests pass their own."""

    related_min_sim: float = config.SUB_RELATED_MIN_SIM
    neighbor_min_sim: float = config.SUB_NEIGHBOR_MIN_SIM
    min_title_overlap: int = config.SUB_MIN_TITLE_OVERLAP
    min_support: int = config.SUB_MIN_SUPPORT
    min_direct_support: int = config.SUB_MIN_DIRECT_SUPPORT
    min_enrichment: float = config.SUB_MIN_ENRICHMENT
    pool_size: int = config.SUB_POOL_SIZE
    max_candidates: int = config.SUB_MAX_CANDIDATES
    max_cited: int = config.SUB_MAX_CITED
    generic_title_words: frozenset[str] = frozenset(
        config.SUB_GENERIC_TITLE_WORDS)

    def describe(self) -> dict[str, Any]:
        out = dict(self.__dict__)
        out["generic_title_words"] = sorted(self.generic_title_words)
        return out


@dataclass
class Roles:
    """Content of ingredient_roles.yaml (general cooking knowledge)."""

    roles: dict[str, list[str]] = field(default_factory=dict)
    substitutes: dict[str, list[str]] = field(default_factory=dict)
    removal_effects: dict[str, str] = field(default_factory=dict)
    vocabulary: list[str] = field(default_factory=list)


def _lower_keys(mapping: dict | None) -> dict[str, Any]:
    return {str(k).strip().lower(): v for k, v in (mapping or {}).items()}


def load_roles(path: Path | str | None = None) -> Roles:
    """Read the roles file. A missing file gives an empty Roles (with a warning)."""
    path = Path(path) if path else config.INGREDIENT_ROLES_PATH
    if not path.exists():
        logger.warning(
            "Ingredient roles file not found: %s (no role knowledge)", path)
        return Roles()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Roles(
        roles={k: [str(r).strip().lower() for r in (v or [])]
               for k, v in _lower_keys(data.get("roles")).items()},
        substitutes={k: [str(s).strip().lower() for s in (v or [])]
                     for k, v in _lower_keys(data.get("substitutes")).items()},
        removal_effects={k: str(v).strip()
                         for k, v in _lower_keys(data.get("removal_effects")).items()},
        vocabulary=[str(r).strip().lower()
                    for r in (data.get("role_vocabulary") or [])],
    )


# ----------------------------------------------------------------------
# Result objects
# ----------------------------------------------------------------------
@dataclass
class EvidenceRecipe:
    """One recipe that is cited as evidence for a substitute."""

    row_idx: int
    id: str
    title: str
    # "direct" (same dish family) or "indirect" (related)
    tier: str
    # Jaccard overlap with the original recipe's core ingredients
    similarity: float
    n_steps: int
    # this recipe's ingredient line(s) that contain the substitute
    lines: list[str]


@dataclass
class Candidate:
    """One possible substitute with the evidence for it."""

    name: str                       # canonical base name
    source: str                     # "data" | "knowledge" | "both"
    level: str                      # "direct" | "indirect" | "none"
    # related recipes without the original ingredient that use it
    n_support: int
    n_direct: int                   # ...of which same dish family
    rate_without: float | None      # n_support / size of the WITHOUT group
    rate_with: float | None         # share of the WITH group that uses it
    enrichment: float | None        # rate_without - rate_with
    in_vocabulary: bool             # appears as an ingredient in the dataset at all
    # cooking roles shared with the replaced ingredient
    shared_roles: list[str]
    evidence: list[EvidenceRecipe] = field(default_factory=list)


@dataclass
class SubstitutionEvidence:
    status: str                     # "ok" | "insufficient_evidence"
    note: str
    # id, title, source, ingredient_lines, instructions, n_steps
    original: dict[str, Any]
    ingredient: str                 # what the user asked to replace
    target: dict[str, Any]          # base, forms, lines [{position, line}]
    role: dict[str, Any]            # roles, known, removal_effect, source
    constraints: dict[str, Any]
    # sizes of every group, so every number has a denominator
    pools: dict[str, Any]
    candidates: list[Candidate]
    # substitutes dropped for safety, with the reason
    rejected: list[dict[str, Any]]
    # OTHER lines of the original that still break a constraint
    residual_conflicts: list[dict[str, Any]]
    settings: dict[str, Any]
    sql: str = ""
    mask_sql: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# The one query that scores every recipe against the original (see module docstring, step 2).
# r: one row per ingredient row, flagged as target / staple.  g: per recipe counts.
NEIGHBOR_SQL = (
    "WITH r AS ("
    "SELECT row_idx, canonical_base AS base, "
    "(canonical_base = ? OR list_contains(?, canonical)) AS is_target, "
    "(list_contains(?, canonical) OR list_contains(?, canonical_base)) AS is_staple "
    "FROM recipe_ingredient), "
    "g AS (SELECT row_idx, bool_or(is_target) AS has_target, "
    "count(DISTINCT base) FILTER (WHERE NOT is_target AND NOT is_staple) AS n_core, "
    "count(DISTINCT base) FILTER (WHERE NOT is_target AND NOT is_staple AND list_contains(?, base)) AS n_shared "
    "FROM r GROUP BY row_idx) "
    "SELECT g.row_idx, g.has_target, g.n_core, g.n_shared, rs.n_steps "
    "FROM g JOIN recipe_stats rs ON rs.row_idx = g.row_idx "
    "WHERE g.n_shared >= 1 AND g.row_idx <> ?"
)


def _label(name: str) -> str:
    return name.replace("_", " ")


# ----------------------------------------------------------------------
# The miner
# ----------------------------------------------------------------------
class SubstitutionMiner:
    def __init__(
        self,
        con,
        stats: RecipeStats,
        *,
        staples: Iterable[str] = (),
        roles: Roles | None = None,
        allergen_matcher: AllergenMatcher | None = None,
        settings: SubstitutionSettings | None = None,
    ):
        self.con = con
        self.stats = stats
        self.staples = frozenset(s.strip().lower() for s in staples)
        self.roles = roles if roles is not None else load_roles()
        self.allergens = allergen_matcher
        self.settings = settings or SubstitutionSettings()
        self.base_of: dict[str, str] = {
            v: base for base, vs in stats.variants.items() for v in vs}
        self._require_columns()

    def _require_columns(self) -> None:
        rows = self.con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'recipe_ingredient'").fetchall()
        missing = REQUIRED_COLUMNS - {r[0] for r in rows}
        if missing:
            raise RuntimeError(
                f"recipe_ingredient has no column(s) {sorted(missing)}. Rebuild the normalized "
                "tables: python -m recipebot.build_normalized")

    # -- small helpers -------------------------------------------------------
    def _forms(self, base: str) -> list[str]:
        """Base first, then its variants that exist in the dataset."""
        vocab = self.stats.vocab
        return [base] + [v for v in self.stats.variants.get(base, [])
                         if v in vocab and v != base]

    def _roles_for(self, name: str) -> list[str]:
        """Roles of an ingredient: its own entry, else the entry of one of its forms."""
        for candidate in [name, *self.stats.variants.get(name, [])]:
            if candidate in self.roles.roles:
                return self.roles.roles[candidate]
        return []

    def _effect_for(self, name: str) -> str | None:
        for candidate in [name, *self.stats.variants.get(name, [])]:
            if candidate in self.roles.removal_effects:
                return self.roles.removal_effects[candidate]
        return None

    def _banned_bases(self, excluded: Iterable[str]) -> set[str]:
        bases: set[str] = set()
        for term in excluded:
            for name in self.stats.resolve(term).names:
                bases.add(self.base_of.get(name, name))
        return bases

    def _allergen_hit(self, names: Sequence[str], allergens: Sequence[str]) -> str | None:
        """First allergen found in any of the texts, as "dairy ('cream' in 'heavy cream')", else None."""
        if not allergens:
            return None
        if self.allergens is None:
            raise ValueError(
                "An allergen matcher is required when allergens are excluded.")
        for allergen in allergens:
            for text in names:
                terms = self.allergens.matches(text, allergen)
                if terms:
                    return f"{_label(allergen)} ('{terms[0]}' in '{text}')"
        return None

    # -- step 1: the original recipe -----------------------------------------
    def _load_original(self, recipe_id: str) -> dict[str, Any]:
        row = self.con.execute(
            "SELECT r.row_idx, r.id, r.title, r.source, r.ingredients_clean, r.instructions_clean, "
            "rs.n_steps FROM recipes r JOIN recipe_stats rs ON rs.row_idx = r.row_idx "
            "WHERE r.id = ?", [recipe_id]).fetchone()
        if row is None:
            raise SubstitutionError(
                f"I have no recipe with the id '{recipe_id}'.")
        row_idx, rid, title, source, lines, instructions, n_steps = row
        return {"row_idx": row_idx, "id": rid, "title": title, "source": source,
                "ingredient_lines": list(lines or []), "instructions": instructions or "",
                "n_steps": n_steps}

    def _resolve_target(self, ingredient: str) -> tuple[str, list[str]]:
        """'eggs' -> ('egg', ['egg']); 'unsalted butter' -> ('butter', ['butter', 'unsalted butter', ...])."""
        resolved = self.stats.resolve(
            ingredient)       # raises UnknownIngredientError
        base = self.base_of.get(resolved.base, resolved.base)
        forms = list(dict.fromkeys(
            [base, resolved.base, *resolved.names, *self._forms(base)]))
        return base, forms

    def _recipe_rows(self, row_idx: int) -> list[tuple[int, str, str]]:
        """(position, canonical, canonical_base) of the original recipe, in line order."""
        return self.con.execute(
            "SELECT position, canonical, canonical_base FROM recipe_ingredient "
            "WHERE row_idx = ? ORDER BY position, name_index", [row_idx]).fetchall()

    # -- steps 2 to 4: similar recipes ------------------------------------------
    def _similar_recipes(self, original_row: int, base: str, forms: list[str], core: list[str]):
        """Returns arrays (row_idx, has_target, similarity, n_steps) for recipes sharing a core ingredient."""
        staples = sorted(self.staples) or [""]
        rows = self.con.execute(
            NEIGHBOR_SQL, [base, forms, staples, staples, core, original_row]).fetchall()
        if not rows:
            empty = np.zeros(0, dtype=np.int64)
            return empty, empty.astype(bool), np.zeros(0), empty
        data = np.array(rows, dtype=np.int64)
        row_idx, has_target = data[:, 0], data[:, 1].astype(bool)
        n_core, n_shared, steps = data[:, 2], data[:, 3], data[:, 4]
        similarity = n_shared / (len(core) + n_core - n_shared)       # Jaccard
        return row_idx, has_target, similarity, steps

    def _top(self, idx: np.ndarray, row_idx: np.ndarray, similarity: np.ndarray) -> tuple[np.ndarray, bool]:
        """Most similar first (ties by row_idx), cut to pool_size. Returns (indices, was_cut)."""
        order = np.lexsort((row_idx[idx], -np.round(similarity[idx], 9)))
        cut = len(order) > self.settings.pool_size
        return idx[order][: self.settings.pool_size], cut

    def _sets_of(self, row_idxs: list[int]) -> dict[int, set[str]]:
        """row_idx -> distinct canonical_base names, for a list of recipes."""
        if not row_idxs:
            return {}
        sets: dict[int, set[str]] = {r: set() for r in row_idxs}
        for row_idx, base in self.con.execute(
                "SELECT row_idx, canonical_base FROM recipe_ingredient "
                "WHERE row_idx IN (SELECT unnest(?::INTEGER[]))", [row_idxs]).fetchall():
            sets[row_idx].add(base)
        return sets

    def _titles(self, row_idxs: list[int]) -> dict[int, tuple[str, str]]:
        if not row_idxs:
            return {}
        return {r: (rid, title) for r, rid, title in self.con.execute(
            "SELECT row_idx, id, title FROM recipes WHERE row_idx IN (SELECT unnest(?::INTEGER[]))",
            [row_idxs]).fetchall()}

    # -- the public method ---------------------------------------------------------
    def mine(
        self,
        recipe_id: str,
        ingredient: str,
        constraints: Constraints | None = None,
        allowed: np.ndarray | None = None,
        mask_sql: str = "",
    ) -> SubstitutionEvidence:
        """Find evidence for replacing `ingredient` in recipe `recipe_id`.

        `allowed` is the hard-constraint mask (True = a recipe may be cited); None means no constraints.
        Raises SubstitutionError (unknown recipe / ingredient not in the recipe) or
        UnknownIngredientError (the ingredient is not in the dataset vocabulary).
        """
        cfg = self.settings
        constraints = constraints or Constraints()
        original = self._load_original(recipe_id)
        base, forms = self._resolve_target(ingredient)
        forms_set = set(forms)
        rows = self._recipe_rows(original["row_idx"])
        target_positions = sorted({p for p, canonical, b in rows
                                   if b == base or canonical in forms_set})
        if not target_positions:
            names = sorted({b for _, _, b in rows})
            raise SubstitutionError(
                f"'{ingredient}' is not an ingredient of '{original['title']}' [{original['id']}]. "
                f"Its ingredients are: {', '.join(names)}.")
        target_lines = [{"position": p, "line": original["ingredient_lines"][p]}
                        for p in target_positions if p < len(original["ingredient_lines"])]

        recipe_bases = {b for _, _, b in rows}
        core = sorted({b for _, canonical, b in rows
                       if b not in forms_set and b not in self.staples
                       and canonical not in self.staples})
        n_total = len(allowed) if allowed is not None else self.con.execute(
            "SELECT count(*) FROM recipes").fetchone()[0]
        if allowed is None:
            allowed = np.ones(n_total, dtype=bool)

        pools: dict[str, Any] = {"n_recipes_total": n_total, "original_core_ingredients": core,
                                 "n_related_with": 0, "n_related_without": 0,
                                 "n_without_allowed": 0, "n_with_used": 0, "n_without_used": 0,
                                 "n_direct": 0, "n_indirect": 0, "pool_cut": False}
        role_info = self._role_info(base)
        candidates: list[Candidate] = []
        rejected: list[dict[str, Any]] = []

        if core:
            row_idx, has_target, sim, steps = self._similar_recipes(
                original["row_idx"], base, forms, core)
            if len(row_idx) and int(row_idx.max()) >= len(allowed):
                raise ValueError(
                    "The hard-constraint mask is shorter than the recipe table.")
            related = sim >= cfg.related_min_sim
            with_all = np.flatnonzero(has_target & related)
            without_all = np.flatnonzero(~has_target & related)
            without_ok = without_all[allowed[row_idx[without_all]]
                                     & (steps[without_all] >= 1)]
            with_pool, cut_a = self._top(with_all, row_idx, sim)
            without_pool, cut_b = self._top(without_ok, row_idx, sim)
            pools.update(n_related_with=len(with_all), n_related_without=len(without_all),
                         n_without_allowed=len(without_ok), n_with_used=len(with_pool),
                         n_without_used=len(without_pool), pool_cut=bool(cut_a or cut_b))
            candidates, rejected, extra = self._candidates(
                original, base, forms_set, recipe_bases, constraints, role_info,
                row_idx, sim, steps, with_pool, without_pool)
            pools.update(extra)

        candidates.sort(key=lambda c: (LEVEL_RANK[c.level], not c.in_vocabulary, -c.n_direct,
                                       -c.n_support, -(c.enrichment or 0.0), c.name))
        candidates = candidates[: cfg.max_candidates]
        if any(c.level != "none" for c in candidates):
            status, note = "ok", ""
        elif not core:
            status = "insufficient_evidence"
            note = ("The original recipe has no ingredients besides the one to replace and pantry "
                    "staples, so there is no way to find similar recipes.")
        else:
            status = "insufficient_evidence"
            note = (f"Fewer than {cfg.min_support} related recipes without {base} (that obey your "
                    f"constraints) use any single substitute, so the dataset does not support a "
                    f"substitution here.")
        return SubstitutionEvidence(
            status=status, note=note, original=original, ingredient=ingredient,
            target={"base": base, "forms": forms, "lines": target_lines},
            role=role_info, constraints=constraints.describe(), pools=pools,
            candidates=candidates, rejected=rejected,
            residual_conflicts=self._residual_conflicts(
                original, rows, set(target_positions), constraints),
            settings=cfg.describe(), sql=NEIGHBOR_SQL, mask_sql=mask_sql)

    # -- role information ------------------------------------------------------------
    def _role_info(self, base: str) -> dict[str, Any]:
        roles = self._roles_for(base)
        return {"roles": roles, "known": bool(roles), "removal_effect": self._effect_for(base),
                "source": ROLE_SOURCE}

    # -- step 5: choose the candidates -----------------------------------------------
    def _candidates(self, original, base, forms_set, recipe_bases, constraints, role_info,
                    row_idx, sim, steps, with_pool, without_pool):
        cfg = self.settings
        n_with, n_without = len(with_pool), len(without_pool)
        titles = self._titles([int(row_idx[i]) for i in without_pool])
        original_words = {t for t in tokenize(
            original["title"]) if t not in cfg.generic_title_words}
        # row_idx -> "direct" | "indirect"
        tier: dict[int, str] = {}
        for i in without_pool:
            r = int(row_idx[i])
            words = set(tokenize(titles[r][1]))
            same_dish = (sim[i] >= cfg.neighbor_min_sim
                         and len(original_words & words) >= cfg.min_title_overlap)
            tier[r] = "direct" if same_dish else "indirect"

        sets = self._sets_of([int(row_idx[i])
                             for i in [*without_pool, *with_pool]])
        n0: Counter = Counter()        # recipes WITHOUT the ingredient that use each name
        nd: Counter = Counter()        # ...of which same dish family
        n1: Counter = Counter()        # recipes WITH the ingredient that use each name
        for i in without_pool:
            r = int(row_idx[i])
            for b in sets[r]:
                n0[b] += 1
                if tier[r] == "direct":
                    nd[b] += 1
        for i in with_pool:
            for b in sets[int(row_idx[i])]:
                n1[b] += 1

        banned = self._banned_bases(constraints.exclude)
        target_roles = set(role_info["roles"])
        priors = [self._prior(p) for p in self.roles.substitutes.get(base, [])]
        prior_names = {p for p, _ in priors}
        in_vocab = dict(priors)

        n_role_filtered = n_already = n_weak = 0
        chosen: dict[str, Candidate] = {}

        def add(name: str, source: str) -> None:
            support = n0[name]
            rate0 = support / n_without if n_without else None
            rate1 = n1[name] / n_with if n_with else None
            enrichment = (
                rate0 - rate1) if (rate0 is not None and rate1 is not None) else None
            if support >= cfg.min_direct_support and nd[name] >= cfg.min_direct_support:
                level = "direct"
            elif support >= cfg.min_support:
                level = "indirect"
            else:
                level = "none"
            chosen[name] = Candidate(
                name=name, source=source, level=level, n_support=support, n_direct=nd[name],
                rate_without=rate0, rate_with=rate1, enrichment=enrichment,
                in_vocabulary=in_vocab.get(name, name in self.stats.vocab),
                shared_roles=sorted(target_roles & set(self._roles_for(name))))

        # found in the data
        for name in sorted(n0, key=lambda b: (-n0[b], b)):
            if n0[name] < cfg.min_support:
                n_weak += 1
                continue
            if name in forms_set or name == base:
                continue
            if name in recipe_bases:
                n_already += 1
                continue
            rate0 = n0[name] / n_without
            rate1 = n1[name] / n_with if n_with else None
            if rate1 is not None and rate0 - rate1 < cfg.min_enrichment:
                # common everywhere: not a replacement
                continue
            if target_roles and not (target_roles & set(self._roles_for(name))):
                # no shared cooking role (or role unknown)
                n_role_filtered += 1
                continue
            add(name, "both" if name in prior_names else "data")

        for name, _ in priors:                                      # general knowledge
            if name in chosen or name in forms_set or name == base or name in recipe_bases:
                continue
            add(name, "knowledge")

        rejected: list[dict[str, Any]] = []
        # safety filters, never silent
        for name in list(chosen):
            reason = None
            if name in banned:
                reason = "you excluded this ingredient"
            else:
                hit = self._allergen_hit(
                    [name, *self._forms(name)], constraints.exclude_allergens)
                if hit:
                    reason = f"contains {hit}, which you excluded"
            if reason:
                rejected.append({"name": name, "reason": reason, "n_support": chosen[name].n_support,
                                 "source": chosen[name].source})
                del chosen[name]

        self._cite(chosen.values(), without_pool,
                   row_idx, sim, steps, tier, titles, sets)
        extra = {"n_direct": sum(1 for t in tier.values() if t == "direct"),
                 "n_indirect": sum(1 for t in tier.values() if t == "indirect"),
                 "n_filtered_no_shared_role": n_role_filtered,
                 "n_filtered_already_in_recipe": n_already,
                 "n_filtered_too_few_recipes": n_weak,
                 "role_filter_applied": bool(target_roles)}
        return list(chosen.values()), rejected, extra

    def _prior(self, name: str) -> tuple[str, bool]:
        """A knowledge-file substitute -> (base name, exists in the dataset vocabulary)."""
        try:
            resolved = self.stats.resolve(name)
        except UnknownIngredientError:
            return name, False
        return self.base_of.get(resolved.base, resolved.base), True

    # -- step 6: cite the recipes ------------------------------------------------------
    def _cite(self, candidates, without_pool, row_idx, sim, steps, tier, titles, sets) -> None:
        """Fill Candidate.evidence: direct recipes first, then the most similar, then by row."""
        cfg = self.settings
        rows = [(int(row_idx[i]), float(sim[i]), int(steps[i]))
                for i in without_pool]
        picked: dict[str, list[tuple[int, float, int]]] = {}
        for cand in candidates:
            if cand.level == "none":
                continue
            having = [t for t in rows if cand.name in sets[t[0]]]
            having.sort(key=lambda t: (
                tier[t[0]] != "direct", -round(t[1], 9), t[0]))
            picked[cand.name] = having[: cfg.max_cited]
        needed = sorted({r for lst in picked.values() for r, _, _ in lst})
        if not needed:
            return
        lines: dict[int, list[tuple[str, str]]] = {r: [] for r in needed}
        for r, line, base in self.con.execute(
                "SELECT row_idx, raw_line, canonical_base FROM recipe_ingredient "
                "WHERE row_idx IN (SELECT unnest(?::INTEGER[])) ORDER BY row_idx, position, name_index",
                [needed]).fetchall():
            lines[r].append((line, base))
        for cand in candidates:
            for r, s, n_steps in picked.get(cand.name, []):
                shown = list(dict.fromkeys(
                    line for line, b in lines[r] if b == cand.name))
                cand.evidence.append(EvidenceRecipe(
                    row_idx=r, id=titles[r][0], title=titles[r][1], tier=tier[r],
                    similarity=s, n_steps=n_steps, lines=shown))

    # -- what the substitution cannot fix ------------------------------------------------
    def _residual_conflicts(self, original, rows, target_positions, constraints) -> list[dict[str, Any]]:
        """OTHER lines of the original recipe that still break an active constraint."""
        conflicts: list[dict[str, Any]] = []
        lines = original["ingredient_lines"]
        for position, line in enumerate(lines):
            if position in target_positions:
                continue
            hit = self._allergen_hit([line], constraints.exclude_allergens)
            if hit:
                conflicts.append(
                    {"position": position, "line": line, "constraint": hit})
        banned = self._banned_bases(constraints.exclude)
        for position, canonical, base in rows:
            if position not in target_positions and base in banned and position < len(lines):
                conflicts.append({"position": position, "line": lines[position],
                                  "constraint": f"excluded ingredient '{base}'"})
        return conflicts

    # -- independent check ----------------------------------------------------------------
    def verify(self, res: SubstitutionEvidence, constraints: Constraints | None = None) -> list[str]:
        """Re-check every cited recipe from the database, without using the mask. [] = consistent."""
        constraints = constraints or Constraints()
        problems: list[str] = []
        forms = set(res.target["forms"]) | {res.target["base"]}
        banned = self._banned_bases(constraints.exclude)
        for cand in res.candidates:
            tag = f"substitute '{cand.name}'"
            if cand.name in forms:
                problems.append(f"{tag} is the ingredient being replaced")
            if cand.name in banned:
                problems.append(f"{tag} is an excluded ingredient")
            hit = self._allergen_hit(
                [cand.name, *self._forms(cand.name)], constraints.exclude_allergens)
            if hit:
                problems.append(f"{tag} contains {hit}")
            if cand.level == "none" and cand.evidence:
                problems.append(f"{tag} has level 'none' but cites recipes")
            if cand.level != "none" and not cand.evidence:
                problems.append(
                    f"{tag} has level '{cand.level}' but cites no recipe")
            if len(cand.evidence) > cand.n_support:
                problems.append(
                    f"{tag} cites more recipes than its support count")
            for ev in cand.evidence:
                problems += self._verify_recipe(
                    ev, cand.name, forms, banned, constraints, tag)
        return problems

    def _verify_recipe(self, ev: EvidenceRecipe, name: str, forms: set[str], banned: set[str],
                       constraints: Constraints, tag: str) -> list[str]:
        row = self.con.execute(
            "SELECT r.row_idx, r.ingredients_clean, rs.n_steps FROM recipes r "
            "JOIN recipe_stats rs ON rs.row_idx = r.row_idx WHERE r.id = ?", [ev.id]).fetchone()
        if row is None:
            return [f"{tag}: cited recipe {ev.id} does not exist"]
        row_idx, lines, n_steps = row
        found: list[str] = []
        pairs = self.con.execute(
            "SELECT canonical, canonical_base FROM recipe_ingredient WHERE row_idx = ?", [row_idx]).fetchall()
        bases = {b for _, b in pairs}
        if bases & forms or any(c in forms for c, _ in pairs):
            found.append(
                f"{tag}: cited recipe {ev.id} contains the ingredient being replaced")
        if name not in bases:
            found.append(f"{tag}: cited recipe {ev.id} does not contain it")
        if bases & banned:
            found.append(
                f"{tag}: cited recipe {ev.id} contains an excluded ingredient")
        if n_steps < 1:
            found.append(f"{tag}: cited recipe {ev.id} has no instructions")
        if constraints.max_steps is not None and n_steps > constraints.max_steps:
            found.append(
                f"{tag}: cited recipe {ev.id} has {n_steps} steps, over your limit")
        hit = self._allergen_hit(
            list(lines or []), constraints.exclude_allergens)
        if hit:
            found.append(f"{tag}: cited recipe {ev.id} contains {hit}")
        return found


# ----------------------------------------------------------------------
# Taxonomy check and text output (for the command line)
# ----------------------------------------------------------------------
def check_taxonomy(stats: RecipeStats, roles: Roles, matcher: AllergenMatcher | None = None) -> list[str]:
    """Lines describing names in ingredient_roles.yaml that the dataset does not know."""
    lines: list[str] = []
    names = set(roles.roles) | set(
        roles.removal_effects) | set(roles.substitutes)
    names |= {s for subs in roles.substitutes.values() for s in subs}
    for name in sorted(names):
        try:
            resolved = stats.resolve(name)
            if resolved.base != name:
                lines.append(
                    f"  '{name}' is written differently in the dataset: '{resolved.base}'")
        except UnknownIngredientError as exc:
            hint = f" (close: {', '.join(exc.suggestions[:4])})" if exc.suggestions else ""
            lines.append(f"  '{name}' is NOT in the dataset vocabulary{hint}")
    for target, subs in sorted(roles.substitutes.items()):
        for sub in subs:
            for allergen in (matcher.allergens if matcher else []):
                terms = matcher.matches(sub, allergen)
                if terms:
                    lines.append(f"  substitute '{sub}' (for {target}) is flagged as {_label(allergen)} "
                                 f"by '{terms[0]}' (add an exception in allergens.yaml only if that is wrong)")
    return lines or ["  every name is in the vocabulary and no substitute is flagged"]


def format_text(res: SubstitutionEvidence) -> str:
    """Plain-text report for the command line. Step 12 builds the chat answer from the same data."""
    o, p = res.original, res.pools
    out = [f"Original: {o['title']}  [{o['id']}]  ({o['n_steps']} steps)",
           f"Replacing: {res.target['base']}  (forms counted: {', '.join(res.target['forms'])})"]
    out += [f"  line {t['position'] + 1}: {t['line']}" for t in res.target["lines"]]
    role = res.role
    out.append("Role of the ingredient: " + (", ".join(role["roles"]) if role["known"] else "not in the roles file")
               + f"   [{role['source']}]")
    out.append(
        f"Hard constraints: {json.dumps(res.constraints)}   (nothing was relaxed)")
    out.append(f"Related recipes: {p['n_related_with']} with {res.target['base']}, {p['n_related_without']} without; "
               f"{p['n_without_allowed']} of those obey the constraints and have steps "
               f"({p['n_direct']} same dish family, {p['n_indirect']} related only)"
               + ("; pool cut to the most similar" if p["pool_cut"] else "") + ".")
    out.append(f"Status: {res.status}" +
               (f" - {res.note}" if res.note else ""))
    for n, c in enumerate(res.candidates, 1):
        rates = ("" if c.rate_without is None else
                 f", used by {c.rate_without:.0%} of the related recipes without it vs "
                 + ("n/a" if c.rate_with is None else f"{c.rate_with:.0%} with it"))
        vocab = "" if c.in_vocabulary else "  [not an ingredient in the dataset]"
        out.append(f"{n}. {c.name}  evidence: {c.level.upper()}  (source: {c.source}; {c.n_support} recipes, "
                   f"{c.n_direct} same dish{rates}){vocab}")
        for ev in c.evidence:
            out.append(f"     {ev.tier:8} [{ev.id}] {ev.title}  sim {ev.similarity:.2f}, {ev.n_steps} steps: "
                       + "; ".join(ev.lines))
    for r in res.rejected:
        out.append(f"Rejected: {r['name']} - {r['reason']}")
    for c in res.residual_conflicts:
        out.append(
            f"Still conflicts after replacing: line {c['position'] + 1} '{c['line']}' ({c['constraint']})")
    if role["removal_effect"]:
        out.append(
            f"Predicted effect of removing it (general knowledge): {role['removal_effect']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m recipebot.tools.substitution",
        description="Evidence for replacing an ingredient in one recipe (Step 11).")
    parser.add_argument(
        "--recipe-id", help="id of the original recipe, e.g. ar:abc123")
    parser.add_argument(
        "--replace", help="the ingredient to replace, e.g. egg")
    parser.add_argument("--exclude-allergen", nargs="*",
                        default=[], help="e.g. dairy egg")
    parser.add_argument("--exclude", nargs="*", default=[],
                        help="ingredients that must not appear")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--json", action="store_true",
                        help="print the full result as JSON")
    parser.add_argument("--check-taxonomy", action="store_true",
                        help="check ingredient_roles.yaml against the database and allergens.yaml")
    args = parser.parse_args(argv)

    from recipebot.db import connect
    from recipebot.normalization.allergens import load_allergens
    from recipebot.retrieval.common import ids_fingerprint
    from recipebot.retrieval.masks import AllergenFlags, build_sql_mask
    from recipebot.tools.matching import RecipeMatcher

    config.setup_logging(logging.WARNING)
    con = connect(read_only=True)
    try:
        stats = RecipeStats(con)
        taxonomy = load_allergens()
        matcher = AllergenMatcher(taxonomy)
        roles = load_roles()
        if args.check_taxonomy:
            print("Checking ingredient_roles.yaml:")
            print("\n".join(check_taxonomy(stats, roles, matcher)))
            return 0
        if not (args.recipe_id and args.replace):
            parser.error(
                "--recipe-id and --replace are required (or use --check-taxonomy)")

        constraints = Constraints(exclude=tuple(args.exclude), exclude_allergens=tuple(args.exclude_allergen),
                                  max_steps=args.max_steps)
        n = con.execute("SELECT count(*) FROM recipes").fetchone()[0]
        mask, mask_sql, _ = build_sql_mask(stats, n, constraints)
        if constraints.exclude_allergens:
            ids = [r[0] for r in con.execute(
                "SELECT id FROM recipes ORDER BY row_idx").fetchall()]
            flags = AllergenFlags.load_or_build(
                con, taxonomy, ids_fingerprint(ids))
            for allergen in constraints.exclude_allergens:
                mask &= ~flags.contains(allergen)
        miner = SubstitutionMiner(con, stats, staples=RecipeMatcher(con, stats).staples, roles=roles,
                                  allergen_matcher=matcher)
        try:
            res = miner.mine(args.recipe_id, args.replace,
                             constraints, mask, mask_sql)
        except (SubstitutionError, UnknownIngredientError) as exc:
            print(exc)
            return 1
        problems = miner.verify(res, constraints)
        print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False)
              if args.json else format_text(res))
        print("Independent check: " +
              ("passed" if not problems else "FAILED: " + "; ".join(problems)))
        return 0 if not problems else 2
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
