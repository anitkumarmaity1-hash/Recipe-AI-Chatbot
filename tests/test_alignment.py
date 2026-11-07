"""Alignment and integrity tests on the REAL database.

Skipped until the database is built (python -m recipebot.build_db).
In Step 6 the BM25 and FAISS length/ID checks will be added here.
"""
import duckdb
import pytest

from recipebot import config
from recipebot.cleaning import ALL_REASONS

pytestmark = pytest.mark.skipif(
    not config.DB_PATH.exists(), reason="database not built yet: run python -m recipebot.build_db"
)

# total records across the three files, from the Step 2 EDA run
TOTAL_RAW_FROM_EDA = 125_164


@pytest.fixture(scope="module")
def con():
    connection = duckdb.connect(str(config.DB_PATH), read_only=True)
    yield connection
    connection.close()


def test_row_idx_is_contiguous_and_unique(con):
    n, lo, hi, distinct = con.execute(
        "SELECT count(*), min(row_idx), max(row_idx), count(DISTINCT row_idx) FROM recipes"
    ).fetchone()
    assert lo == 0 and hi == n - 1 and distinct == n


def test_ids_are_unique_and_prefixed(con):
    n, distinct = con.execute(
        "SELECT count(*), count(DISTINCT id) FROM recipes").fetchone()
    assert n == distinct
    bad = con.execute(
        "SELECT count(*) FROM recipes WHERE source NOT IN ('ar','epi','fn')").fetchone()[0]
    assert bad == 0


def test_usable_plus_excluded_equals_raw_total(con):
    usable = con.execute("SELECT count(*) FROM recipes").fetchone()[0]
    excluded = con.execute(
        "SELECT count(*) FROM recipes_excluded").fetchone()[0]
    assert usable + excluded == TOTAL_RAW_FROM_EDA


def test_no_advertisement_in_cleaned_ingredients(con):
    n = con.execute(
        "SELECT count(*) FROM (SELECT unnest(ingredients_clean) AS line FROM recipes) "
        "WHERE upper(line) LIKE '%ADVERTISEMENT%'"
    ).fetchone()[0]
    assert n == 0


def test_empty_instruction_flag_is_consistent(con):
    n = con.execute(
        "SELECT count(*) FROM recipes WHERE instructions_empty != (trim(instructions_clean) = '')"
    ).fetchone()[0]
    assert n == 0


def test_excluded_reasons_are_known(con):
    found = {r[0] for r in con.execute(
        "SELECT DISTINCT reason FROM recipes_excluded").fetchall()}
    assert found <= set(ALL_REASONS)
