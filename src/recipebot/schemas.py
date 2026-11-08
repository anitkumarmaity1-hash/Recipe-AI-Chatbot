"""What the language model must return for every user message (Step 8).

`Understanding` is the only thing the LLM produces: an intent plus slots.
It never contains recipe facts. `Understanding.from_dict` validates and cleans
the model's JSON; anything invalid raises UnderstandingError instead of being
guessed. The JSON schema sent to Gemini is generated from the same field list,
so schema and code cannot drift apart (a test checks this).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any

MAX_TEXT_CHARS = 200     # longest string we accept in any slot
MAX_LIST_ITEMS = 20      # longest list we accept in any slot
MAX_STEPS_LIMIT = 500
MAX_K_LIMIT = 50


class UnderstandingError(ValueError):
    """The model output (or the backend call) could not be turned into an Understanding."""


class Intent(str, Enum):
    SEARCH = "search"                # find recipes for a dish / need
    REFINE = "refine"                # change filters of the current search
    STATS = "stats"                  # count / percentage / average / median / ranking
    MATCH = "match"                  # recipes I can cook from my ingredients
    SUBSTITUTE = "substitute"        # replace an ingredient in a recipe
    SHOW_DETAILS = "show_details"    # ingredients / steps of one recipe
    CLEAR_FILTERS = "clear_filters"  # forget all restrictions
    UNSUPPORTED = "unsupported"      # cooking time, nutrition, or not about recipes


class StatType(str, Enum):
    COUNT = "count"
    PERCENTAGE = "percentage"
    # average / median ingredients
    INGREDIENT_COUNT_SUMMARY = "ingredient_count_summary"
    TOP_INGREDIENTS = "top_ingredients"
    FEWEST_STEPS = "fewest_steps"


class RestrictionType(str, Enum):
    ALLERGY = "allergy"
    DIET = "diet"
    PREFERENCE = "preference"


# the schema uses "none" / "" / 0 instead of null (simpler for the API)
NONE_WORD = "none"


@dataclass
class Understanding:
    intent: Intent
    dish_query: str | None = None             # dish words only, never negations
    # recipe must contain ALL
    include: list[str] = field(default_factory=list)
    # recipe must contain AT LEAST ONE
    include_any: list[str] = field(default_factory=list)
    # recipe must contain NONE
    exclude: list[str] = field(default_factory=list)
    # restrictions the user now removes
    allow: list[str] = field(default_factory=list)
    max_steps: int | None = None
    # ingredients the user has
    available: list[str] = field(default_factory=list)
    stat_type: StatType | None = None
    k: int | None = None                      # "top 5", "five recipes"
    # must be an id from the session state
    target_recipe_id: str | None = None
    target_recipe_title: str | None = None
    ingredient_to_replace: str | None = None
    restriction_type: RestrictionType | None = None
    # short text for unsupported / unclear requests
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            out[f.name] = value.value if isinstance(value, Enum) else value
        return out

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: Any) -> "Understanding":
        """Validate and clean the model's JSON. Raises UnderstandingError."""
        if not isinstance(data, dict):
            raise UnderstandingError(
                f"expected a JSON object, got {type(data).__name__}")

        intent = _enum(Intent, data.get("intent"), "intent", required=True)
        stat_type = _enum(StatType, data.get("stat_type"), "stat_type")
        restriction = _enum(RestrictionType, data.get(
            "restriction_type"), "restriction_type")
        if intent is Intent.STATS and stat_type is None:
            raise UnderstandingError("intent 'stats' needs a stat_type")

        return cls(
            intent=intent,
            dish_query=_text(data.get("dish_query"), "dish_query"),
            include=_text_list(data.get("include"), "include"),
            include_any=_text_list(data.get("include_any"), "include_any"),
            exclude=_text_list(data.get("exclude"), "exclude"),
            allow=_text_list(data.get("allow"), "allow"),
            max_steps=_int(data.get("max_steps"),
                           "max_steps", MAX_STEPS_LIMIT),
            available=_text_list(data.get("available"), "available"),
            stat_type=stat_type,
            k=_int(data.get("k"), "k", MAX_K_LIMIT),
            target_recipe_id=_text(
                data.get("target_recipe_id"), "target_recipe_id"),
            target_recipe_title=_text(
                data.get("target_recipe_title"), "target_recipe_title"),
            ingredient_to_replace=_text(
                data.get("ingredient_to_replace"), "ingredient_to_replace"),
            restriction_type=restriction,
            reason=_text(data.get("reason"), "reason"),
        )


# ----------------------------------------------------------------------
# Small validators (each raises UnderstandingError with the field name)
# ----------------------------------------------------------------------
def _is_none(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in ("", NONE_WORD))


def _enum(enum_cls, value: Any, name: str, required: bool = False):
    if _is_none(value):
        if required:
            raise UnderstandingError(f"'{name}' is required")
        return None
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        allowed = [m.value for m in enum_cls]
        raise UnderstandingError(
            f"'{name}' must be one of {allowed}, got {value!r}") from None


def _text(value: Any, name: str) -> str | None:
    if _is_none(value):
        return None
    if not isinstance(value, str):
        raise UnderstandingError(
            f"'{name}' must be a string, got {type(value).__name__}")
    return value.strip()[:MAX_TEXT_CHARS] or None


def _text_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise UnderstandingError(f"'{name}' must be a list of strings")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise UnderstandingError(f"'{name}' must contain only strings")
        item = item.strip().lower()[:MAX_TEXT_CHARS]
        if item and item not in cleaned:
            cleaned.append(item)
    if len(cleaned) > MAX_LIST_ITEMS:
        raise UnderstandingError(
            f"'{name}' has more than {MAX_LIST_ITEMS} items")
    return cleaned


def _int(value: Any, name: str, upper: int) -> int | None:
    if value is None or value == 0 or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise UnderstandingError(
            f"'{name}' must be a whole number, got {value!r}")
    number = int(value)
    if number < 0:
        raise UnderstandingError(f"'{name}' must not be negative")
    return min(number, upper)


# ----------------------------------------------------------------------
# JSON schema sent to the model (generated from the dataclass)
# ----------------------------------------------------------------------
def understanding_json_schema() -> dict[str, Any]:
    """JSON Schema for structured output. 'none', '' and 0 mean 'not given'."""
    string = {"type": "string"}
    string_list = {"type": "array", "items": {"type": "string"}}
    integer = {"type": "integer"}

    def choice(enum_cls, with_none: bool) -> dict[str, Any]:
        values = [m.value for m in enum_cls] + \
            ([NONE_WORD] if with_none else [])
        return {"type": "string", "enum": values}

    kinds: dict[str, dict[str, Any]] = {
        "intent": choice(Intent, with_none=False),
        "stat_type": choice(StatType, with_none=True),
        "restriction_type": choice(RestrictionType, with_none=True),
        "max_steps": integer,
        "k": integer,
    }
    properties: dict[str, dict[str, Any]] = {}
    for f in fields(Understanding):
        if f.name in kinds:
            properties[f.name] = kinds[f.name]
        elif f.default_factory is list:
            properties[f.name] = string_list
        else:
            properties[f.name] = string
    return {"type": "object", "properties": properties, "required": list(properties)}
