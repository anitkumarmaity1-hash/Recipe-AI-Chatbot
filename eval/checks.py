"""Checks for the evaluation set (no database, no model in this file).

A case in eval/golden.json lists "checks" for one turn. Every check is a plain, readable test of
the chatbot's REPLY TEXT plus facts read back from the database (through a `Facts` object), so a
check never trusts the chatbot's own claim. run_checks() returns a list of failure messages;
an empty list means the turn passed.

Supported checks
  intent          the intent the chatbot used, e.g. "stats"
  contains        every string must appear in the reply
  contains_any    at least one string must appear
  not_contains    none of the strings may appear
  n_ids           exactly this many recipe ids [ar:...] in the reply
  min_ids         at least this many recipe ids
  ids_exist       every listed recipe id exists in the database (nothing invented)
  max_steps_ids   every listed recipe has at most this many steps (read from the database)
  no_allergen     none of the listed recipes has a line that mentions this allergen category
The output guard must also be clean in every turn.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, Sequence

from recipebot.data_loading import SOURCES

ID_PATTERN = re.compile(
    r"\[((?:" + "|".join(map(re.escape, SOURCES)) + r"):[^\]\s]+)\]")
KNOWN_CHECKS = {"intent", "contains", "contains_any", "not_contains", "n_ids", "min_ids",
                "ids_exist", "max_steps_ids", "no_allergen"}


class Facts(Protocol):
    def existing_ids(self, ids: Sequence[str]) -> set[str]: ...
    def n_steps(self, ids: Sequence[str]) -> dict[str, int]: ...
    def allergen_hits(
        self, ids: Sequence[str], allergen: str) -> list[str]: ...


def ids_in(text: str) -> list[str]:
    """Recipe ids printed in square brackets, in order, without duplicates."""
    return list(dict.fromkeys(ID_PATTERN.findall(text)))


def run_checks(text: str, intent: str, guard_problems: Sequence[str],
               checks: dict[str, Any], facts: Facts) -> list[str]:
    unknown = set(checks) - KNOWN_CHECKS
    if unknown:
        return [f"unknown check(s): {sorted(unknown)}"]
    failures: list[str] = []
    ids = ids_in(text)

    if guard_problems:
        failures.append(f"output guard problems: {list(guard_problems)}")
    if "intent" in checks and intent != checks["intent"]:
        failures.append(
            f"intent was '{intent}', expected '{checks['intent']}'")
    for needle in checks.get("contains", []):
        if needle not in text:
            failures.append(f"reply does not contain: {needle!r}")
    if checks.get("contains_any") and not any(n in text for n in checks["contains_any"]):
        failures.append(f"reply contains none of: {checks['contains_any']}")
    for needle in checks.get("not_contains", []):
        if needle in text:
            failures.append(f"reply must not contain: {needle!r}")
    if "n_ids" in checks and len(ids) != checks["n_ids"]:
        failures.append(
            f"{len(ids)} recipe ids listed, expected {checks['n_ids']}")
    if "min_ids" in checks and len(ids) < checks["min_ids"]:
        failures.append(
            f"{len(ids)} recipe ids listed, expected at least {checks['min_ids']}")
    if checks.get("ids_exist") and ids:
        missing = [i for i in ids if i not in facts.existing_ids(ids)]
        if missing:
            failures.append(f"recipe ids not in the database: {missing}")
    if "max_steps_ids" in checks and ids:
        limit = checks["max_steps_ids"]
        too_long = {i: n for i, n in facts.n_steps(ids).items() if n > limit}
        if too_long:
            failures.append(f"recipes over the {limit}-step limit: {too_long}")
    if checks.get("no_allergen") and ids:
        hits = facts.allergen_hits(ids, checks["no_allergen"])
        if hits:
            failures.append(
                f"recipes mention {checks['no_allergen']}: {hits[:3]}")
    return failures
