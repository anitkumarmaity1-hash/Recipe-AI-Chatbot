"""Detect ingredient-list lines that are notes, not ingredients (Step 4b).

Two kinds of prefix (see data/taxonomy/non_ingredient_prefixes.yaml):
  drop  -> the whole line is ignored ("Special equipment: 9-inch pan")
  strip -> the prefix is removed, the rest is a normal ingredient line
           ("Garnish: 1 lemon twist" -> "1 lemon twist")
A prefix only counts at the START of the line and must be followed by ":".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from recipebot import config

KEEP = "keep"
DROP = "drop"
STRIP = "strip"


@dataclass(frozen=True)
class LineDecision:
    action: str            # keep | drop | strip
    prefix: str | None = None
    text: str = ""         # for strip: the remainder after the prefix


def _prefix_pattern(prefixes) -> str:
    """Regex alternation, longest prefix first, spaces matched flexibly."""
    cleaned = sorted(
        {" ".join(str(p).lower().split()) for p in prefixes if str(p).strip()},
        key=len,
        reverse=True,
    )
    return "|".join(r"\s+".join(re.escape(word) for word in p.split()) for p in cleaned)


class LineFilter:
    """Classify a cleaned ingredient line as keep / drop / strip."""

    def __init__(self, drop=(), strip=()) -> None:
        self._drop = self._compile(drop)
        self._strip = self._compile(strip)

    @staticmethod
    def _compile(prefixes):
        pattern = _prefix_pattern(prefixes)
        if not pattern:
            return None
        return re.compile(
            rf"^[\s*_#>\-]*(?P<prefix>{pattern})\s*:\s*[*_]*\s*(?P<rest>.*)$",
            re.IGNORECASE | re.DOTALL,
        )

    def classify(self, line: str) -> LineDecision:
        for action, regex in ((DROP, self._drop), (STRIP, self._strip)):
            if regex is None:
                continue
            match = regex.match(line)
            if not match:
                continue
            prefix = " ".join(match.group("prefix").lower().split())
            if action == DROP:
                return LineDecision(DROP, prefix)
            rest = match.group("rest").strip()
            if not rest:  # nothing left after the prefix
                return LineDecision(DROP, prefix)
            return LineDecision(STRIP, prefix, rest)
        return LineDecision(KEEP)


def load_line_filter(path: Path | str | None = None) -> LineFilter:
    """Load data/taxonomy/non_ingredient_prefixes.yaml (no filtering if missing)."""
    path = Path(path) if path else config.TAXONOMY_DIR / "non_ingredient_prefixes.yaml"
    if not path.exists():
        return LineFilter()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return LineFilter(drop=data.get("drop") or [], strip=data.get("strip") or [])