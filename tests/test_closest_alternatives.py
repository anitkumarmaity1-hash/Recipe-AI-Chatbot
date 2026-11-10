"""P2 (T2d): when nothing is eligible, the closest recipes that VIOLATE a constraint are shown,
clearly marked, and are never returned as results. Synthetic database, no network."""

import duckdb
import numpy as np
import pytest
from test_match import N, RECIPES, STAPLES, VARIANTS, make_db

from recipebot.agent.match_composer import compose_match
from recipebot.normalization.allergens import AllergenMatcher
from recipebot.normalization.ingredients import IngredientNormalizer
from recipebot.retrieval.masks import Constraints, build_sql_mask
from recipebot.tools.matching import RecipeMatcher
from recipebot.tools.stats import RecipeStats

TAXONOMY = {"dairy": {"include": [
    "milk", "butter", "cheese"], "exceptions": []}}


@pytest.fixture()
def matcher(tmp_path):
    path = make_db(tmp_path / "m.duckdb")
    con = duckdb.connect(str(path))
    con.execute("ALTER TABLE recipes ADD COLUMN ingredients_clean VARCHAR[]")
    for row_idx, _rid, _title, _steps, lines in RECIPES:
        con.execute("UPDATE recipes SET ingredients_clean = ? WHERE row_idx = ?",
                    [[f"1 cup {c}" for c, _ in lines], row_idx])
    con.close()
    con = duckdb.connect(str(path), read_only=True)
    yield RecipeMatcher(con, RecipeStats(con, variants=VARIANTS), staples=STAPLES,
                        normalizer=IngredientNormalizer({}), allergen_matcher=AllergenMatcher(TAXONOMY))
    con.close()


def run(matcher, available, constraints, mask=None):
    sql_mask, sql, _ = build_sql_mask(matcher.stats, N, constraints)
    return matcher.match(available, constraints, sql_mask if mask is None else mask, sql, k=5)


def test_a_step_limit_nothing_can_meet_gives_marked_alternatives_and_no_results(matcher):
    res = run(matcher, ["tomato"], Constraints(max_steps=1))
    assert res.hits == [] and res.n_eligible == 0
    assert {a.id for a in res.alternatives} == {"a:A", "a:C"}
    assert all(any("steps (your limit is 1)" in v for v in a.violations)
               for a in res.alternatives)
    assert matcher.verify(res) == []


def test_contradicting_include_and_exclude_name_the_broken_rule_per_recipe(matcher):
    res = run(matcher, ["rice"], Constraints(
        include=("peanut",), exclude=("peanut",)))
    by_id = {a.id: a.violations for a in res.alternatives}
    assert "contains peanut, which you excluded" in by_id["a:B"]
    assert "does not contain peanut, which you require" in by_id["a:C"]


def test_allergen_violations_quote_the_ingredient_line(matcher):
    nothing_allowed = np.zeros(N, dtype=bool)
    res = run(matcher, ["tomato"], Constraints(
        exclude_allergens=("dairy",)), mask=nothing_allowed)
    # a:A has no dairy, so it is not shown
    assert [a.id for a in res.alternatives] == ["a:C"]
    assert res.alternatives[0].violations == [
        'dairy (ingredient line: "1 cup cheese")']


def test_no_alternatives_when_a_recipe_is_eligible(matcher):
    res = run(matcher, ["tomato"], Constraints())
    assert res.hits and res.alternatives == []


def test_alternatives_never_appear_next_to_real_results(matcher):
    res = run(matcher, ["tomato"], Constraints(max_steps=1))
    res.hits = [res.alternatives[0]]
    assert any(
        "only allowed when no recipe is eligible" in p for p in matcher.verify(res))


def test_the_answer_marks_alternatives_as_not_eligible(matcher):
    text = compose_match(run(matcher, ["tomato"], Constraints(max_steps=1)))
    assert "NOT ELIGIBLE" in text and "VIOLATE a hard constraint" in text
    assert "VIOLATES: has 4 steps (your limit is 1)" in text and "Ranking:" not in text
    assert "nothing was relaxed" in text


def test_to_dict_is_json_ready(matcher):
    import json
    json.dumps(run(matcher, ["tomato"], Constraints(max_steps=1)).to_dict())
