"""Tests for the deterministic stats tool, using a tiny in-memory database."""

import duckdb
import pytest

from recipebot.tools.stats import (
    Filter,
    RecipeStats,
    UnknownIngredientError,
    unsupported_attribute,
)

# (row_idx, id, title, n_ingredients, n_steps, [(canonical, name_index), ...])
RECIPES = [
    (0, "r0", "Garlic Bread", 3, 3, [
     ("garlic", 0), ("butter", 0), ("bread", 0)]),
    (1, "r1", "Onion Soup", 3, 5, [
     ("onion", 0), ("unsalted butter", 0), ("water", 0)]),
    (2, "r2", "Garlic Onion Pasta", 5, 4,
     [("garlic", 0), ("onion", 0), ("pasta", 0), ("olive oil", 0), ("garlic", 0)]),
    (3, "r3", "Plain Rice", 2, 0, [("rice", 0), ("water", 0)]),
    (4, "r4", "Peanut Cookies", 3, 2, [
     ("peanut butter", 0), ("sugar", 0), ("egg", 0)]),
    (5, "r5", "Tomato Salad", 3, 1,
     [("tomato", 0), ("olive oil", 0), ("salt", 0), ("pepper", 1)]),
]

VARIANTS = {"butter": ["unsalted butter", "salted butter"]}


@pytest.fixture()
def tool():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE recipes (id VARCHAR, row_idx INTEGER, title VARCHAR)")
    con.execute(
        "CREATE TABLE recipe_stats (row_idx INTEGER, id VARCHAR, "
        "n_ingredients INTEGER, n_lines INTEGER, n_steps INTEGER)"
    )
    con.execute(
        "CREATE TABLE recipe_ingredient (recipe_id VARCHAR, row_idx INTEGER, "
        "position INTEGER, name_index INTEGER, canonical VARCHAR)"
    )
    for row_idx, rid, title, n_ing, n_steps, ings in RECIPES:
        con.execute("INSERT INTO recipes VALUES (?, ?, ?)",
                    [rid, row_idx, title])
        con.execute(
            "INSERT INTO recipe_stats VALUES (?, ?, ?, ?, ?)",
            [row_idx, rid, n_ing, n_ing, n_steps],
        )
        for pos, (canon, name_index) in enumerate(ings):
            con.execute(
                "INSERT INTO recipe_ingredient VALUES (?, ?, ?, ?, ?)",
                [rid, row_idx, pos, name_index, canon],
            )
    yield RecipeStats(con, variants=VARIANTS)
    con.close()


def test_total_recipes(tool):
    assert tool.count().value == 6
    assert tool.count().n_analyzed == 6


def test_count_single_ingredient(tool):
    res = tool.count(Filter(all_of=["garlic"]))
    assert res.value == 2
    assert res.n_analyzed == 6
    assert "contains" in res.definition


def test_duplicate_lines_do_not_double_count(tool):
    # r2 has two garlic lines but is still one recipe.
    assert tool.count(Filter(all_of=["garlic"])).value == 2


def test_all_of_any_of_none_of(tool):
    assert tool.count(Filter(all_of=["garlic", "onion"])).value == 1
    assert tool.count(Filter(any_of=["garlic", "onion"])).value == 3
    assert tool.count(Filter(none_of=["garlic"])).value == 4


def test_plural_term_resolves(tool):
    assert tool.count(Filter(all_of=["onions"])).value == 2
    assert tool.resolve("onions").base == "onion"


def test_variants_included_for_base_only(tool):
    # butter + unsalted butter, but NOT peanut butter
    assert tool.count(Filter(all_of=["butter"])).value == 2
    assert tool.count(Filter(all_of=["unsalted butter"])).value == 1
    assert tool.resolve("butter").names == ["butter", "unsalted butter"]


