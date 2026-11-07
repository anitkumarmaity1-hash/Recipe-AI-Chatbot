"""Day 1, Step 4 (hybrid): build the normalized tables.

Run from the project root (after python -m recipebot.build_db):
    python -m recipebot.build_normalized              # normal run (Stage A is incremental)
    python -m recipebot.build_normalized --reparse    # throw the parser cache away and parse again

Stage A (slow, resumable): parse every UNIQUE cleaned ingredient line with ingredient-parser-nlp
        and store the raw output in table `ingredient_parse` (a cache, saved every chunk).
Stage B (fast, repeatable): combine the cache with our dictionary/regex rules to build
        `recipe_ingredient` and `recipe_stats`. Tuning synonyms only needs Stage B again.

Only derived tables are dropped/recreated. `recipes` is never modified.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from recipebot import config, db
from recipebot.normalization.ingredients import IngredientNormalizer, load_synonyms
from recipebot.normalization.parser_layer import (
    ParsedLine,
    _import_parser,
    normalize_unit,
    parse_line,
    resolve_line,
    warmup,
)
from recipebot.normalization.steps import count_lines, count_steps

logger = logging.getLogger(__name__)

# parser names below this are listed in the report
NAME_CONFIDENCE_THRESHOLD = 0.90
CHUNK_SIZE = 50_000                # unique lines parsed (and saved) per chunk
MAX_CHUNK_FAILURE_RATE = 0.05      # abort if more than 5% of a chunk fails to parse
FLUSH_ROWS = 200_000               # recipe_ingredient rows inserted per batch

CREATE_PARSE = """
CREATE TABLE IF NOT EXISTS ingredient_parse (
    line            VARCHAR PRIMARY KEY,   -- the CLEANED ingredient line
    names           VARCHAR[] NOT NULL,    -- raw parser names (original case, plural)
    name_confidence DOUBLE,
    quantity        DOUBLE,
    quantity_max    DOUBLE,
    unit            VARCHAR,
    preparation     VARCHAR,
    comment         VARCHAR,
    purpose         VARCHAR,
    parse_ok        BOOLEAN NOT NULL
)
"""
CREATE_STATS = """
CREATE TABLE recipe_stats (
    row_idx       INTEGER PRIMARY KEY,
    id            VARCHAR NOT NULL,
    n_ingredients INTEGER NOT NULL,
    n_lines       INTEGER NOT NULL,
    n_steps       INTEGER NOT NULL
)
"""
CREATE_INGREDIENT = """
CREATE TABLE recipe_ingredient (
    recipe_id        VARCHAR NOT NULL,
    row_idx          INTEGER NOT NULL,
    position         INTEGER NOT NULL,   -- index of the line in ingredients_clean
    name_index       INTEGER NOT NULL,   -- 0 for the first name on a line ("salt and pepper" has 0 and 1)
    raw_line         VARCHAR NOT NULL,   -- the CLEANED ingredient line
    canonical        VARCHAR NOT NULL,
    alternatives     VARCHAR[] NOT NULL, -- "butter or margarine": canonical=butter, alternatives=[margarine]
    quantity         DOUBLE,
    quantity_max     DOUBLE,
    unit             VARCHAR,
    preparation      VARCHAR,
    comment          VARCHAR,
    name_confidence  DOUBLE,
    canonical_source VARCHAR NOT NULL,   -- parser | regex_fallback
    regex_canonical  VARCHAR NOT NULL    -- what the regex layer alone says (audit)
)
"""


def _num(column: str) -> str:
    """pandas turns None into NaN in float columns; convert NaN back to a real SQL NULL."""
    return f"CASE WHEN isnan({column}::DOUBLE) THEN NULL ELSE {column}::DOUBLE END"


@dataclass
class ParseStats:
    total_unique: int = 0
    newly_parsed: int = 0


@dataclass
class DerivedStats:
    unparsed_count: int = 0
    unparsed_examples: list[str] = field(default_factory=list)
    # per ingredient line occurrence
    line_sources: Counter = field(default_factory=Counter)


# ------------------------------------------------------------------ Stage A
def build_parse_cache(db_path: Path | str, chunk_size: int = CHUNK_SIZE, reparse: bool = False) -> ParseStats:
    """Parse every unique cleaned ingredient line that is not in the cache yet."""
    warmup()
    parse = _import_parser()
    stats = ParseStats()
    con = db.connect(read_only=False, path=db_path)
    try:
        if reparse:
            con.execute("DROP TABLE IF EXISTS ingredient_parse")
        con.execute(CREATE_PARSE)
        all_lines = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT line FROM (SELECT unnest(ingredients_clean) AS line FROM recipes) ORDER BY line"
            ).fetchall()
        ]
        done = {r[0] for r in con.execute(
            "SELECT line FROM ingredient_parse").fetchall()}
        todo = [line for line in all_lines if line not in done]
        stats.total_unique = len(all_lines)
        logger.info("Unique cleaned lines: %s | already cached: %s | to parse: %s",
                    f"{len(all_lines):,}", f"{len(done):,}", f"{len(todo):,}")

        start = time.time()
        for begin in range(0, len(todo), chunk_size):
            chunk = todo[begin: begin + chunk_size]
            parsed = [parse_line(line, parse) for line in chunk]
            failed = [p.line for p in parsed if not p.parse_ok]
            if len(failed) > MAX_CHUNK_FAILURE_RATE * len(chunk):
                raise RuntimeError(
                    f"{len(failed)} of {len(chunk)} lines failed to parse (examples: {failed[:3]}). "
                    "This looks systematic, so nothing from this chunk was saved."
                )
            df = pd.DataFrame(
                [
                    {
                        "line": p.line, "names": p.names, "name_confidence": p.name_confidence,
                        "quantity": p.quantity, "quantity_max": p.quantity_max, "unit": p.unit,
                        "preparation": p.preparation, "comment": p.comment, "purpose": p.purpose,
                        "parse_ok": p.parse_ok,
                    }
                    for p in parsed
                ]
            )
            con.register("parse_df", df)
            try:
                con.execute(
                    f"INSERT INTO ingredient_parse SELECT line::VARCHAR, names::VARCHAR[], "
                    f"{_num('name_confidence')}, {_num('quantity')}, {_num('quantity_max')}, "
                    f"unit::VARCHAR, preparation::VARCHAR, comment::VARCHAR, purpose::VARCHAR, "
                    f"parse_ok::BOOLEAN FROM parse_df"
                )
            finally:
                con.unregister("parse_df")
            stats.newly_parsed += len(chunk)
            elapsed = time.time() - start
            rate = stats.newly_parsed / elapsed if elapsed else 0.0
            remaining = (len(todo) - stats.newly_parsed) / \
                rate if rate else 0.0
            logger.info("Parsed %s / %s lines (%.0f lines/s, about %.0f min left)",
                        f"{stats.newly_parsed:,}", f"{len(todo):,}", rate, remaining / 60)
    finally:
        con.close()
    return stats


# ------------------------------------------------------------------ Stage B
def _flush(con, rows: list[dict]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    con.register("ing_df", df)
    try:
        con.execute(
            f"INSERT INTO recipe_ingredient SELECT recipe_id::VARCHAR, row_idx::INTEGER, "
            f"position::INTEGER, name_index::INTEGER, raw_line::VARCHAR, canonical::VARCHAR, "
            f"alternatives::VARCHAR[], {_num('quantity')}, {_num('quantity_max')}, unit::VARCHAR, "
            f"preparation::VARCHAR, comment::VARCHAR, {_num('name_confidence')}, "
            f"canonical_source::VARCHAR, regex_canonical::VARCHAR FROM ing_df"
        )
    finally:
        con.unregister("ing_df")
    rows.clear()


def build_recipe_tables(
    db_path: Path | str, normalizer: IngredientNormalizer, log_every: int = 10_000
) -> DerivedStats:
    """Build recipe_stats and recipe_ingredient from the parser cache + our rules."""
    stats = DerivedStats()
    con = db.connect(read_only=False, path=db_path)
    try:
        cache: dict[str, ParsedLine] = {}
        for (line, names, conf, qty, qty_max, unit, prep, comment, purpose, ok) in con.execute(
            "SELECT line, names, name_confidence, quantity, quantity_max, unit, preparation, "
            "comment, purpose, parse_ok FROM ingredient_parse"
        ).fetchall():
            cache[line] = ParsedLine(line, list(
                names), conf, qty, qty_max, unit, prep, comment, purpose, ok)

        recipes = con.execute(
            "SELECT row_idx, id, ingredients_clean, instructions_clean FROM recipes ORDER BY row_idx"
        ).fetchall()

        con.execute("DROP TABLE IF EXISTS recipe_ingredient")
        con.execute("DROP TABLE IF EXISTS recipe_stats")
        con.execute(CREATE_STATS)
        con.execute(CREATE_INGREDIENT)

        resolved_cache = {}
        stats_rows: list[dict] = []
        ingredient_rows: list[dict] = []
        for i, (row_idx, rid, ingredients, instructions) in enumerate(recipes, 1):
            stats_rows.append(
                {"row_idx": row_idx, "id": rid, "n_ingredients": len(ingredients),
                 "n_lines": count_lines(instructions), "n_steps": count_steps(instructions)}
            )
            for position, line in enumerate(ingredients):
                parsed = cache.get(line)
                if parsed is None:
                    raise RuntimeError(
                        f"Parser cache is missing a line (e.g. {line!r}). Run Stage A first.")
                resolved = resolved_cache.get(line)
                if resolved is None:
                    resolved = resolved_cache[line] = resolve_line(
                        line, parsed, normalizer)
                stats.line_sources[resolved.source] += 1
                if not resolved.canonicals:
                    stats.unparsed_count += 1
                    if len(stats.unparsed_examples) < 15:
                        stats.unparsed_examples.append(line)
                    continue
                for name_index, canonical in enumerate(resolved.canonicals):
                    ingredient_rows.append(
                        {
                            "recipe_id": rid, "row_idx": row_idx, "position": position,
                            "name_index": name_index, "raw_line": line, "canonical": canonical,
                            "alternatives": resolved.alternatives, "quantity": parsed.quantity,
                            "quantity_max": parsed.quantity_max, "unit": normalize_unit(parsed.unit),
                            "preparation": parsed.preparation, "comment": parsed.comment,
                            "name_confidence": parsed.name_confidence,
                            "canonical_source": resolved.source,
                            "regex_canonical": resolved.regex_canonical,
                        }
                    )
            if len(ingredient_rows) >= FLUSH_ROWS:
                _flush(con, ingredient_rows)
            if i % log_every == 0:
                logger.info("Processed %s / %s recipes",
                            f"{i:,}", f"{len(recipes):,}")
        _flush(con, ingredient_rows)

        stats_df = pd.DataFrame(stats_rows)
        con.register("stats_df", stats_df)
        try:
            con.execute(
                "INSERT INTO recipe_stats SELECT row_idx::INTEGER, id::VARCHAR, n_ingredients::INTEGER, "
                "n_lines::INTEGER, n_steps::INTEGER FROM stats_df"
            )
        finally:
            con.unregister("stats_df")

        n_recipes = con.execute("SELECT count(*) FROM recipes").fetchone()[0]
        n_stats = con.execute(
            "SELECT count(*) FROM recipe_stats").fetchone()[0]
        if n_recipes != n_stats:
            raise RuntimeError(
                f"CHECK FAILED: recipe_stats has {n_stats} rows, recipes has {n_recipes}")
    finally:
        con.close()
    return stats


# ------------------------------------------------------------------ Report
def _md(value: object) -> str:
    return str(value).replace("|", "/")


def render_report(db_path: Path | str, stats: DerivedStats) -> str:
    con = db.connect(read_only=True, path=db_path)
    try:
        n_rec = con.execute("SELECT count(*) FROM recipe_stats").fetchone()[0]
        s_min, s_med, s_mean, s_max, s_zero, s_one_line = con.execute(
            "SELECT min(n_steps), median(n_steps), avg(n_steps), max(n_steps), "
            "count(*) FILTER (WHERE n_steps = 0), count(*) FILTER (WHERE n_lines <= 1) FROM recipe_stats"
        ).fetchone()
        l_med, l_mean, l_max = con.execute(
            "SELECT median(n_lines), avg(n_lines), max(n_lines) FROM recipe_stats"
        ).fetchone()
        i_min, i_med, i_mean, i_max = con.execute(
            "SELECT min(n_ingredients), median(n_ingredients), avg(n_ingredients), max(n_ingredients) "
            "FROM recipe_stats"
        ).fetchone()

        p_total, p_fail, p_noname = con.execute(
            "SELECT count(*), count(*) FILTER (WHERE NOT parse_ok), "
            "count(*) FILTER (WHERE parse_ok AND len(names) = 0) FROM ingredient_parse"
        ).fetchone()
        fail_examples = [r[0] for r in con.execute(
            "SELECT line FROM ingredient_parse WHERE NOT parse_ok ORDER BY hash(line) LIMIT 10").fetchall()]
        noname_examples = [r[0] for r in con.execute(
            "SELECT line FROM ingredient_parse WHERE parse_ok AND len(names) = 0 "
            "ORDER BY hash(line) LIMIT 10").fetchall()]

        n_rows = con.execute(
            "SELECT count(*) FROM recipe_ingredient").fetchone()[0]
        n_distinct = con.execute(
            "SELECT count(DISTINCT canonical) FROM recipe_ingredient").fetchone()[0]
        n_split = con.execute(
            "SELECT count(*) FILTER (WHERE name_index > 0) FROM recipe_ingredient").fetchone()[0]
        n_alt = con.execute(
            "SELECT count(*) FILTER (WHERE len(alternatives) > 0) FROM recipe_ingredient").fetchone()[0]
        no_canon = con.execute(
            "SELECT count(*) FROM recipes r WHERE NOT EXISTS "
            "(SELECT 1 FROM recipe_ingredient i WHERE i.row_idx = r.row_idx)"
        ).fetchone()[0]
        low_conf = con.execute(
            "SELECT count(*) FROM recipe_ingredient WHERE name_index = 0 AND canonical_source = 'parser' "
            f"AND name_confidence < {NAME_CONFIDENCE_THRESHOLD}"
        ).fetchone()[0]
        low_examples = con.execute(
            "SELECT DISTINCT raw_line, canonical, name_confidence FROM recipe_ingredient "
            f"WHERE canonical_source = 'parser' AND name_confidence < {NAME_CONFIDENCE_THRESHOLD} "
            "ORDER BY name_confidence, raw_line LIMIT 20"
        ).fetchall()
        n_first, n_diff = con.execute(
            "SELECT count(DISTINCT raw_line) FILTER (WHERE name_index = 0), "
            "count(DISTINCT raw_line) FILTER (WHERE name_index = 0 AND canonical <> regex_canonical) "
            "FROM recipe_ingredient"
        ).fetchone()
        diff_examples = con.execute(
            "SELECT raw_line, canonical, regex_canonical FROM ("
            "SELECT DISTINCT raw_line, canonical, regex_canonical FROM recipe_ingredient "
            "WHERE name_index = 0 AND canonical <> regex_canonical) ORDER BY hash(raw_line) LIMIT 30"
        ).fetchall()
        q_with, q_total = con.execute(
            "SELECT count(*) FILTER (WHERE name_index = 0 AND quantity IS NOT NULL), "
            "count(*) FILTER (WHERE name_index = 0) FROM recipe_ingredient"
        ).fetchone()
        units = con.execute(
            "SELECT unit, count(*) AS n FROM recipe_ingredient WHERE name_index = 0 AND unit IS NOT NULL "
            "GROUP BY unit ORDER BY n DESC LIMIT 15"
        ).fetchall()
        top = con.execute(
            "SELECT canonical, count(DISTINCT row_idx) AS n FROM recipe_ingredient "
            "GROUP BY canonical ORDER BY n DESC, canonical LIMIT 40"
        ).fetchall()
        sample = con.execute(
            "SELECT raw_line, canonical FROM recipe_ingredient "
            "ORDER BY hash(row_idx::VARCHAR || '|' || position::VARCHAR || '|' || name_index::VARCHAR) LIMIT 30"
        ).fetchall()
    finally:
        con.close()

    src = stats.line_sources
    out = [
        "# Normalization report (Step 4, hybrid)", "", f"Recipes processed: {n_rec:,}", "",
        "## Steps (rule: one sentence = one step, pysbd on instructions_clean)", "",
        "| Metric | Value |", "|---|---:|",
        f"| n_steps min / median / mean / max | {s_min} / {s_med} / {s_mean:.2f} / {s_max} |",
        f"| recipes with 0 steps | {s_zero:,} |",
        f"| n_lines median / mean / max | {l_med} / {l_mean:.2f} / {l_max} |",
        f"| recipes with 1 or fewer non-empty lines | {s_one_line:,} |",
        f"| n_ingredients min / median / mean / max | {i_min} / {i_med} / {i_mean:.2f} / {i_max} |",
        "", "## Parser stage (table ingredient_parse)", "", "| Metric | Value |", "|---|---:|",
        f"| unique cleaned lines in cache | {p_total:,} |",
        f"| parser failures (exception) | {p_fail:,} |",
        f"| parsed but no name found | {p_noname:,} |",
        "", "Failure examples: " +
            (", ".join(f"`{_md(x)}`" for x in fail_examples) or "(none)"),
        "", "No-name examples: " +
            (", ".join(f"`{_md(x)}`" for x in noname_examples) or "(none)"),
        "", "## Ingredient rows (table recipe_ingredient)", "", "| Metric | Value |", "|---|---:|",
        f"| ingredient line occurrences resolved by parser | {src.get('parser', 0):,} |",
        f"| resolved by regex fallback | {src.get('regex_fallback', 0):,} |",
        f"| no canonical name (skipped) | {stats.unparsed_count:,} |",
        f"| rows in recipe_ingredient | {n_rows:,} |",
        f"| extra rows from multi-name lines (\"salt and pepper\") | {n_split:,} |",
        f"| rows with alternatives (\"butter or margarine\") | {n_alt:,} |",
        f"| distinct canonical names | {n_distinct:,} |",
        f"| recipes with no canonical ingredient at all | {no_canon:,} |",
        f"| first-name rows with parser confidence < {NAME_CONFIDENCE_THRESHOLD} | {low_conf:,} |",
        f"| first-name rows with a quantity | {q_with:,} of {q_total:,} |",
        "", "### Skipped line examples", "",
    ]
    out += [f"- `{_md(x)}`" for x in stats.unparsed_examples] or ["- (none)"]
    out += ["", f"### Parser vs regex: {n_diff:,} of {n_first:,} distinct lines get a different canonical name",
            "", "| Cleaned line | Parser+rules (used) | Regex only |", "|---|---|---|"]
    out += [f"| {_md(r)} | {_md(c)} | {_md(x)} |" for r, c, x in diff_examples]
    out += ["", "### Lowest-confidence parser names", "",
            "| Cleaned line | Canonical | Confidence |", "|---|---|---:|"]
    out += [f"| {_md(r)} | {_md(c)} | {conf:.3f} |" for r,
            c, conf in low_examples]
    out += ["", "### Most common units (normalized)",
            "", "| Unit | Rows |", "|---|---:|"]
    out += [f"| {_md(u)} | {n:,} |" for u, n in units]
    out += ["", "### Top 40 canonical names (number of recipes)",
            "", "| Canonical | Recipes |", "|---|---:|"]
    out += [f"| {_md(c)} | {n:,} |" for c, n in top]
    out += ["", "### Deterministic sample: cleaned line -> canonical",
            "", "| Cleaned line | Canonical |", "|---|---|"]
    out += [f"| {_md(r)} | {_md(c)} |" for r, c in sample]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Build recipe_ingredient and recipe_stats.")
    parser.add_argument("--reparse", action="store_true",
                        help="drop the parser cache and parse every line again")
    args = parser.parse_args(argv)

    config.setup_logging()
    build_parse_cache(config.DB_PATH, reparse=args.reparse)
    normalizer = IngredientNormalizer(load_synonyms())
    logger.info("Loaded %d synonyms", len(normalizer.synonyms))
    stats = build_recipe_tables(config.DB_PATH, normalizer)
    report = render_report(config.DB_PATH, stats)
    print(report)
    path = config.PROJECT_ROOT / "docs" / "NORMALIZATION_REPORT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    logger.info("Report saved to %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
