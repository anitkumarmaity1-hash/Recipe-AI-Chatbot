"""Output guard (Step 9): programmatic checks on the FINAL answer text.

The composer builds answers from tool output, so today these checks pass by
construction. They exist because the next layer (optional LLM wording) can
write anything: every recipe id and every number in the answer must come from
the tool output of the same turn, or the answer is withheld.
"""

from __future__ import annotations

import re
from typing import Iterable

from recipebot.data_loading import SOURCES

# Recipe ids are always printed inside square brackets: [ar:abc/def]
_ID = re.compile(
    r"\[((?:" + "|".join(map(re.escape, SOURCES)) + r"):[^\]\s]+)\]")


def check_reply(text: str, allowed_ids: Iterable[str], must_contain: Iterable[str] = ()) -> list[str]:
    """Return a list of problems; an empty list means the answer passed.

    allowed_ids:  ids that appear in this turn's tool output
    must_contain: exact strings (formatted numbers) the tool output requires
    """
    allowed = set(allowed_ids)
    problems = [f"recipe id not in this turn's tool output: {rid}"
                for rid in dict.fromkeys(_ID.findall(text)) if rid not in allowed]
    problems += [f"value from the tool output is missing: {needle}"
                 for needle in must_contain if needle not in text]
    return problems
