"""Exploratory data analysis (EDA) of the three raw Recipe Box files.

Purpose: answer the open questions from handover section 6.1 with real numbers
before we design the database:

* Are recipe keys unique across the three files (can IDs be ``{source}:{key}``)?
* Is ``instructions`` a string or a list, and is it newline-separated?
* How many records have missing/empty fields, 0 or 1 ingredients?
* How much junk is there (``ADVERTISEMENT`` lines, section headers)?
* How many exact duplicate recipes exist?

Run from the project root:

    python -m recipebot.eda

The report is printed and also saved to docs/EDA_REPORT.md. Every number is
computed by this code from the real files; nothing is hand-written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from recipebot import config
from recipebot.data_loading import SOURCE_LABELS, SOURCES, load_raw_file, raw_file_path

logger = logging.getLogger(__name__)

ADVERT_RE = re.compile(r"advertisement", re.IGNORECASE)
# Rough sentence splitter: a proxy only. The real step-counting rule is decided in Step 4.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
MAX_EXAMPLES = 5


def _is_empty(value: Any) -> bool:
    """True for None, blank strings and empty containers."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _instructions_text(value: Any) -> str:
    """Return instructions as one text block, whether stored as str or list."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def _summary(values: list[float]) -> dict[str, float | None]:
    """min / median / mean / max of a list (None values when the list is empty)."""
    if not values:
        return {"min": None, "median": None, "mean": None, "max": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": round(statistics.fmean(values), 2),
        "max": max(values),
    }


def content_fingerprint(record: dict[str, Any]) -> str:
    """Hash of (title, ingredients, instructions); equal hash = exact duplicate content."""
    payload = json.dumps(
        [record.get("title"), record.get("ingredients"),
         record.get("instructions")],
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def analyze_source(records: dict[str, Any]) -> dict[str, Any]:
    """Compute all EDA statistics for one raw file (a {key: record} mapping)."""
    field_presence: Counter[str] = Counter()
    value_types: dict[str, Counter[str]] = {
        "title": Counter(),
        "ingredients": Counter(),
        "instructions": Counter(),
    }
    empty_counts = {"title": 0, "ingredients": 0, "instructions": 0}
    ingredient_counts: list[int] = []
    lines_total = lines_empty = lines_advert = lines_header = 0
    advert_examples: list[str] = []
    header_examples: list[str] = []
    instr_lengths: list[int] = []
    instr_sentences: list[int] = []
    instr_with_newline = instr_with_advert = 0
    titles: Counter[str] = Counter()
    fingerprints: Counter[str] = Counter()
    non_dict = 0
    sample_record: dict[str, Any] | None = None

    for rec in records.values():
        if not isinstance(rec, dict):
            non_dict += 1
            continue
        if sample_record is None and not _is_empty(rec.get("ingredients")):
            sample_record = rec
        field_presence.update(rec.keys())
        for name, counter in value_types.items():
            counter[type(rec.get(name)).__name__] += 1
            if _is_empty(rec.get(name)):
                empty_counts[name] += 1

        # Ingredients (expected: list of raw strings).
        ingredients = rec.get("ingredients")
        lines = [str(x) for x in ingredients] if isinstance(
            ingredients, list) else []
        ingredient_counts.append(len(lines))
        for line in lines:
            lines_total += 1
            stripped = line.strip()
            if not stripped:
                lines_empty += 1
            elif ADVERT_RE.search(stripped):
                lines_advert += 1
                if len(advert_examples) < MAX_EXAMPLES:
                    advert_examples.append(stripped)
            elif stripped.endswith(":"):
                lines_header += 1
                if len(header_examples) < MAX_EXAMPLES:
                    header_examples.append(stripped)

        # Instructions (expected: one string).
        text = _instructions_text(rec.get("instructions"))
        if text.strip():
            instr_lengths.append(len(text))
            sentences = [s for s in SENTENCE_SPLIT_RE.split(text.strip()) if s]
            instr_sentences.append(len(sentences))
            if "\n" in text.strip():
                instr_with_newline += 1
            if ADVERT_RE.search(text):
                instr_with_advert += 1

        title = rec.get("title")
        if isinstance(title, str) and title.strip():
            titles[title.strip().lower()] += 1
        fingerprints[content_fingerprint(rec)] += 1

    return {
        "n_records": len(records),
        "non_dict": non_dict,
        "fields_seen": sorted(field_presence),
        "field_presence": dict(field_presence),
        "value_types": {k: dict(v) for k, v in value_types.items()},
        "empty_counts": empty_counts,
        "ingredient_count_summary": _summary(ingredient_counts),
        "records_with_0_ingredients": sum(1 for n in ingredient_counts if n == 0),
        "records_with_1_ingredient": sum(1 for n in ingredient_counts if n == 1),
        "records_with_le2_ingredients": sum(1 for n in ingredient_counts if n <= 2),
        "ingredient_lines_total": lines_total,
        "ingredient_lines_empty": lines_empty,
        "ingredient_lines_advert": lines_advert,
        "ingredient_lines_header_like": lines_header,
        "advert_examples": advert_examples,
        "header_examples": header_examples,
        "instr_with_newline": instr_with_newline,
        "instr_with_advert": instr_with_advert,
        "instr_length_summary": _summary(instr_lengths),
        "instr_sentence_summary": _summary(instr_sentences),
        "duplicate_title_extra_copies": sum(c - 1 for c in titles.values() if c > 1),
        "duplicate_content_extra_copies": sum(c - 1 for c in fingerprints.values() if c > 1),
        # Kept for cross-file checks; not shown in the report tables.
        "_keys": set(records),
        "_fingerprints": set(fingerprints),
        "_sample_record": sample_record,
    }


def analyze_cross_file(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compare files with each other: key collisions and cross-file duplicate content."""
    sources = list(results)
    key_overlaps: dict[str, int] = {}
    content_overlaps: dict[str, int] = {}
    for i, first in enumerate(sources):
        for second in sources[i + 1:]:
            label = f"{first} & {second}"
            key_overlaps[label] = len(
                results[first]["_keys"] & results[second]["_keys"])
            content_overlaps[label] = len(
                results[first]["_fingerprints"] & results[second]["_fingerprints"])
    total_records = sum(r["n_records"] for r in results.values())
    all_keys: set[str] = set().union(*(r["_keys"] for r in results.values()))
    return {
        "total_records": total_records,
        "unique_keys_overall": len(all_keys),
        "key_overlaps": key_overlaps,
        "content_overlaps": content_overlaps,
    }


