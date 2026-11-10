"""Calls from the UI into the backend. Every function here goes through `RecipeAgent`, so the
hard-constraint mask, the independent verification and the output guard always run.

The form pages (ingredient finder, substitution, analytics, recipe details) need no language
model: they build an `Understanding` from the form fields (validated by the backend's own
`Understanding.from_dict`) and feed it to a fresh agent with `FixedUnderstander`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from recipebot.agent.agent import AgentReply, RecipeAgent
from recipebot.schemas import Understanding, UnderstandingError
from ui import queries
from ui.engine import Engine, FixedUnderstander

WITHHELD_PREFIXES = ("Results withheld", "The answer was withheld")


class RequestError(ValueError):
    """The form values cannot be turned into a valid request (shown to the user as is)."""


@dataclass(frozen=True)
class Restrictions:
    # allergen categories, e.g. ("dairy", "egg")
    allergens: tuple[str, ...] = ()
    # phrases ("butter", "mushrooms"); the backend decides what they mean
    exclude: tuple[str, ...] = ()
    max_steps: int | None = None


@dataclass
class ToolRun:
    reply: AgentReply
    agent: RecipeAgent

    @property
    def withheld(self) -> bool:
        return is_withheld(self.reply)

    @property
    def payload(self) -> dict[str, Any] | None:
        return None if self.withheld else self.reply.payload

    @property
    def unenforced(self) -> list[str]:
        return list(self.agent.state.unenforced)


@dataclass
class RecipeDetail:
    id: str
    title: str
    source_label: str
    lines: list[str]
    steps: list[str]
    warnings: list[str]
    n_steps: int
    text: str = ""


def is_withheld(reply: AgentReply) -> bool:
    """True when the backend refused to show results (guard or independent check failed)."""
    return bool(reply.guard_problems) or reply.text.startswith(WITHHELD_PREFIXES)


def split_terms(text: str) -> list[str]:
    """'Eggs, Milk;  butter' -> ['eggs', 'milk', 'butter'] (lowercase, no duplicates)."""
    out: list[str] = []
    for part in re.split(r"[,;\n]", text or ""):
        part = " ".join(part.lower().split())
        if part and part not in out:
            out.append(part)
    return out


def _understanding(**slots: Any) -> Understanding:
    try:
        return Understanding.from_dict(slots)
    except UnderstandingError as exc:
        raise RequestError(str(exc)) from None


def _run(engine: Engine, understanding: Understanding, *, allergens: Sequence[str] = (),
         message: str = "request from the NOSH form") -> ToolRun:
    agent = engine.new_agent(FixedUnderstander(understanding))
    unknown = [a for a in allergens if a not in engine.allergens]
    if unknown:
        raise RequestError(f"Unknown allergen category: {', '.join(unknown)}.")
    agent.state.exclude_allergens = list(dict.fromkeys(allergens))
    reply = engine.handle(agent, message)
    return ToolRun(reply, agent)


# ----------------------------------------------------------------------
def search_recipes(engine: Engine, query: str, k: int = 8) -> ToolRun:
    """Plain recipe lookup (used by the pickers). No restrictions."""
    if not query.strip():
        raise RequestError("Type a dish or an ingredient to search for.")
    return _run(engine, _understanding(intent="search", dish_query=query.strip(), k=k))


def find_by_ingredients(engine: Engine, available: Sequence[str], restrictions: Restrictions,
                        k: int) -> ToolRun:
    if not available:
        raise RequestError("Add at least one ingredient first.")
    u = _understanding(intent="match", available=list(available), exclude=list(restrictions.exclude),
                       max_steps=restrictions.max_steps or 0, k=k)
    return _run(engine, u, allergens=restrictions.allergens)


def substitute(engine: Engine, recipe_id: str, ingredient: str, restrictions: Restrictions) -> ToolRun:
    if not recipe_id.strip():
        raise RequestError("Choose a recipe first.")
    if not ingredient.strip():
        raise RequestError("Choose the ingredient to replace.")
    u = _understanding(intent="substitute", target_recipe_id=recipe_id.strip(),
                       ingredient_to_replace=ingredient.strip(), exclude=list(restrictions.exclude),
                       max_steps=restrictions.max_steps or 0)
    return _run(engine, u, allergens=restrictions.allergens)


def statistics(engine: Engine, stat_type: str, *, include: Sequence[str] = (), k: int | None = None,
               max_steps: int | None = None, allergens: Sequence[str] = ()) -> ToolRun:
    u = _understanding(intent="stats", stat_type=stat_type, include=list(include), k=k or 0,
                       max_steps=max_steps or 0)
    return _run(engine, u, allergens=allergens)


def recipe_detail(engine: Engine, recipe_id: str, allergens: Sequence[str] = (),
                  exclude_ingredients: Sequence[str] = ()) -> RecipeDetail | str:
    """Cleaned recipe plus warnings for the given restrictions, or a message when it cannot be shown.

    The backend's `show_details` handler decides the warnings (they come back as WARNING: lines);
    the page then reads the recipe text itself so that it can be laid out as lists.
    """
    recipe_id = (recipe_id or "").strip()
    if not recipe_id:
        return "Enter a recipe id (for example the one shown on a recipe card)."
    u = _understanding(intent="show_details", target_recipe_id=recipe_id)
    agent = engine.new_agent(FixedUnderstander(u))
    agent.state.exclude_allergens = list(allergens)
    agent.state.exclude_ingredients = list(exclude_ingredients)
    reply = engine.handle(agent, "show recipe from the NOSH form")
    if reply.tool != "details" or is_withheld(reply):
        return reply.text
    record = queries.recipe_record(engine, recipe_id)
    if record is None:                                  # cannot happen after a successful details call
        return f"I have no recipe with the id '{recipe_id}'."
    from recipebot.normalization.steps import split_steps
    warnings = [line[len("WARNING: "):] for line in reply.text.splitlines(
    ) if line.startswith("WARNING: ")]
    return RecipeDetail(id=record["id"], title=record["title"], source_label=record["source_label"],
                        lines=record["lines"], steps=split_steps(
                            record["instructions"]),
                        warnings=warnings, n_steps=record["n_steps"], text=reply.text)
