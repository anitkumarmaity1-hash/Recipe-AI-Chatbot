"""Cleaning rules for raw Recipe Box records (Day 1, Step 3).

Everything here is pure Python: no files, no database. That makes the rules easy
to test and easy to explain. The raw data is never modified; we only produce
*additional* cleaned values next to the originals.

Rules (approved by the user):
  1. ADVERTISEMENT is stripped from ingredient lines; lines that are only
     ADVERTISEMENT are dropped.
  2. Instructions that are exactly "text\\ntext" keep one copy in the cleaned column.
  3. Records with no title or no ingredients are excluded (with a reason).
     Records with empty instructions are KEPT and flagged.
  4. Ingredient lines ending with ":" (section headers like "TOPPING:") are
     dropped from the cleaned list.
  5. Exact duplicates are excluded (first one kept). Empty records are excluded
     BEFORE duplicate detection, and we never dedupe by title alone.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

AD_PATTERN = re.compile(r"ADVERTISEMENT", re.IGNORECASE)

REASON_MALFORMED = "malformed_record"
REASON_NO_TITLE = "empty_title"
REASON_NO_INGREDIENTS = "empty_ingredients"
REASON_NO_USABLE = "no_usable_ingredients_after_cleaning"
REASON_DUPLICATE = "exact_duplicate"
ALL_REASONS = (
    REASON_MALFORMED,
    REASON_NO_TITLE,
    REASON_NO_INGREDIENTS,
    REASON_NO_USABLE,
    REASON_DUPLICATE,
)


@dataclass
class BuildResult:
    """Output of process_sources: rows for both tables plus per-source counters."""

    usable: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Counter] = field(default_factory=dict)


def clean_ingredient_line(line: Any) -> tuple[str, str]:
    """Clean one ingredient line. Returns (cleaned_text, status).

    status is one of:
      "kept"         unchanged apart from whitespace
      "ad_stripped"  ADVERTISEMENT removed, real text remains (kept)
      "ad_only"      nothing left after removing ADVERTISEMENT (dropped)
      "header"       section header ending with ":" (dropped)
      "empty"        empty or non-string line (dropped)
    """
    if not isinstance(line, str):
        return "", "empty"
    had_ad = bool(AD_PATTERN.search(line))
    text = " ".join(AD_PATTERN.sub(" ", line).split())
    if not text:
        return "", "ad_only" if had_ad else "empty"
    if text.endswith(":"):
        return text, "header"
    return text, "ad_stripped" if had_ad else "kept"


def clean_ingredients(lines: list[Any], counter: Counter | None = None) -> list[str]:
    """Clean a whole ingredient list; only 'kept' and 'ad_stripped' lines survive."""
    cleaned: list[str] = []
    for line in lines:
        text, status = clean_ingredient_line(line)
        if counter is not None:
            counter["lines_total"] += 1
            counter[f"lines_{status}"] += 1
        if status in ("kept", "ad_stripped"):
            cleaned.append(text)
    return cleaned


def undouble_instructions(text: str) -> tuple[str, bool]:
    """If text is exactly <copy> + "\\n" + <same copy>, return (one copy, True).

    Otherwise return (text, False). Exact match only (after trimming outer
    whitespace), so we never guess.
    """
    trimmed = text.strip()
    n = len(trimmed)
    if n >= 3 and n % 2 == 1:
        half = n // 2
        if trimmed[half] == "\n" and trimmed[:half] == trimmed[half + 1:]:
            return trimmed[:half], True
    return text, False


def content_fingerprint(title: Any, ingredients: Any, instructions: Any) -> str:
    """SHA-256 of the ORIGINAL content: two records match only if all three are identical."""
    payload = json.dumps([title, ingredients, instructions],
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _exclude(
    result: BuildResult,
    st: Counter,
    rid: str,
    source: str,
    record: Any,
    reason: str,
    duplicate_of: str | None = None,
) -> None:
    result.excluded.append(
        {
            "id": rid,
            "source": source,
            "reason": reason,
            "duplicate_of": duplicate_of,
            "raw_json": json.dumps(record, ensure_ascii=False),
        }
    )
    st["excluded"] += 1
    st[f"excluded:{reason}"] += 1


def process_sources(raw_by_source: dict[str, dict[str, Any]]) -> BuildResult:
    """Apply all cleaning rules. Order of sources and records defines row_idx."""
    result = BuildResult()
    seen: dict[str, str] = {}  # fingerprint -> id of the first kept record

    for source, records in raw_by_source.items():
        st = result.stats.setdefault(source, Counter())
        for key, rec in records.items():
            rid = f"{source}:{key}"
            st["raw_records"] += 1

            if not isinstance(rec, dict):
                _exclude(result, st, rid, source, rec, REASON_MALFORMED)
                continue

            title = rec.get("title")
            raw_ings = rec.get("ingredients")
            raw_ins = rec.get("instructions")

            cleaned_ings = clean_ingredients(
                raw_ings, st) if isinstance(raw_ings, list) else []

            if isinstance(raw_ins, str):
                body, was_doubled = undouble_instructions(raw_ins)
                if was_doubled:
                    st["doubled_instructions"] += 1
            else:
                body, was_doubled = "", False
                if raw_ins is not None:
                    st["non_string_instructions"] += 1

            # Reasons are checked in this fixed order.
            reason = None
            if not isinstance(title, str) or not title.strip():
                reason = REASON_NO_TITLE
            elif not isinstance(raw_ings, list) or len(raw_ings) == 0:
                reason = REASON_NO_INGREDIENTS
            elif not cleaned_ings:
                reason = REASON_NO_USABLE

            duplicate_of = None
            if reason is None:
                fp = content_fingerprint(title, raw_ings, raw_ins)
                if fp in seen:
                    reason, duplicate_of = REASON_DUPLICATE, seen[fp]
                else:
                    seen[fp] = rid

            if reason is not None:
                _exclude(result, st, rid, source, rec, reason, duplicate_of)
                continue

            instructions_clean = body.strip()
            instructions_empty = instructions_clean == ""
            if instructions_empty:
                st["empty_instructions"] += 1

            originals = [x if isinstance(x, str) else str(x) for x in raw_ings]
            st["non_string_ingredient_items"] += sum(
                1 for x in raw_ings if not isinstance(x, str))

            st["usable"] += 1
            result.usable.append(
                {
                    "id": rid,
                    "row_idx": len(result.usable),
                    "source": source,
                    "title": title,
                    "ingredients": originals,
                    "instructions": raw_ins if isinstance(raw_ins, str) else None,
                    "ingredients_clean": cleaned_ings,
                    "instructions_clean": instructions_clean,
                    "instructions_empty": instructions_empty,
                    "instructions_was_doubled": was_doubled,
                }
            )
    return result
