"""Allergen detection from a hand-written YAML taxonomy (deterministic, auditable).

Matching runs on the FULL ingredient text (not the canonical name), on whole words or
phrases, with optional plural -s/-es. "Exceptions" are removed first, so
"coconut milk" is not dairy and "peanut butter" is not dairy (but IS peanut).
Limits: hidden ingredients are not detected. This is a recipe-text check, never a
medical safety guarantee.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from recipebot import config


def load_allergens(path: Path | str | None = None) -> dict[str, dict[str, list[str]]]:
    """Load data/taxonomy/allergens.yaml and return the {allergen: rules} mapping."""
    path = Path(path) if path else config.TAXONOMY_DIR / "allergens.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["allergens"]


def _phrase_regex(term: str) -> re.Pattern[str]:
    words = r"\s+".join(re.escape(w) for w in term.lower().split())
    return re.compile(r"(?<!\S)" + words + r"(?:s|es)?(?!\S)")


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z]+", text.lower()))


class AllergenMatcher:
    def __init__(self, taxonomy: dict[str, dict[str, list[str]]] | None = None) -> None:
        taxonomy = taxonomy if taxonomy is not None else load_allergens()
        self._rules = {}
        for name, rules in taxonomy.items():
            include = [(term, _phrase_regex(term))
                       for term in rules.get("include", [])]
            exceptions = [_phrase_regex(term)
                          for term in rules.get("exceptions", [])]
            self._rules[name] = (include, exceptions)

    @property
    def allergens(self) -> list[str]:
        return list(self._rules)

    def matches(self, text: str, allergen: str) -> list[str]:
        """Return the include-terms of `allergen` found in `text` (empty list = none found)."""
        if allergen not in self._rules:
            raise KeyError(
                f"Unknown allergen '{allergen}'. Known: {self.allergens}")
        include, exceptions = self._rules[allergen]
        cleaned = _words(text)
        for pattern in exceptions:
            cleaned = pattern.sub(" ", cleaned)
        return [term for term, pattern in include if pattern.search(cleaned)]

    def detect(self, text: str) -> dict[str, list[str]]:
        """Return {allergen: matched terms} for every allergen found in `text`."""
        found = {name: self.matches(text, name) for name in self._rules}
        return {name: terms for name, terms in found.items() if terms}
