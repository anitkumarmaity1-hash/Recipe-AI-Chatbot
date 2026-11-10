"""Session state (Step 9): what the chatbot remembers between messages.

Pure Python, no database, no model. Rules (also written in docs/DESIGN.md):
  * Allergen and ingredient exclusions PERSIST until the user removes them
    ("dairy is fine now") or clears everything.
  * "must contain" ingredients and the step limit belong to ONE search: a new
    search resets them, a refinement adds to them.
  * Statistics and show_details never change the restrictions: "how many
    recipes have no dairy?" is a one-off question, not a new restriction.
  * Phrases we cannot enforce (for example "vegan") are remembered separately
    and always reported, never silently dropped.
  * Step 10: `available` (the ingredients the user has) and `mode` ("search" or
    "match") are remembered, so "Exclude eggs too" after an ingredient match
    re-runs the MATCH, not a text search. `available` survives clear_filters.
  * Step 12: after a substitution, `mode` is "substitute" and `substitution` remembers
    which recipe and ingredient, so "no nuts either" re-runs the substitution with the
    new restriction. A new search or match changes the mode back.
  * Step 10b: a new ingredient list that still contains every old ingredient ("I also have
    rice") EXTENDS the same match: the step limit and the "must contain" list are kept.
    A list that drops an old ingredient, or the first list after a text search, is a new search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from recipebot.retrieval.masks import Constraints
from recipebot.schemas import Intent, Understanding
from recipebot.understanding.restrictions import RestrictionMapper

# Intents whose "exclude" / "allow" slots change the session restrictions.
RESTRICTION_INTENTS = frozenset(
    {Intent.SEARCH, Intent.REFINE, Intent.MATCH, Intent.SUBSTITUTE})


def _add(items: list[str], value: str) -> bool:
    if value in items:
        return False
    items.append(value)
    return True


def _remove(items: list[str], value: str) -> bool:
    if value not in items:
        return False
    items.remove(value)
    return True


def label(name: str) -> str:
    """'tree_nut' -> 'tree nut' (for messages)."""
    return name.replace("_", " ")


def ingredient_key(raw: str) -> str:
    """Lowercase, one space between words, last word singular: 'Tomatoes ' -> 'tomato'.

    Only used to compare two ingredient lists; nothing is stored under this key.
    """
    words = re.sub(r"\s+", " ", raw.strip().lower()).split(" ")
    word = words[-1]
    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"                      # berries -> berry
    elif len(word) > 4 and word.endswith("oes"):
        word = word[:-2]                            # tomatoes -> tomato
    elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        # eggs -> egg, peas -> pea, glass stays
        word = word[:-1]
    words[-1] = word
    return " ".join(w for w in words if w)


@dataclass
class SessionState:
    exclude_allergens: list[str] = field(default_factory=list)
    exclude_ingredients: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)       # this search only
    max_steps: int | None = None                          # this search only
    unenforced: list[str] = field(default_factory=list)   # e.g. ["vegan"]
    # Step 10: ingredients the user has
    available: list[str] = field(default_factory=list)
    # Step 10: "search" or "match"; Step 12: "substitute"
    mode: str = "search"
    # Step 12: {"recipe_id": ..., "ingredient": ...} of the last substitution
    substitution: dict[str, str] | None = None
    # set by apply(): was the previous mode "match"? (decides extend vs new search)
    mode_was_match: bool = False
    last_query: str | None = None
    last_results: list[dict[str, Any]] = field(default_factory=list)
    active_recipe: dict[str, str] | None = None

    # ------------------------------------------------------------------
    def constraints(self) -> Constraints:
        """The hard constraints for the next search."""
        return Constraints(
            include=tuple(self.include),
            exclude=tuple(self.exclude_ingredients),
            exclude_allergens=tuple(self.exclude_allergens),
            max_steps=self.max_steps,
        )

    def has_restrictions(self) -> bool:
        return bool(self.exclude_allergens or self.exclude_ingredients
                    or self.include or self.max_steps is not None)

    def clear_filters(self) -> None:
        self.exclude_allergens.clear()
        self.exclude_ingredients.clear()
        self.include.clear()
        self.unenforced.clear()
        self.max_steps = None

    def set_results(self, hits) -> None:
        """Remember the numbered results so "the second one" can be resolved."""
        self.last_results = [{"n": n, "id": h.id, "title": h.title}
                             for n, h in enumerate(hits, 1)]

    # ------------------------------------------------------------------
    def apply(self, u: Understanding, mapper: RestrictionMapper) -> list[str]:
        """Merge one Understanding into the state. Returns messages describing what changed."""
        if u.intent is Intent.CLEAR_FILTERS:
            self.clear_filters()
            return ["All restrictions cleared."]
        if u.intent not in RESTRICTION_INTENTS:
            return []

        changes: list[str] = []
        # 1. restrictions the user drops
        removed = mapper.map(u.allow)
        for name in removed.allergens:
            if _remove(self.exclude_allergens, name):
                changes.append(f"Removed restriction: {label(name)}.")
        for name in removed.ingredients:
            if _remove(self.exclude_ingredients, name):
                changes.append(f"Removed restriction: {name}.")
        for name in removed.unsupported:
            _remove(self.unenforced, name)

        # 2. restrictions the user adds
        added = mapper.map(u.exclude)
        for name in added.allergens:
            if _add(self.exclude_allergens, name):
                changes.append(
                    f"Added restriction: no {label(name)} (allergen check on every ingredient line).")
        for name in added.ingredients:
            if _add(self.exclude_ingredients, name):
                changes.append(f"Added restriction: no {name} (ingredient).")
        for name in added.unsupported:
            if _add(self.unenforced, name):
                changes.append(
                    f"Cannot enforce: '{name}' (not something ingredient lists can prove).")

        if u.intent is Intent.SEARCH:                       # 3. one-search settings
            self.mode = "search"
            self._start_new_search(u, changes)
            query = u.dish_query or " ".join(u.include)
            if query:
                self.last_query = query
        elif u.intent is Intent.MATCH:
            self.mode_was_match = self.mode == "match"
            self.mode = "match"
            if u.available:
                extends = (self.mode_was_match and bool(self.available)
                           and {ingredient_key(a) for a in self.available}
                           <= {ingredient_key(a) for a in u.available})
                self.available = list(u.available)
                if extends:                                 # "I also have rice": same search
                    self._merge_one_search_settings(u)
                    changes.append("Ingredient list extended: your 'must contain' list "
                                   "and step limit were kept.")
                else:                                       # a new list starts a new match
                    self._start_new_search(u, changes)
            else:                                           # "what can I cook?" keeps the list
                self._merge_one_search_settings(u)
        else:
            self._merge_one_search_settings(u)
            if u.dish_query:
                self.last_query = u.dish_query
        return changes

    def _start_new_search(self, u: Understanding, changes: list[str]) -> None:
        if self.include or self.max_steps is not None:
            changes.append("New search: the previous 'must contain' list and step limit were reset; "
                           "allergen and ingredient exclusions stay.")
        self.include = list(u.include)
        self.max_steps = u.max_steps

    def _merge_one_search_settings(self, u: Understanding) -> None:
        for term in u.include:
            _add(self.include, term)
        if u.max_steps is not None:
            self.max_steps = u.max_steps

    # ------------------------------------------------------------------
    def to_prompt_state(self) -> dict[str, Any]:
        """The compact state sent to the understanding model (shape documented in prompt.py)."""
        state = {
            "active_filters": {
                "include": list(self.include),
                "exclude": [label(a) for a in self.exclude_allergens] + list(self.exclude_ingredients),
                "max_steps": self.max_steps,
            },
            "last_results": list(self.last_results),
            "active_recipe": dict(self.active_recipe) if self.active_recipe else None,
        }
        if self.available:          # Step 10: lets the model keep and extend the list
            state["available"] = list(self.available)
        return state