def _fmt_counter(counter: dict[str, int]) -> str:
    return ", ".join(f"{k}: {v:,}" for k, v in sorted(counter.items())) or "-"


def _fmt_summary(s: dict[str, float | None]) -> str:
    return f"{s['min']} / {s['median']} / {s['mean']} / {s['max']}"


def render_report(results: dict[str, dict[str, Any]], cross: dict[str, Any]) -> str:
    """Render the EDA results as Markdown."""
    sources = list(results)
    header = "| Metric | " + \
        " | ".join(SOURCE_LABELS[s] for s in sources) + " |"
    divider = "|---|" + "---|" * len(sources)

    def row(label: str, getter) -> str:
        return f"| {label} | " + " | ".join(str(getter(results[s])) for s in sources) + " |"

    lines = [
        "# EDA Report: Recipe Box raw data",
        "",
        f"Generated by `python -m recipebot.eda` on {date.today().isoformat()}. "
        "All numbers are computed from the files in `data/raw/`.",
        "",
        "## Overall",
        f"- Total records (sum of files): **{cross['total_records']:,}**",
        f"- Unique hash keys across all files: **{cross['unique_keys_overall']:,}**",
        f"- Key collisions between files: {cross['key_overlaps']}",
        f"- Identical-content recipes shared between files: {cross['content_overlaps']}",
        "",
        "## Per-file statistics",
        header,
        divider,
        row("Records", lambda r: f"{r['n_records']:,}"),
        row("Non-object records", lambda r: r["non_dict"]),
        row("Field names seen", lambda r: ", ".join(r["fields_seen"])),
        row("`title` value types", lambda r: _fmt_counter(
            r["value_types"]["title"])),
        row("`ingredients` value types", lambda r: _fmt_counter(
            r["value_types"]["ingredients"])),
        row("`instructions` value types", lambda r: _fmt_counter(
            r["value_types"]["instructions"])),
        row("Empty/missing title",
            lambda r: f"{r['empty_counts']['title']:,}"),
        row("Empty/missing ingredients",
            lambda r: f"{r['empty_counts']['ingredients']:,}"),
        row("Empty/missing instructions",
            lambda r: f"{r['empty_counts']['instructions']:,}"),
        row("Ingredients per recipe (min / median / mean / max)",
            lambda r: _fmt_summary(r["ingredient_count_summary"])),
        row("Recipes with 0 ingredients",
            lambda r: f"{r['records_with_0_ingredients']:,}"),
        row("Recipes with 1 ingredient",
            lambda r: f"{r['records_with_1_ingredient']:,}"),
        row("Recipes with <= 2 ingredients",
            lambda r: f"{r['records_with_le2_ingredients']:,}"),
        row("Ingredient lines (total)",
            lambda r: f"{r['ingredient_lines_total']:,}"),
        row("Empty ingredient lines",
            lambda r: f"{r['ingredient_lines_empty']:,}"),
        row("Ingredient lines containing ADVERTISEMENT",
            lambda r: f"{r['ingredient_lines_advert']:,}"),
        row("Ingredient lines ending with ':' (section-header-like)",
            lambda r: f"{r['ingredient_lines_header_like']:,}"),
        row("Instructions containing a newline",
            lambda r: f"{r['instr_with_newline']:,}"),
        row("Instructions containing ADVERTISEMENT",
            lambda r: f"{r['instr_with_advert']:,}"),
        row("Instruction length in chars (min / median / mean / max)",
            lambda r: _fmt_summary(r["instr_length_summary"])),
        row("Rough sentence count per recipe (min / median / mean / max)",
            lambda r: _fmt_summary(r["instr_sentence_summary"])),
        row("Extra copies sharing a title (case-insensitive)",
            lambda r: f"{r['duplicate_title_extra_copies']:,}"),
        row("Extra copies with identical title+ingredients+instructions",
            lambda r: f"{r['duplicate_content_extra_copies']:,}"),
        "",
        "Note: the sentence count is only a rough proxy. The real step-counting rule is decided in Day 1 Step 4.",
        "",
        "## Examples of suspicious ingredient lines",
    ]
    for s in sources:
        lines.append(
            f"- {SOURCE_LABELS[s]} ADVERTISEMENT lines: {results[s]['advert_examples'] or 'none found'}")
        lines.append(
            f"- {SOURCE_LABELS[s]} header-like lines: {results[s]['header_examples'] or 'none found'}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run EDA on the three raw Recipe Box files.")
    parser.add_argument("--raw-dir", type=Path, default=config.RAW_DIR)
    parser.add_argument("--report", type=Path,
                        default=config.PROJECT_ROOT / "docs" / "EDA_REPORT.md")
    args = parser.parse_args(argv)

    config.setup_logging()
    results: dict[str, dict[str, Any]] = {}
    for source in SOURCES:
        try:
            records = load_raw_file(raw_file_path(source, args.raw_dir))
        except (FileNotFoundError, ValueError) as exc:
            logger.error("%s", exc)
            return 1
        logger.info("Analyzing %s (%d records)", source, len(records))
        results[source] = analyze_source(records)

    cross = analyze_cross_file(results)
    report = render_report(results, cross)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(report)

    # One real record per file so you can see the raw shape (console only, not saved).
    for source, res in results.items():
        sample = json.dumps(res["_sample_record"],
                            indent=2, ensure_ascii=False)
        print(
            f"--- Sample record from {SOURCE_LABELS[source]} (truncated) ---")
        print(sample[:1500])
    logger.info("Report saved to %s", args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
