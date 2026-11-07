"""Day 1, Step 3: build the DuckDB database from the three raw files.

Run from the project root:
    python -m recipebot.build_db            # first build
    python -m recipebot.build_db --force    # rebuild (old file replaced only if all checks pass)

Tables
  recipes           usable records: ORIGINAL columns + CLEANED columns + flags
  recipes_excluded  excluded records with a reason (original record kept as JSON)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from recipebot import config
from recipebot.cleaning import ALL_REASONS, BuildResult, process_sources
from recipebot.data_loading import SOURCE_LABELS, SOURCES, load_raw_file, raw_file_path

logger = logging.getLogger(__name__)

CREATE_RECIPES = """
CREATE TABLE recipes (
    id                       VARCHAR PRIMARY KEY,
    row_idx                  INTEGER NOT NULL,
    source                   VARCHAR NOT NULL,
    title                    VARCHAR NOT NULL,
    ingredients              VARCHAR[] NOT NULL,   -- ORIGINAL
    instructions             VARCHAR,              -- ORIGINAL
    ingredients_clean        VARCHAR[] NOT NULL,   -- cleaned
    instructions_clean       VARCHAR NOT NULL,     -- cleaned
    instructions_empty       BOOLEAN NOT NULL,
    instructions_was_doubled BOOLEAN NOT NULL
)
"""

CREATE_EXCLUDED = """
CREATE TABLE recipes_excluded (
    id           VARCHAR PRIMARY KEY,
    source       VARCHAR NOT NULL,
    reason       VARCHAR NOT NULL,
    duplicate_of VARCHAR,
    raw_json     VARCHAR NOT NULL
)
"""

STAT_ROWS = [
    ("Raw records read", "raw_records"),
    ("Usable (table `recipes`)", "usable"),
    ("Excluded (table `recipes_excluded`)", "excluded"),
    *[(f"- excluded: {r}", f"excluded:{r}") for r in ALL_REASONS],
    ("Usable with empty instructions (kept, flagged)", "empty_instructions"),
    ("Doubled instructions (exact match, all non-malformed records)",
     "doubled_instructions"),
    ("Ingredient lines seen (records with a list of ingredients)", "lines_total"),
    ("- kept unchanged", "lines_kept"),
    ("- ADVERTISEMENT stripped, text kept", "lines_ad_stripped"),
    ("- dropped: ADVERTISEMENT only", "lines_ad_only"),
    ("- dropped: section header ending with ':'", "lines_header"),
    ("- dropped: empty", "lines_empty"),
    ("Non-string instructions (expected 0)", "non_string_instructions"),
    ("Non-string ingredient items in usable records (expected 0)",
     "non_string_ingredient_items"),
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"CHECK FAILED: {message}")


def write_database(result: BuildResult, db_path: Path) -> None:
    """Create both tables and insert all rows."""
    con = duckdb.connect(str(db_path))
    try:
        con.execute(CREATE_RECIPES)
        con.execute(CREATE_EXCLUDED)
        if result.usable:
            usable_df = pd.DataFrame(result.usable)
            con.register("usable_df", usable_df)
            con.execute(
                """INSERT INTO recipes SELECT
                       id::VARCHAR, row_idx::INTEGER, source::VARCHAR, title::VARCHAR,
                       ingredients::VARCHAR[], instructions::VARCHAR,
                       ingredients_clean::VARCHAR[], instructions_clean::VARCHAR,
                       instructions_empty::BOOLEAN, instructions_was_doubled::BOOLEAN
                   FROM usable_df"""
            )
            con.unregister("usable_df")
        if result.excluded:
            excluded_df = pd.DataFrame(result.excluded)
            con.register("excluded_df", excluded_df)
            con.execute(
                """INSERT INTO recipes_excluded SELECT
                       id::VARCHAR, source::VARCHAR, reason::VARCHAR,
                       duplicate_of::VARCHAR, raw_json::VARCHAR
                   FROM excluded_df"""
            )
            con.unregister("excluded_df")
    finally:
        con.close()


def run_checks(db_path: Path, result: BuildResult, raw_by_source: dict[str, dict[str, Any]]) -> list[str]:
    """Verify the freshly built database. Raises RuntimeError on the first failure."""
    total_raw = sum(len(r) for r in raw_by_source.values())
    lines: list[str] = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        n_usable = con.execute("SELECT count(*) FROM recipes").fetchone()[0]
        n_excl = con.execute(
            "SELECT count(*) FROM recipes_excluded").fetchone()[0]
        _require(n_usable == len(result.usable) and n_excl == len(result.excluded),
                 "table sizes differ from the in-memory result")
        _require(n_usable + n_excl == total_raw,
                 f"usable ({n_usable}) + excluded ({n_excl}) != raw records ({total_raw})")
        lines.append(
            f"PASS usable ({n_usable:,}) + excluded ({n_excl:,}) = raw records ({total_raw:,})")

        if n_usable:
            lo, hi, distinct = con.execute(
                "SELECT min(row_idx), max(row_idx), count(DISTINCT row_idx) FROM recipes"
            ).fetchone()
            _require(lo == 0 and hi == n_usable - 1 and distinct == n_usable,
                     "row_idx is not exactly 0..N-1")
            db_ids = [r[0] for r in con.execute(
                "SELECT id FROM recipes ORDER BY row_idx").fetchall()]
            _require(db_ids == [u["id"] for u in result.usable],
                     "row_idx order differs from build order")
            lines.append(
                f"PASS row_idx is 0..{n_usable - 1:,}, unique, in build order")

        ad = con.execute(
            "SELECT count(*) FROM (SELECT unnest(ingredients_clean) AS line FROM recipes) "
            "WHERE upper(line) LIKE '%ADVERTISEMENT%'"
        ).fetchone()[0]
        _require(
            ad == 0, f"{ad} cleaned ingredient lines still contain ADVERTISEMENT")
        bad = con.execute(
            "SELECT count(*) FROM (SELECT unnest(ingredients_clean) AS line FROM recipes) "
            "WHERE trim(line) = '' OR line LIKE '%:'"
        ).fetchone()[0]
        _require(
            bad == 0, f"{bad} cleaned ingredient lines are empty or end with ':'")
        empty_lists = con.execute(
            "SELECT count(*) FROM recipes WHERE len(ingredients_clean) = 0"
        ).fetchone()[0]
        _require(empty_lists == 0,
                 f"{empty_lists} usable recipes have no cleaned ingredients")
        lines.append(
            "PASS no cleaned ingredient line contains ADVERTISEMENT, is empty, or ends with ':'")

        flag_bad = con.execute(
            "SELECT count(*) FROM recipes WHERE instructions_empty != (trim(instructions_clean) = '')"
        ).fetchone()[0]
        _require(flag_bad == 0,
                 "instructions_empty flag disagrees with instructions_clean")
        lines.append("PASS instructions_empty flag is consistent")

        mismatches = 0
        for rid, title, ings, ins in con.execute(
            "SELECT id, title, ingredients, instructions FROM recipes ORDER BY row_idx"
        ).fetchall():
            source, _, key = rid.partition(":")
            rec = raw_by_source[source][key]
            expected_ings = [x if isinstance(x, str) else str(
                x) for x in rec["ingredients"]]
            expected_ins = rec.get("instructions")
            if not isinstance(expected_ins, str):
                expected_ins = None
            if title != rec["title"] or list(ings) != expected_ings or ins != expected_ins:
                mismatches += 1
        _require(mismatches == 0,
                 f"{mismatches} usable recipes differ from the raw files in original columns")
        lines.append(
            "PASS original columns (title, ingredients, instructions) are identical to the raw files")

        bad_excl = 0
        for rid, raw_json in con.execute("SELECT id, raw_json FROM recipes_excluded").fetchall():
            source, _, key = rid.partition(":")
            if json.loads(raw_json) != raw_by_source[source][key]:
                bad_excl += 1
        _require(bad_excl == 0,
                 f"{bad_excl} excluded records differ from the raw files")
        orphan = con.execute(
            "SELECT count(*) FROM recipes_excluded WHERE reason = 'exact_duplicate' "
            "AND duplicate_of NOT IN (SELECT id FROM recipes)"
        ).fetchone()[0]
        _require(
            orphan == 0, f"{orphan} duplicates point to a recipe that is not in `recipes`")
        lines.append(
            "PASS excluded records are recoverable and every duplicate points to a kept recipe")
    finally:
        con.close()
    return lines


def build_database(raw_by_source: dict[str, dict[str, Any]], db_path: Path) -> tuple[BuildResult, list[str]]:
    """Clean, write to a temporary file, verify, then replace db_path."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_name(db_path.name + ".tmp")
    for leftover in (tmp_path, tmp_path.with_name(tmp_path.name + ".wal")):
        if leftover.exists():
            leftover.unlink()

    result = process_sources(raw_by_source)
    write_database(result, tmp_path)
    # raises if anything is wrong
    check_lines = run_checks(tmp_path, result, raw_by_source)
    os.replace(tmp_path, db_path)
    logger.info("Database written to %s", db_path)
    return result, check_lines


