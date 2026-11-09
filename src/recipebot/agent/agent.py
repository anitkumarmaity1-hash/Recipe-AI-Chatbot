"""The agent loop (Step 9): one user message in, one grounded answer out.

    message -> [keyword refusal] -> understand (LLM) -> merge into SessionState
            -> deterministic tool (search | stats | details) -> composer -> guard

The model only produces an Understanding. Every fact, number and recipe id
comes from DuckDB through the tools; the guard re-checks the final text.
Intents that are not built yet (match, substitute) say so honestly.
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import numpy as np

from recipebot import config
from recipebot.agent import composer
from recipebot.agent.guard import check_reply
from recipebot.agent.state import SessionState, label
from recipebot.data_loading import SOURCE_LABELS
from recipebot.normalization.steps import split_steps
from recipebot.retrieval.masks import Constraints
from recipebot.schemas import Intent, StatType, Understanding, UnderstandingError
from recipebot.tools.stats import (
    CONTAINS_DEFINITION,
    STEP_RULE,
    Filter,
    StatsResult,
    UnknownIngredientError,
    unsupported_attribute,
)
from recipebot.understanding.gemini_backend import ConfigError
from recipebot.understanding.restrictions import RestrictionMapper

logger = logging.getLogger(__name__)


class Understander(Protocol):
    def understand(self, message: str, state: dict[str, Any] | None = None) -> Understanding:
        ...


@dataclass
class AgentReply:
    text: str
    intent: str = "none"
    understanding: dict[str, Any] | None = None
    tool: str | None = None
    # raw tool output (for logs and evaluation)
    payload: dict[str, Any] | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)
    guard_problems: list[str] = field(default_factory=list)


@dataclass
class _Draft:
    """What a handler returns before the guard has looked at it."""
    text: str
    tool: str | None = None
    payload: dict[str, Any] | None = None
    # recipe ids present in the tool output
    ids: set[str] = field(default_factory=set)
    must_contain: list[str] = field(default_factory=list)


class RecipeAgent:
    def __init__(self, retriever, understander: Understander, mapper: RestrictionMapper,
                 *, default_k: int = config.DEFAULT_RESULT_K, max_k: int = config.MAX_RESULT_K):
        self.retriever = retriever
        self.con = retriever.con
        self.stats = retriever.stats
        self.understander = understander
        self.mapper = mapper
        self.default_k = default_k
        self.max_k = max_k
        self.state = SessionState()
        self._steps: np.ndarray | None = None
        self._handlers: dict[Intent, Callable[[Understanding, list[str]], _Draft]] = {
            Intent.SEARCH: self._search,
            Intent.REFINE: self._search,
            Intent.STATS: self._stats,
            Intent.SHOW_DETAILS: self._details,
            Intent.CLEAR_FILTERS: self._clear,
            Intent.MATCH: lambda u, c: self._not_built("Ingredient matching (Task 2)", 10, c),
            Intent.SUBSTITUTE: lambda u, c: self._not_built("Ingredient substitution (Task 3)", "11 and 12", c),
            Intent.UNSUPPORTED: self._unsupported,
        }

    def reset(self) -> None:
        self.state = SessionState()

    # ------------------------------------------------------------------
    def handle(self, message: str) -> AgentReply:
        message = (message or "").strip()
        if not message:
            return AgentReply("Please type a question about recipes.")

        # 1. Data we do not have: refuse without calling the model at all.
        refusal = unsupported_attribute(message)
        if refusal:
            return AgentReply(refusal, intent=Intent.UNSUPPORTED.value)

        # 2. Understand. If this fails, nothing in the session changes.
        t0 = time.perf_counter()
        try:
            u = self.understander.understand(
                message, self.state.to_prompt_state())
        except (UnderstandingError, ConfigError) as exc:
            return AgentReply(f"I could not understand that message ({exc}). "
                              "Nothing was changed; please rephrase.")
        timings = {"understand": 1000 * (time.perf_counter() - t0)}

        # 3. Update the session; roll back if a restriction names an unknown ingredient.
        snapshot = copy.deepcopy(self.state)
        t0 = time.perf_counter()
        try:
            changes = self.state.apply(u, self.mapper)
            for term in [*self.state.exclude_ingredients, *self.state.include]:
                # raises UnknownIngredientError
                self.stats.resolve(term)
            draft = self._handlers[u.intent](u, changes)
        except UnknownIngredientError as exc:
            self.state = snapshot
            return AgentReply(f"{exc} Nothing was changed.", intent=u.intent.value,
                              understanding=u.to_dict(), timings_ms=timings)
        timings["tool"] = 1000 * (time.perf_counter() - t0)

        # 4. Guard the final text.
        problems = check_reply(draft.text, draft.ids, draft.must_contain)
        text = draft.text
        if problems:
            logger.error("Output guard blocked an answer: %s", problems)
            text = ("The answer was withheld because it failed an internal check: "
                    + "; ".join(problems))
        return AgentReply(text, intent=u.intent.value, understanding=u.to_dict(),
                          tool=draft.tool, payload=draft.payload, timings_ms=timings,
                          guard_problems=problems)

    # ------------------------------------------------------------------
    # Search and refine
    # ------------------------------------------------------------------
    def _search(self, u: Understanding, changes: list[str]) -> _Draft:
        st = self.state
        if not st.last_query:
            return _Draft("\n".join([*changes, "Restrictions saved. What would you like to search "
                                     "for (a dish or an ingredient)?"]))
        constraints = st.constraints()
        k = min(u.k or self.default_k, self.max_k)
        res = self.retriever.search(st.last_query, constraints, k=k)

        problems = self.retriever.verify(
            res.hits, constraints)      # independent re-check
        if problems:
            logger.error("verify() found violations: %s", problems)
            return _Draft("Results withheld: an independent check found a hard-constraint "
                          "violation, so nothing is shown. " +
                          "; ".join(problems),
                          tool="search", payload=res.to_dict())

        st.set_results(res.hits)
        info = self._hit_info([h.row_idx for h in res.hits])
        text = composer.compose_search(res, st.unenforced, info, changes)
        return _Draft(text, "search", res.to_dict(), {h.id for h in res.hits},
                      [composer.fmt_int(res.n_allowed), composer.fmt_int(res.n_total)])

    def _hit_info(self, row_idxs: list[int]) -> dict[int, tuple[int, int]]:
        if not row_idxs:
            return {}
        marks = ",".join("?" * len(row_idxs))
        rows = self.con.execute(
            f"SELECT row_idx, n_steps, n_ingredients FROM recipe_stats WHERE row_idx IN ({marks})",
            row_idxs).fetchall()
        return {r: (s, n) for r, s, n in rows}

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
    def _stats(self, u: Understanding, changes: list[str]) -> _Draft:
        mapped = self.mapper.map(u.exclude)
        include = list(u.include)
        notes: list[str] = []
        if u.dish_query:        # "how many pasta recipes": only ingredient names can be counted
            try:
                self.stats.resolve(u.dish_query)
            except UnknownIngredientError as exc:
                return _Draft(f"Statistics can only filter by ingredient names, and '{u.dish_query}' "
                              f"is not one. {exc}")
            include.append(u.dish_query)
            notes.append(
                f"'{u.dish_query}' was treated as an ingredient name.")
        if mapped.unsupported:
            notes.append(
                f"Not applied (cannot be checked reliably): {', '.join(mapped.unsupported)}.")

        if u.stat_type is StatType.FEWEST_STEPS:
            return self._fewest_steps(u, include, mapped, notes)

        if mapped.allergens:
            notes.append("Allergen categories (" + ", ".join(label(a) for a in mapped.allergens) +
                         ") cannot be applied to statistics; name ingredients instead, "
                         "for example milk, butter, cheese.")
        flt = Filter(all_of=include, any_of=u.include_any,
                     none_of=mapped.ingredients, max_steps=u.max_steps)
        if self.state.has_restrictions() or self.state.unenforced:
            notes.append(
                "Your session restrictions were NOT applied to this dataset-wide number.")

        if u.stat_type is StatType.COUNT:
            res = self.stats.count(flt)
        elif u.stat_type is StatType.PERCENTAGE:
            res = self.stats.percentage(of=flt)
        elif u.stat_type is StatType.INGREDIENT_COUNT_SUMMARY:
            res = self.stats.ingredient_count_stats(flt)
        else:   # TOP_INGREDIENTS
            skip = tuple(n for t in (*include, *u.include_any)
                         for n in self.stats.resolve(t).names)
            if skip:
                notes.append(
                    "The filter ingredient itself is left out of the ranking.")
            res = self.stats.top_common_ingredients(
                flt, k=min(u.k or config.DEFAULT_TOP_K, self.max_k), exclude_names=skip)
        return _Draft(composer.compose_stats(res, notes), "stats", res.to_dict(),
                      must_contain=composer.expected_numbers(res))

    def _steps_array(self) -> np.ndarray:
        if self._steps is None:
            rows = self.con.execute(
                "SELECT n_steps FROM recipe_stats ORDER BY row_idx").fetchall()
            self._steps = np.array([r[0] for r in rows], dtype=np.int64)
        return self._steps

    def _fewest_steps(self, u: Understanding, include: list[str], mapped, notes: list[str]) -> _Draft:
        """k recipes with the fewest steps. Returns recipes, so session restrictions DO apply."""
        if u.include_any:
            return _Draft("Fewest-steps rankings support 'must contain' ingredients but not "
                          "'any of' lists. Please name the ingredients that are required.")
        st = self.state
        allergens = list(dict.fromkeys(
            [*st.exclude_allergens, *mapped.allergens]))
        excluded = list(dict.fromkeys(
            [*st.exclude_ingredients, *mapped.ingredients]))
        constraints = Constraints(include=include, exclude=excluded,
                                  exclude_allergens=allergens, max_steps=u.max_steps)
        for term in [*include, *excluded]:
            self.stats.resolve(term)
        mask, sql = self.retriever.allowed_mask(constraints)
        steps, ids = self._steps_array(), self.retriever.bm25.ids
        # 0-step recipes are not ranked
        eligible = np.flatnonzero(mask & (steps >= 1)).tolist()
        # fewest steps, ties by id
        eligible.sort(key=lambda i: (int(steps[i]), ids[i]))
        top = eligible[: min(u.k or self.default_k, self.max_k)]
        titles = dict(self.con.execute(
            f"SELECT row_idx, title FROM recipes WHERE row_idx IN ({','.join('?' * len(top))})",
            top).fetchall()) if top else {}
        res = StatsResult(
            name="fewest_steps",
            value=[{"id": ids[i], "title": titles[i],
                    "n_steps": int(steps[i])} for i in top],
            n_analyzed=len(eligible),
            filters={"all_of": include, "any_of": [], "none_of": excluded, "exclude_allergens": allergens,
                     "max_steps": u.max_steps, "min_steps": 1},
            definition=CONTAINS_DEFINITION, sql=sql,
            details={"step_rule": STEP_RULE})
        if allergens or excluded:
            notes.append(
                "Your active restrictions were applied because this answer lists recipes.")
        if allergens:
            notes.append(composer.ALLERGEN_DISCLAIMER)
        return _Draft(composer.compose_stats(res, notes), "stats", res.to_dict(),
                      {row["id"] for row in res.value}, composer.expected_numbers(res))

    # ------------------------------------------------------------------
    # Recipe details
    # ------------------------------------------------------------------
    def _details(self, u: Understanding, changes: list[str]) -> _Draft:
        st = self.state
        recipe_id = u.target_recipe_id or (st.active_recipe or {}).get("id")
        if not recipe_id:
            return _Draft("Which recipe? Search first, then say 'the second one' or give a recipe id.")
        row = self.con.execute(
            "SELECT row_idx, title, source, ingredients_clean, instructions_clean "
            "FROM recipes WHERE id = ?", [recipe_id]).fetchone()
        if row is None:
            return _Draft(f"I have no recipe with the id '{recipe_id}'.")
        row_idx, title, source, lines, instructions = row
        lines = list(lines or [])
        st.active_recipe = {"id": recipe_id, "title": title}
        text = composer.compose_details(
            recipe_id, title, SOURCE_LABELS.get(source, source), lines,
            split_steps(instructions), self._restriction_warnings(row_idx, lines))
        return _Draft(text, "details", {"id": recipe_id, "title": title}, {recipe_id})

    def _restriction_warnings(self, row_idx: int, lines: list[str]) -> list[str]:
        """The recipe was asked for explicitly, so show it, but say if it breaks an active restriction."""
        warnings = []
        for allergen in self.state.exclude_allergens:
            for line in lines:
                terms = self.retriever.matcher.matches(line, allergen)
                if terms:
                    warnings.append(f"this recipe mentions {label(allergen)} ('{terms[0]}' in "
                                    f"'{line}'), which you excluded.")
                    break
        if self.state.exclude_ingredients:
            names = {r[0] for r in self.con.execute(
                "SELECT canonical FROM recipe_ingredient WHERE row_idx = ?", [row_idx]).fetchall()}
            for term in self.state.exclude_ingredients:
                hit = names & set(self.stats.resolve(term).names)
                if hit:
                    warnings.append(
                        f"this recipe contains {', '.join(sorted(hit))}, which you excluded.")
        return warnings

    # ------------------------------------------------------------------
    # Small intents
    # ------------------------------------------------------------------
    def _clear(self, u: Understanding, changes: list[str]) -> _Draft:
        return _Draft("All restrictions cleared. Tell me what you would like to search for.")

    def _not_built(self, name: str, step: int | str, changes: list[str]) -> _Draft:
        return _Draft(f"{name} is not built yet (plan Step {step}). Right now I can search recipes, "
                      "answer statistics about the dataset and show a recipe's ingredients and steps.")

    def _unsupported(self, u: Understanding, changes: list[str]) -> _Draft:
        why = f" ({u.reason})" if u.reason else ""
        return _Draft(f"I cannot answer that from the Recipe Box dataset{why}. I can search recipes, "
                      "answer statistics about them, and show a recipe's ingredients and steps.")
