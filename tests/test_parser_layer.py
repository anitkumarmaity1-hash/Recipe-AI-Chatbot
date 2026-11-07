"""Step 4 tests (hybrid): ingredient-parser-nlp + rule layer, and the two-stage build.

The expected values below were observed with ingredient-parser-nlp 2.9.2.
Skipped automatically if the library is not installed.
"""
import duckdb
import pytest

pytest.importorskip("ingredient_parser")

from recipebot.build_db import build_database  # noqa: E402
from recipebot.build_normalized import build_parse_cache, build_recipe_tables  # noqa: E402
from recipebot.normalization.ingredients import IngredientNormalizer  # noqa: E402
from recipebot.normalization.parser_layer import (  # noqa: E402
    normalize_unit,
    parse_line,
    resolve_line,
    warmup,
)

NORMALIZER = IngredientNormalizer({"scallion": "green onion"})


@pytest.fixture(scope="module", autouse=True)
def _warm_up_parser():
    warmup()  # fails loudly if the NLTK tagger cannot be downloaded


def resolve(line):
    return resolve_line(line, parse_line(line), NORMALIZER)


@pytest.mark.parametrize(
    "line, canonicals, alternatives",
    [
        ("1 teaspoon garlic powder", ["garlic powder"], []),
        ("1 (13.5 ounce) can coconut milk", ["coconut milk"], []),
        ("3 large eggs", ["egg"], []),
        ("2 tbsp. butter or margarine", ["butter"], ["margarine"]),
        ("Salt and pepper to taste", ["salt", "pepper"], []),
        ("2 cups fresh basil leaves", ["basil leaf"], []),
        ("4 ripe tomatoes, chopped", ["tomato"], []),
        ("1 bunch scallions", ["green onion"], []),
        ("To taste", [], []),
    ],
)
def test_resolve_line(line, canonicals, alternatives):
    result = resolve(line)
    assert result.canonicals == canonicals
    assert result.alternatives == alternatives


def test_forms_stay_distinct():
    assert resolve("2 cloves garlic, minced").canonicals == ["garlic"]
    assert resolve("1 teaspoon garlic powder").canonicals == ["garlic powder"]
    assert resolve("1 cup coconut milk").canonicals != resolve(
        "1 cup milk").canonicals


def test_quantity_and_unit():
    parsed = parse_line("1/2 cup peanut butter")
    assert parsed.quantity == 0.5
    assert normalize_unit(parsed.unit) == "cup"
    assert parse_line("1 teaspoon garlic powder").quantity == 1.0


def test_preparation_and_comment():
    assert parse_line("1/2 medium onion, diced").preparation == "diced"
    assert parse_line("Salt and pepper to taste").comment == "to taste"


def test_odd_lines_do_not_crash():
    parsed = parse_line("")
    assert parsed.parse_ok is False
    assert resolve_line("", parsed, NORMALIZER).source == "none"
    assert parse_line("   ").parse_ok is False


@pytest.mark.parametrize(
    "unit, expected",
    [("cups", "cup"), ("tablespoons", "tablespoon"), ("pinches", "pinch"), ("ounces", "ounce"),
     ("", None), (None, None)],
)
def test_normalize_unit(unit, expected):
    assert normalize_unit(unit) == expected


def _tiny_raw():
    return {
        "ar": {
            "r1": {
                "title": "Pancakes",
                "ingredients": ["2 cups all-purpose flour ADVERTISEMENT", "3 large eggs ADVERTISEMENT", "To taste"],
                "instructions": "Mix the flour. Bake it.",
            },
            "r2": {"title": "Toast", "ingredients": ["2 slices bread"], "instructions": ""},
        }
    }


def test_two_stage_build_end_to_end(tmp_path):
    db_path = tmp_path / "tiny.duckdb"
    build_database(_tiny_raw(), db_path)

    first = build_parse_cache(db_path)
    assert first.newly_parsed == 4  # flour, eggs, "To taste", bread
    # cache makes Stage A incremental
    assert build_parse_cache(db_path).newly_parsed == 0

    stats = build_recipe_tables(db_path, NORMALIZER)
    assert stats.unparsed_count == 1  # "To taste"
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        assert con.execute(
            "SELECT count(*) FROM ingredient_parse").fetchone()[0] == 4
        assert con.execute(
            "SELECT canonical FROM recipe_ingredient WHERE recipe_id = 'ar:r1' ORDER BY position"
        ).fetchall() == [("all-purpose flour",), ("egg",)]
        assert con.execute(
            "SELECT quantity FROM recipe_ingredient WHERE recipe_id = 'ar:r1' AND canonical = 'all-purpose flour'"
        ).fetchone()[0] == 2.0
        assert con.execute(
            "SELECT n_ingredients, n_steps, n_lines FROM recipe_stats WHERE id = 'ar:r1'"
        ).fetchone() == (3, 2, 1)
        assert con.execute(
            "SELECT n_steps FROM recipe_stats WHERE id = 'ar:r2'").fetchone()[0] == 0
    finally:
        con.close()

    # Stage B must be safely repeatable
    build_recipe_tables(db_path, NORMALIZER)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        assert con.execute(
            "SELECT count(*) FROM recipe_stats").fetchone()[0] == 2
    finally:
        con.close()
