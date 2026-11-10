"""Safety net for substitution requests: restrictions the user wrote in the message.

Why this exists: for "replace the cream without dairy" the language model may return an empty
`exclude` list, and then "dairy" would silently not be a hard constraint. The safety decision
must not depend on the model, so this module reads the user's own message with a few plain
patterns and keeps only the phrases that restriction_terms.yaml says are allergen categories
or unsupported diets. Ordinary ingredient phrases ("without butter") are left to the model.
"""

from __future__ import annotations

import re
from typing import Iterable

from recipebot.understanding.restrictions import RestrictionMapper, normalize_phrase

_END = r"(?=\s*(?:[,.;:!?]|\band\b|\bor\b|\bbut\b|\bplease\b|$))"
# "without dairy", "no nuts", "allergic to eggs", "cannot have dairy"
_AFTER = re.compile(
    r"\b(?:without|avoid|no|allergic to|cannot have|can not have|can't have|cant have|"
    r"don't eat|do not eat)\s+(?:any\s+|the\s+|all\s+|my\s+)?([a-z][a-z -]*?)" + _END)
# "dairy free", "gluten-free"
_FREE = re.compile(r"\b([a-z]+[ -]free)\b")
_MAX_WORDS = 3


def _is_known(phrase: str, mapper: RestrictionMapper) -> bool:
    mapped = mapper.map([phrase])
    return bool(mapped.allergens or mapped.unsupported)


def restriction_hints(message: str, mapper: RestrictionMapper) -> list[str]:
    """Allergen or unsupported-diet phrases found in the message, in order, without duplicates."""
    text = (message or "").lower().replace("\u2019", "'")
    found: list[str] = []
    for pattern in (_AFTER, _FREE):
        for match in pattern.finditer(text):
            words = match.group(1).split()
            # "nuts either" -> try "nuts"; "dairy products" -> try "dairy", then "dairy products"
            for n in range(1, min(len(words), _MAX_WORDS) + 1):
                candidate = " ".join(words[:n])
                if _is_known(candidate, mapper):
                    if candidate not in found:
                        found.append(candidate)
                    break
    return found


def merge_hints(message: str, exclude: Iterable[str], mapper: RestrictionMapper) -> list[str]:
    """The model's exclude list plus any hint it missed (nothing is removed or reordered)."""
    current = list(exclude)
    have = {normalize_phrase(x) for x in current}
    for phrase in restriction_hints(message, mapper):
        if normalize_phrase(phrase) not in have:
            current.append(phrase)
            have.add(normalize_phrase(phrase))
    return current
