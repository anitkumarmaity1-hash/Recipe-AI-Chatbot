"""Hybrid layer: ingredient-parser-nlp (structure) + our dictionary/regex rules (names).

parse_line   wraps the library and returns a plain ParsedLine (safe: never raises on odd input).
resolve_line combines a ParsedLine with the rule layer into final canonical name(s).

Verified behaviour of ingredient-parser-nlp 2.9.2 (checked on Linux / Python 3.12):
  * parse_ingredient("") and parse_ingredient("   ") raise IndexError -> we catch and flag parse_ok=False
  * parse_multiple_ingredients failed with its default volumetric_units_system -> we do not use it
  * names keep plurals and descriptors ("fresh basil leaves") -> normalize_name() cleans them
  * "butter or margarine" and "salt and pepper" both give two names -> we decide via " or "
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from recipebot.normalization.ingredients import IngredientNormalizer, singularize

logger = logging.getLogger(__name__)


@dataclass
class ParsedLine:
    """Raw parser output for one cleaned ingredient line."""

    line: str
    names: list[str] = field(default_factory=list)
    name_confidence: float | None = None  # lowest confidence among the names
    quantity: float | None = None          # first amount only
    quantity_max: float | None = None
    # as returned by the parser (may be plural)
    unit: str | None = None
    preparation: str | None = None
    comment: str | None = None
    purpose: str | None = None
    parse_ok: bool = True


@dataclass
class ResolvedLine:
    """Final names for one line after combining parser output and our rules."""

    canonicals: list[str]      # one row per canonical in recipe_ingredient
    # "butter or margarine" -> canonicals=["butter"], alternatives=["margarine"]
    alternatives: list[str]
    source: str                # "parser" | "regex_fallback" | "none"
    regex_canonical: str       # what the regex layer alone says (for auditing)


def _import_parser() -> Callable[..., Any]:
    try:
        from ingredient_parser import parse_ingredient
    except ImportError as exc:
        raise ImportError(
            "ingredient-parser-nlp is not installed. Run: pip install ingredient-parser-nlp"
        ) from exc
    return parse_ingredient


def warmup() -> None:
    """Parse one known-good line OUTSIDE any try/except.

    On first use the library downloads a small NLTK tagger (internet needed once). Without this
    check a missing download would make every line look like a 'parse failure'.
    """
    parse = _import_parser()
    try:
        parsed = parse("1 cup milk", string_units=True)
    except Exception as exc:
        raise RuntimeError(
            f"ingredient-parser-nlp could not run ({type(exc).__name__}: {exc}). "
            "It downloads a small NLTK tagger on first use, so it needs internet once."
        ) from exc
    if not parsed.name:
        raise RuntimeError(
            "Parser warm-up returned no ingredient name for '1 cup milk'.")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(item: Any) -> str | None:
    text = getattr(item, "text", None)
    return text if text else None


def parse_line(line: str, parse: Callable[..., Any] | None = None) -> ParsedLine:
    """Parse one line. Any library error becomes parse_ok=False instead of an exception."""
    parse = parse or _import_parser()
    try:
        parsed = parse(line, string_units=True)
    except Exception:  # e.g. IndexError on empty input
        return ParsedLine(line=line, parse_ok=False)

    name_items = [n for n in (parsed.name or []) if _text(n)]
    amount = parsed.amount[0] if parsed.amount else None
    unit = getattr(amount, "unit", None)
    return ParsedLine(
        line=line,
        names=[n.text for n in name_items],
        name_confidence=min((n.confidence for n in name_items), default=None),
        quantity=_to_float(getattr(amount, "quantity", None)),
        quantity_max=_to_float(getattr(amount, "quantity_max", None)),
        unit=str(unit) if unit else None,
        preparation=_text(getattr(parsed, "preparation", None)),
        comment=_text(getattr(parsed, "comment", None)),
        purpose=_text(getattr(parsed, "purpose", None)),
        parse_ok=True,
    )


def normalize_unit(unit: str | None) -> str | None:
    """'cups' -> 'cup', 'Tablespoons' -> 'tablespoon'; empty -> None."""
    if not unit:
        return None
    return singularize(unit.lower())


def resolve_line(line: str, parsed: ParsedLine, normalizer: IngredientNormalizer) -> ResolvedLine:
    """Decide the final canonical name(s) for a line (parser first, regex as fallback)."""
    regex_canonical = normalizer.canonical(line)

    names: list[str] = []
    if parsed.parse_ok:
        for raw in parsed.names:
            name = normalizer.normalize_name(raw)
            if name and name not in names:
                names.append(name)

    if names:
        if len(names) > 1 and " or " in line.lower():
            return ResolvedLine([names[0]], names[1:], "parser", regex_canonical)
        return ResolvedLine(names, [], "parser", regex_canonical)
    if regex_canonical:
        return ResolvedLine([regex_canonical], [], "regex_fallback", regex_canonical)
    return ResolvedLine([], [], "none", regex_canonical)
