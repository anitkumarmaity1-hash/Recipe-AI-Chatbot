"""The agent loop (Step 9): one user message in, one grounded answer out.

    message -> [keyword refusal] -> understand (LLM) -> merge into SessionState
            -> deterministic tool (search | match | stats | details) -> composer -> guard

The model only produces an Understanding. Every fact, number and recipe id
comes from DuckDB through the tools; the guard re-checks the final text.
Substitution (Task 3, Step 12) mines evidence, builds an adapted copy and validates it.
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import numpy as np

from recipebot import config
from recipebot.agent import composer, match_composer, substitution_composer
from recipebot.agent.guard import check_reply
from recipebot.agent.state import SessionState, label
from recipebot.data_loading import SOURCE_LABELS
from recipebot.normalization.steps import split_steps
from recipebot.retrieval.common import tokenize
from recipebot.retrieval.masks import Constraints
from recipebot.schemas import Intent, StatType, Understanding, UnderstandingError
from recipebot.tools.adaptation import adapt, choose_candidate, validate_adaptation
from recipebot.tools.matching import RecipeMatcher
from recipebot.tools.substitution import SubstitutionError, SubstitutionMiner
from recipebot.tools.stats import (
    CONTAINS_DEFINITION,
    STEP_RULE,
    Filter,
    StatsResult,
    UnknownIngredientError,
    unsupported_attribute,
)
from recipebot.understanding.gemini_backend import ConfigError
from recipebot.understanding.message_hints import merge_hints
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
                 *, default_k: int = config.DEFAULT_RESULT_K, max_k: int = config.MAX_RESULT_K,
                 matcher: RecipeMatcher | None = None, miner: SubstitutionMiner | None = None):
        self.retriever = retriever
        self.con = retriever.con
        self.stats = retriever.stats
        self.understander = understander
        self.mapper = mapper
        self.default_k = default_k
        self.max_k = max_k
        self.state = SessionState()
        self._steps: np.ndarray | None = None
        # built on first use when not given (Step 10)
        self._matcher = matcher
        # built on first use when not given (Step 12)
        self._miner = miner
        self._handlers: dict[Intent, Callable[[Understanding, list[str]], _Draft]] = {
            Intent.SEARCH: self._search,
            Intent.REFINE: self._refine,
            Intent.STATS: self._stats,
            Intent.SHOW_DETAILS: self._details,
            Intent.CLEAR_FILTERS: self._clear,
            Intent.MATCH: self._match,
            Intent.SUBSTITUTE: self._substitute,
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
        if (u.intent is Intent.SUBSTITUTE
                or (u.intent is Intent.REFINE and self.state.mode == "substitute")):
            # Safety net: restrictions in the user's own wording must not depend on Gemini
            # copying them into `exclude`. This also covers follow-ups such as "no dairy either".
            u.exclude = merge_hints(message, u.exclude, self.mapper)

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

    @property
    def matcher(self) -> RecipeMatcher:
        if self._matcher is None:
            self._matcher = RecipeMatcher(self.con, self.stats)
        return self._matcher

    # ------------------------------------------------------------------
    # Search and refine
    # ------------------------------------------------------------------
    def _refine(self, u: Understanding, changes: list[str]) -> _Draft:
        """A refinement re-runs whatever the user was doing: a text search, an ingredient match or a substitution."""
        if self.state.mode == "match" and self.state.available:
            return self._match(u, changes)
        if self.state.mode == "substitute" and self.state.substitution:
            return self._substitute(u, changes)
        return self._search(u, changes)

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
        text = composer.compose_search(res, st.unenforced, info, changes,
                                       self._hit_lines([h.row_idx for h in res.hits]))
        text += self._quality_note("\n")
        return _Draft(text, "search", res.to_dict(), {h.id for h in res.hits},
                      [composer.fmt_int(res.n_allowed), composer.fmt_int(res.n_total)])

    # ------------------------------------------------------------------
    # Ingredient matching (Task 2)
    # ------------------------------------------------------------------
    def _match(self, u: Understanding, changes: list[str]) -> _Draft:
        st = self.state
        if not st.available:
            return _Draft("\n".join([*changes, "Which ingredients do you have? For example: "
                                     "'I have eggs, flour and milk'."]))
        constraints = st.constraints()
        mask, mask_sql = self.retriever.allowed_mask(constraints)
        k = min(u.k or self.default_k, self.max_k)
        res = self.matcher.match(
            st.available, constraints, mask, mask_sql, k=k,
            allergen_matcher=self.retriever.matcher)

        problems = [*self.retriever.verify(res.hits, constraints),   # hard constraints, re-checked
                    # SQL numbers vs listed evidence
                    *self.matcher.verify(res)]
        if problems:
            logger.error("match verification failed: %s", problems)
            return _Draft("Results withheld: an independent check failed, so nothing is shown. "
                          + "; ".join(problems), tool="match", payload=res.to_dict())

        st.set_results(res.hits)
        text = match_composer.compose_match(res, st.unenforced, changes)
        text += self._quality_note("\n")
        shown = {h.id for h in res.hits} | {
            a.id for a in res.alternatives}   # alternatives are cited too
        return _Draft(text, "match", res.to_dict(), shown, match_composer.expected_numbers(res))

    def _quality_note(self, prefix: str = "") -> str:
        """One line saying how many junk-titled recipes are never ranked ('' when none or unknown)."""
        junk = getattr(self.retriever, "junk", None)
        n = int(junk.sum()) if junk is not None else 0
        if not n:
            return ""
        return (f"{prefix}Quality filter: {composer.fmt_int(n)} recipes whose title looks like a test "
                "record are never ranked here (config JUNK_TITLE_*); statistics counts include them.")

    def _hit_info(self, row_idxs: list[int]) -> dict[int, tuple[int, int]]:
        if not row_idxs:
            return {}
        marks = ",".join("?" * len(row_idxs))
        rows = self.con.execute(
            f"SELECT row_idx, n_steps, n_ingredients FROM recipe_stats WHERE row_idx IN ({marks})",
            row_idxs).fetchall()
        return {r: (s, n) for r, s, n in rows}

    def _hit_lines(self, row_idxs: list[int]) -> dict[int, list[str]]:
        """row_idx -> cleaned ingredient lines, shown as evidence under each search result."""
        if not row_idxs:
            return {}
        marks = ",".join("?" * len(row_idxs))
        rows = self.con.execute(
            f"SELECT row_idx, ingredients_clean FROM recipes WHERE row_idx IN ({marks})",
            row_idxs).fetchall()
        return {r: list(lines or []) for r, lines in rows}

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
        if self._quality_note():
            notes.append(self._quality_note())
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
    # Ingredient substitution (Task 3)
    # ------------------------------------------------------------------
    @property
    def miner(self) -> SubstitutionMiner:
        if self._miner is None:
            self._miner = SubstitutionMiner(self.con, self.stats, staples=self.matcher.staples,
                                            allergen_matcher=self.retriever.matcher)
        return self._miner

    def _resolve_recipe(self, u: Understanding, notes: list[str]) -> tuple[str, str] | str:
        """The original recipe as (id, title), or a message string when none can be found.

        Order: an id from the session > the active recipe if it fits the named dish >
        the best search match for the named dish (said in the answer) > the active recipe.
        """
        st = self.state
        active = st.active_recipe
        if u.target_recipe_id:
            row = self.con.execute("SELECT title FROM recipes WHERE id = ?",
                                   [u.target_recipe_id]).fetchone()
            if row is None:
                return f"I have no recipe with the id '{u.target_recipe_id}'."
            return u.target_recipe_id, row[0]
        query = u.target_recipe_title or u.dish_query
        if query:
            words = set(tokenize(query))
            if active and words and words <= set(tokenize(active["title"])):
                return active["id"], active["title"]
            # No restrictions: the original may contain the thing the user wants to remove.
            # It must CONTAIN that ingredient, so only recipes that have it are searched
            # ("replace the cream in a penne recipe" must not return a recipe without cream).
            ingredient = u.ingredient_to_replace
            res = self.retriever.search(
                query, Constraints(include=(ingredient,) if ingredient else ()), k=1)
            if not res.hits:
                what = f" that contains {ingredient}" if ingredient else ""
                return f"I could not find a recipe for '{query}'{what}."
            hit = res.hits[0]
            what = f" that contains {ingredient}" if ingredient else ""
            notes.append(f"No recipe id was given, so I used the best search match for "
                         f"'{query}'{what}: {hit.title} [{hit.id}]. Say so if you meant another one.")
            return hit.id, hit.title
        if active:
            return active["id"], active["title"]
        return "Which recipe? Search first, then say 'replace the butter in the second one'."

    def _implied_allergens(self, ingredient: str) -> list[str]:
        """Allergen groups the ingredient to replace belongs to ("egg" -> ["egg"], "cream" -> ["dairy"])."""
        terms = {ingredient}
        try:
            resolved = self.stats.resolve(ingredient)
            terms.add(resolved.base)
            terms.update(resolved.names)
        except UnknownIngredientError:
            pass                                    # the miner reports an unknown ingredient
        matcher = self.retriever.matcher
        return [a for a in matcher.allergens
                if any(matcher.matches(t, a) for t in terms)]

    def _substitute(self, u: Understanding, changes: list[str]) -> _Draft:
        st = self.state
        notes: list[str] = []
        if u.intent is Intent.REFINE and st.substitution:     # "no nuts either" re-runs it
            recipe_id, ingredient = st.substitution["recipe_id"], st.substitution["ingredient"]
        else:
            found = self._resolve_recipe(u, notes)
            if isinstance(found, str):
                return _Draft("\n".join([*changes, found]))
            recipe_id, title = found
            ingredient = u.ingredient_to_replace
            if not ingredient:
                names = [r[0] for r in self.con.execute(
                    "SELECT DISTINCT canonical_base FROM recipe_ingredient WHERE recipe_id = ? "
                    "ORDER BY 1", [recipe_id]).fetchall()]
                return _Draft("\n".join([*changes, f"Which ingredient should I replace in {title} "
                                         f"[{recipe_id}]? Its ingredients: {', '.join(names)}."]),
                              ids={recipe_id})

        # "must contain" belongs to one search, so it is not applied to substitution evidence.
        # The allergen group of the ingredient being replaced is also closed for substitutes
        # (replacing egg never offers egg yolk; replacing cream never offers parmesan).
        implied = [a for a in self._implied_allergens(ingredient)
                   if a not in st.exclude_allergens]
        if implied:
            notes.append(
                "Substitutes from the same allergen group as the ingredient being replaced are "
                f"not offered: {', '.join(implied)}. Evidence recipes also have to be free of it.")
        constraints = Constraints(exclude=tuple(st.exclude_ingredients),
                                  exclude_allergens=tuple(
                                      [*st.exclude_allergens, *implied]),
                                  max_steps=st.max_steps)
        mask, mask_sql = self.retriever.allowed_mask(constraints)
        try:
            ev = self.miner.mine(recipe_id, ingredient,
                                 constraints, mask, mask_sql)
        except SubstitutionError as exc:
            return _Draft("\n".join([*changes, *notes, str(exc)]), ids={recipe_id})

        chosen = choose_candidate(ev)
        adapted = (adapt(ev, chosen, constraints,
                   self.retriever.matcher) if chosen else None)
        problems = self.miner.verify(ev, constraints)
        if adapted:
            problems += validate_adaptation(adapted,
                                            ev, constraints, self.retriever.matcher)
        if problems:
            logger.error("substitution verification failed: %s", problems)
            # Do not leak a failed adapted object in the tool payload either. A refusal is the
            # correct result when ANY line or step violates a hard restriction.
            payload = {"evidence": ev.to_dict(), "adapted": None,
                       "adaptation_validation": {"passed": False, "problems": problems}}
            return _Draft(
                f"I can't provide an adapted recipe for [{ev.original['id']}] that satisfies "
                "your hard restrictions. The independent final-recipe check found: "
                + "; ".join(problems)
                + ". No adapted recipe is shown, and the original database recipe is unchanged.",
                tool="substitute", payload=payload, ids={ev.original["id"]})

        payload = {"evidence": ev.to_dict(), "adapted": adapted.to_dict()
                   if adapted else None}

        st.active_recipe = {
            "id": ev.original["id"], "title": ev.original["title"]}
        st.mode = "substitute"
        st.substitution = {"recipe_id": recipe_id, "ingredient": ingredient}
        text = substitution_composer.compose_substitution(
            ev, adapted, chosen, st.unenforced, changes, notes)
        ids = substitution_composer.cited_ids(ev)
        return _Draft(text, "substitute", payload, ids, substitution_composer.expected_numbers(ev))

    # ------------------------------------------------------------------
    # Small intents
    # ------------------------------------------------------------------
    def _clear(self, u: Understanding, changes: list[str]) -> _Draft:
        return _Draft("All restrictions cleared. Tell me what you would like to search for.")

    def _unsupported(self, u: Understanding, changes: list[str]) -> _Draft:
        why = f" ({u.reason})" if u.reason else ""
        return _Draft(f"I cannot answer that from the Recipe Box dataset{why}. I can search recipes, "
                      "match them to your ingredients, answer statistics about them, and show a "
                      "recipe's ingredients and steps.")
