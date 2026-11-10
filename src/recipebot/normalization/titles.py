"""Junk-title detection (P2): titles that look like test records, e.g. "Tst" or "Tstcgdgdgdgdgdgdgd".

Three plain rules, all thresholds in config.py (JUNK_TITLE_*):
  1. fewer than JUNK_TITLE_MIN_LETTERS letters or digits in total (ASCII titles only)
  2. three or more ASCII letters but not a single vowel (a, e, i, o, u, y), unless the letters are
     in JUNK_TITLE_ALLOW ("BLT", "BBQ")
  3. a word (split on every non-letter) with JUNK_TITLE_MAX_CONSONANT_RUN or more consonants in a row
Titles in other scripts have no ASCII letters and are never flagged by rules 2 and 3.
The rules are deliberately conservative: a few junk titles may stay, a real title is hardly ever hidden.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

import numpy as np

from recipebot import config

_VOWELS = "aeiouy"


def _ascii_letters(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode(
        "ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", folded.lower())


def is_junk_title(title: str | None, *, min_letters: int | None = None,
                  max_run: int | None = None, allow: Iterable[str] | None = None) -> bool:
    title = (title or "").strip()
    min_letters = config.JUNK_TITLE_MIN_LETTERS if min_letters is None else min_letters
    max_run = config.JUNK_TITLE_MAX_CONSONANT_RUN if max_run is None else max_run
    allowed = {a.lower()
               for a in (config.JUNK_TITLE_ALLOW if allow is None else allow)}

    compact = re.sub(r"\W", "", title)
    if len(compact) < min_letters and compact.isascii():    # short titles in other scripts are real
        return True
    letters = _ascii_letters(title)
    if len(letters) < 3 or letters in allowed:
        return False
    if not any(v in letters for v in _VOWELS):
        return True
    run = re.compile(rf"[bcdfghjklmnpqrstvwxz]{{{max_run},}}")
    # words are split on every non-letter, so "Mmm-Mmm-Magnificent" is three words
    folded = unicodedata.normalize("NFKD", title).encode(
        "ascii", "ignore").decode("ascii").lower()
    return any(run.search(word) for word in re.split(r"[^a-z]+", folded))


def junk_mask(titles: Iterable[str | None]) -> np.ndarray:
    """True where the title looks like a test record (same order as the input)."""
    return np.array([is_junk_title(t) for t in titles], dtype=bool)