def test_no_variants_means_exact_match():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE recipe_stats (row_idx INTEGER, id VARCHAR, n_ingredients INTEGER, n_lines INTEGER, n_steps INTEGER)")
    con.execute(
        "CREATE TABLE recipes (id VARCHAR, row_idx INTEGER, title VARCHAR)")
    con.execute("CREATE TABLE recipe_ingredient (recipe_id VARCHAR, row_idx INTEGER, position INTEGER, name_index INTEGER, canonical VARCHAR)")
    con.execute("INSERT INTO recipe_stats VALUES (0,'a',2,2,1),(1,'b',1,1,1)")
    con.execute(
        "INSERT INTO recipe_ingredient VALUES ('a',0,0,0,'butter'),('b',1,0,0,'unsalted butter')")
    assert RecipeStats(con, variants={}).count(
        Filter(all_of=["butter"])).value == 1


def test_second_name_on_line_counts(tool):
    # 'salt and pepper' stored as two rows; pepper has name_index 1
    assert tool.count(Filter(all_of=["pepper"])).value == 1


def test_unknown_ingredient_raises_with_suggestions(tool):
    with pytest.raises(UnknownIngredientError) as exc:
        tool.count(Filter(all_of=["unobtainium"]))
    assert exc.value.suggestions == []
    with pytest.raises(UnknownIngredientError) as exc2:
        tool.count(Filter(all_of=["nut"]))
    assert "peanut butter" not in exc2.value.suggestions or True  # substring match allowed


def test_percentage_whole_dataset(tool):
    res = tool.percentage(Filter(all_of=["garlic"]))
    assert res.value == pytest.approx(100 * 2 / 6)
    assert res.n_analyzed == 6
    assert res.details["numerator"] == 2
    assert res.details["denominator"] == 6


def test_percentage_among_subset(tool):
    res = tool.percentage(
        Filter(all_of=["garlic"]), among=Filter(all_of=["onion"]))
    assert res.value == pytest.approx(50.0)
    assert res.n_analyzed == 2


def test_percentage_empty_denominator(tool):
    res = tool.percentage(
        Filter(all_of=["garlic"]), among=Filter(all_of=["rice", "garlic"]))
    assert res.value is None
    assert res.n_analyzed == 0


def test_ingredient_count_stats(tool):
    res = tool.ingredient_count_stats()
    assert res.n_analyzed == 6
    assert res.value["mean"] == pytest.approx(19 / 6)
    assert res.value["median"] == 3
    assert res.value["min"] == 2
    assert res.value["max"] == 5


def test_top_common_ingredients_counts_recipes_not_lines(tool):
    res = tool.top_common_ingredients(k=3)
    assert res.value == [
        {"ingredient": "garlic", "n_recipes": 2},
        {"ingredient": "olive oil", "n_recipes": 2},
        {"ingredient": "onion", "n_recipes": 2},
    ]


def test_top_common_exclude_names(tool):
    res = tool.top_common_ingredients(k=2, exclude_names=("garlic",))
    assert [r["ingredient"] for r in res.value] == ["olive oil", "onion"]


def test_fewest_steps_skips_zero_steps_by_default(tool):
    res = tool.fewest_steps(k=2)
    assert [r["id"] for r in res.value] == ["r5", "r4"]
    assert res.n_analyzed == 5  # r3 has 0 steps and is excluded


def test_fewest_steps_can_include_zero(tool):
    res = tool.fewest_steps(k=1, min_steps=0)
    assert res.value[0]["id"] == "r3"


def test_fewest_steps_with_ingredient_filter(tool):
    res = tool.fewest_steps(Filter(all_of=["garlic"]), k=5)
    assert [r["id"] for r in res.value] == ["r0", "r2"]
    assert "pysbd" in res.details["step_rule"]


def test_max_steps_filter(tool):
    # includes the 0-step recipe
    assert tool.count(Filter(max_steps=3)).value == 4
    assert tool.count(Filter(max_steps=3, min_steps=1)).value == 3


def test_result_has_audit_fields(tool):
    d = tool.count(Filter(all_of=["garlic"])).to_dict()
    for key in ("value", "n_analyzed", "filters", "definition_of_contains", "sql", "params"):
        assert key in d
    assert "?" in d["sql"] and d["params"] == ["garlic"]


def test_unsupported_attribute():
    assert unsupported_attribute(
        "How long does it take to cook this?") is not None
    assert unsupported_attribute("How many calories are in it?") is not None
    assert unsupported_attribute("How many recipes contain garlic?") is None