def render_report(result: BuildResult, check_lines: list[str]) -> str:
    sources = list(result.stats)
    labels = [SOURCE_LABELS.get(s, s) for s in sources]
    out = ["# Build DB report (Step 3)", "", "| Metric | " + " | ".join(labels) + " | Total |",
           "|---|" + "---:|" * (len(sources) + 1)]
    for label, key in STAT_ROWS:
        values = [result.stats[s].get(key, 0) for s in sources]
        out.append(
            f"| {label} | " + " | ".join(f"{v:,}" for v in values) + f" | {sum(values):,} |")
    out += ["", "## Checks", ""] + [f"- {line}" for line in check_lines]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the recipes DuckDB database.")
    parser.add_argument("--force", action="store_true",
                        help="rebuild even if the database exists")
    parser.add_argument("--db-path", default=str(config.DB_PATH))
    args = parser.parse_args(argv)

    config.setup_logging()
    db_path = Path(args.db_path)
    if db_path.exists() and not args.force:
        logger.error(
            "%s already exists. Use --force to rebuild (it is replaced only if all checks pass).", db_path)
        return 1

    raw = {source: load_raw_file(raw_file_path(source)) for source in SOURCES}
    result, check_lines = build_database(raw, db_path)

    report = render_report(result, check_lines)
    print(report)
    report_path = config.PROJECT_ROOT / "docs" / "BUILD_DB_REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    logger.info("Report saved to %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
