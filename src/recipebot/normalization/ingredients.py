"""Dictionary + regex ingredient normalization (the rule layer of the hybrid approach).

Two entry points:
  canonical(line)      full regex pipeline on a raw line. It is the FALLBACK when the parser
                       fails, and is stored as `regex_canonical` for auditing.
                       "1/2 medium onion, diced" -> "onion"
  normalize_name(text) cleanup of a NAME already extracted by ingredient-parser-nlp.
                       "fresh basil leaves" -> "basil leaf"

Regex pipeline: lowercase, drop unicode fractions and (notes), keep text before the first comma,
strip the leading quantity, cut at the first "or", drop descriptor words and leading units,
singularize the LAST word, then apply the synonym map.
Different forms stay different: "garlic powder" != "garlic", "coconut milk" != "milk".
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from recipebot import config

_FRACTION_CHARS = "¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"
_PAREN = re.compile(r"\([^)]*\)")
_QTY = re.compile(r"^\s*\d[\d\s/.\-–]*(?:(?:to|or)\s+\d[\d\s/.\-–]*)*")
_WORD = re.compile(r"[a-z]+(?:['\-][a-z]+)*")

UNITS = {
    "cup", "cups", "c", "tablespoon", "tablespoons", "tbsp", "tbsps", "tbs", "tbl",
    "teaspoon", "teaspoons", "tsp", "tsps", "ounce", "ounces", "oz", "pound", "pounds",
    "lb", "lbs", "gram", "grams", "g", "kg", "kilogram", "kilograms", "ml", "milliliter",
    "milliliters", "l", "liter", "liters", "litre", "litres", "quart", "quarts", "qt",
    "pint", "pints", "pt", "gallon", "gallons", "pinch", "pinches", "dash", "dashes",
    "can", "cans", "package", "packages", "pkg", "packet", "packets", "jar", "jars",
    "bottle", "bottles", "stick", "sticks", "clove", "cloves", "slice", "slices",
    "piece", "pieces", "bunch", "bunches", "sprig", "sprigs", "head", "heads",
    "stalk", "stalks", "handful", "handfuls", "container", "containers", "box", "boxes",
    "bag", "bags", "envelope", "envelopes", "inch", "inches", "fluid", "fl",
}

DESCRIPTORS = {
    "a", "an", "one", "two", "three", "four", "five", "six",
    "fresh", "freshly", "large", "medium", "small", "ripe", "chopped", "diced", "minced",
    "sliced", "grated", "shredded", "peeled", "seeded", "cored", "trimmed", "finely",
    "coarsely", "roughly", "thinly", "thickly", "cubed", "halved", "quartered", "divided",
    "optional", "softened", "melted", "packed", "heaping", "level", "rounded", "boneless",
    "skinless", "beaten", "lightly", "drained", "rinsed", "washed", "uncooked", "frozen",
    "thawed", "plus", "more", "for", "garnish", "serving", "taste", "needed", "to",
    "about", "approximately", "additional",
}

IRREGULAR = {
    "leaves": "leaf", "loaves": "loaf", "halves": "half", "cookies": "cookie",
    "brownies": "brownie", "chilies": "chili",
}
UNCHANGED = {"molasses", "brussels", "greens",
             "grits", "asparagus", "hummus", "couscous"}


def singularize(word: str) -> str:
    """Very small English singularizer, good enough for ingredient nouns and units."""
    if word in IRREGULAR:
        return IRREGULAR[word]
    if word in UNCHANGED or len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes"):
        return word[:-2]
    if word.endswith(("ches", "shes", "xes", "zes", "sses")):
        return word[:-2]
    if word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def load_synonyms(path: Path | str | None = None) -> dict[str, str]:
    """Load data/taxonomy/synonyms.yaml (empty dict if the file is missing)."""
    path = Path(path) if path else config.TAXONOMY_DIR / "synonyms.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k).lower(): str(v).lower() for k, v in (data.get("synonyms") or {}).items()}


class IngredientNormalizer:
    """Rule-based normalizer. Results are cached because lines repeat a lot."""

    def __init__(self, synonyms: dict[str, str] | None = None) -> None:
        self.synonyms = dict(synonyms or {})
        self._cache: dict[str, str] = {}

    def canonical(self, line: str) -> str:
        """Regex pipeline on a raw line. Returns "" if nothing usable is left."""
        if line not in self._cache:
            self._cache[line] = self._compute(line)
        return self._cache[line]

    def normalize_name(self, name: str) -> str:
        """Clean a name extracted by the parser: drop descriptors, singularize, apply synonyms."""
        tokens = [t for t in _WORD.findall(
            name.lower()) if t not in DESCRIPTORS]
        return self._finish(tokens)

    def _finish(self, tokens: list[str]) -> str:
        if not tokens:
            return ""
        tokens = list(tokens)
        tokens[-1] = singularize(tokens[-1])
        phrase = " ".join(tokens)
        return self.synonyms.get(phrase, phrase)

    def _compute(self, line: str) -> str:
        text = line.lower()
        for ch in _FRACTION_CHARS:
            text = text.replace(ch, " ")
        text = _PAREN.sub(" ", text)
        text = text.split(",")[0]
        text = _QTY.sub(" ", text, count=1)
        tokens = _WORD.findall(text)

        if "or" in tokens[1:]:  # "butter or margarine" -> keep the first alternative
            tokens = tokens[: tokens.index("or", 1)]

        tokens = [t for t in tokens if t not in DESCRIPTORS]
        while tokens and (tokens[0] in UNITS or tokens[0] == "of"):
            tokens.pop(0)
        return self._finish(tokens)
