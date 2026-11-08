"""Turn the words the LLM extracted into Step 7 hard constraints (Step 8).

The LLM only copies phrases such as "dairy", "eggs" or "butter" into
`exclude`. This module (plain Python + a YAML file) decides what they mean:
an allergen category, an ingredient name, or something we cannot enforce.
That keeps the safety decision out of the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from recipebot import config
from recipebot.retrieval.masks import Constraints
from recipebot.schemas import Understanding

DEFAULT_TERMS_PATH: Path = config.TAXONOMY_DIR / "restriction_terms.yaml"

_LEADING = re.compile(r"^(no|without|avoid|not)\s+")
_FREE_SUFFIX = re.compile(r"\s+free$")


@dataclass
class MappedRestrictions:
    allergens: list[str] = field(default_factory=list)       # e.g. ["dairy"]
    ingredients: list[str] = field(default_factory=list)     # e.g. ["butter"]
    unsupported: list[str] = field(default_factory=list)     # e.g. ["vegan"]


def normalize_phrase(phrase: str) -> str:
    """Lowercase, hyphens to spaces, single spaces ('Dairy-Free ' -> 'dairy free')."""
    return re.sub(r"\s+", " ", phrase.lower().replace("-", " ")).strip()


class RestrictionMapper:
    def __init__(self, terms: dict, known_allergens: Iterable[str] | None = None):
        self.allergen_phrases: dict[str, list[str]] = {
            normalize_phrase(k): list(v) for k, v in (terms.get("allergen_phrases") or {}).items()
        }
        self.unsupported: set[str] = {
            normalize_phrase(x) for x in (terms.get("unsupported_phrases") or [])
        }
        if known_allergens is not None:
            known = set(known_allergens)
            for phrase, categories in self.allergen_phrases.items():
                unknown = [c for c in categories if c not in known]
                if unknown:
                    raise ValueError(
                        f"restriction_terms.yaml: '{phrase}' uses unknown allergen "
                        f"{unknown}; allergens.yaml defines {sorted(known)}")

    @classmethod
    def from_files(cls, path: Path | str | None = None,
                   known_allergens: Iterable[str] | None = None) -> "RestrictionMapper":
        path = Path(path) if path else DEFAULT_TERMS_PATH
        with open(path, encoding="utf-8") as handle:
            return cls(yaml.safe_load(handle) or {}, known_allergens)

    def _lookup(self, phrase: str) -> tuple[str, list[str] | None]:
        """Return ('allergen', categories), ('unsupported', None) or ('ingredient', None)."""
        if phrase in self.unsupported:
            return "unsupported", None
        if phrase in self.allergen_phrases:
            return "allergen", self.allergen_phrases[phrase]
        return "ingredient", None

    def map(self, phrases: Iterable[str]) -> MappedRestrictions:
        """Classify each phrase. Order is kept, duplicates removed."""
        out = MappedRestrictions()
        for raw in phrases:
            phrase = normalize_phrase(raw)
            if not phrase:
                continue
            kind, categories = self._lookup(phrase)
            if kind == "ingredient":
                # try again without "no ..." / "... free" ("dairy free" -> "dairy")
                stripped = _FREE_SUFFIX.sub("", _LEADING.sub("", phrase))
                if stripped != phrase and stripped:
                    phrase = stripped
                    kind, categories = self._lookup(phrase)
            if kind == "unsupported":
                _add(out.unsupported, phrase)
            elif kind == "allergen":
                for category in categories or []:
                    _add(out.allergens, category)
            else:
                _add(out.ingredients, phrase)
        return out


def _add(target: list[str], value: str) -> None:
    if value not in target:
        target.append(value)


def to_constraints(
    understanding: Understanding, mapper: RestrictionMapper
) -> tuple[Constraints, list[str]]:
    """Understanding -> (Step 7 Constraints, unsupported phrases to tell the user about).

    include_any is not part of Constraints (it is used by statistics only).
    """
    mapped = mapper.map(understanding.exclude)
    constraints = Constraints(
        include=tuple(understanding.include),
        exclude=tuple(mapped.ingredients),
        exclude_allergens=tuple(mapped.allergens),
        max_steps=understanding.max_steps,
    )
    return constraints, mapped.unsupported
