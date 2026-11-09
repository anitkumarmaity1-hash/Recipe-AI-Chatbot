"""Tests for Step 10b: the two defects found in the live Step 10 run (handover 9.6).

1. A listed ingredient that an excluded ALLERGEN covers ("eggs" while "no egg" is active)
   must be dropped and reported, not shown as "Missing" in every result.
2. A new ingredient list that still contains the old one ("I also have rice") extends the
   same search: the step limit and the "must contain" list are kept.
Also: "1 step", not "1 steps".

No network, no real data. Uses the synthetic database of test_match.py.
"""

import pytest
from test_match import MAPPER, N, STAPLES, U, make_db

import duckdb

from recipebot.agent.composer import compose_stats, plural
from recipebot.agent.state import SessionState, ingredient_key
from recipebot.normalization.allergens import AllergenMatcher
from recipebot.normalization.ingredients import IngredientNormalizer
from recipebot.retrieval.masks import Constraints, build_sql_mask
from recipebot.tools.matching import RecipeMatcher
from recipebot.tools.stats import RecipeStats, StatsResult

TAXONOMY = {
    "egg": {"include": ["egg"], "exceptions": []},
    "dairy": {"include": ["milk", "butter", "cheese"],
              "exceptions": ["coconut milk", "peanut butter"]},
}
VARIANTS = {"butter": ["unsalted butter", "salted butter"]}


@pytest.fixture()
def matcher(tmp_path):
    con = duckdb.connect(str(make_db(tmp_path / "m.duckdb")), read_only=True)
    stats = RecipeStats(con, variants=VARIANTS)
    yield RecipeMatcher(con, stats, staples=STAPLES, normalizer=IngredientNormalizer({}),
                        allergen_matcher=AllergenMatcher(TAXONOMY))
    con.close()


def run(matcher, available, constraints, **kwargs):
    mask, sql, _ = build_sql_mask(matcher.stats, N, constraints)
    return matcher.match(available, constraints, mask, sql, k=20, **kwargs)


def ids(res):
    return [h.id for h in res.hits]


# ---- defect 1: allergen-covered ingredients are dropped and reported ----------------
def test_an_ingredient_covered_by_an_excluded_allergen_is_dropped_and_reported(matcher):
    res = run(matcher, ["egg", "onion", "tomato"],
              Constraints(exclude_allergens=("egg",)))
    assert res.terms == ["onion", "tomato"] and res.dropped == ["egg"]
    for hit in res.hits:
        # the "Missing" list no longer contains the egg the user cannot have
        assert "egg" not in hit.unused + hit.matched
        assert hit.coverage == pytest.approx(
            hit.n_matched / 2)   # denominator is 2, not 3
    assert matcher.verify(res) == []


def test_the_plural_the_user_typed_is_handled(matcher):
    res = run(matcher, ["Eggs", "onions"],
              Constraints(exclude_allergens=("egg",)))
    assert res.dropped == ["egg"] and res.terms == ["onion"]


def test_a_form_of_an_ingredient_is_dropped_too(matcher):
    # the user types "unsalted butter", the allergen is dairy: butter is dairy
    res = run(matcher, ["unsalted butter", "flour"],
              Constraints(exclude_allergens=("dairy",)))
    assert res.dropped == ["butter"] and res.terms == ["flour"]


def test_a_name_the_dataset_does_not_know_is_reported_not_dropped_as_an_allergen(matcher):
    # not in the fixture's vocabulary: reported as unknown, never silently dropped
    res = run(matcher, ["coconut milk", "flour"],
              Constraints(exclude_allergens=("dairy",)))
    assert res.dropped == [] and [u["term"]
                                  for u in res.unknown] == ["coconut milk"]


def test_an_ingredient_no_allergen_covers_is_kept(matcher):
    res = run(matcher, ["onion", "tomato"],
              Constraints(exclude_allergens=("egg",)))
    assert res.terms == ["onion", "tomato"] and res.dropped == []


def test_everything_dropped_gives_the_existing_note_and_no_hits(matcher):
    res = run(matcher, ["egg"], Constraints(exclude_allergens=("egg",)))
    assert res.hits == [] and res.terms == [] and res.dropped == ["egg"]
    assert "could be used" in res.note


def test_an_ingredient_exclusion_and_an_allergen_can_both_drop(matcher):
    res = run(matcher, ["egg", "onion", "tomato", "rice"],
              Constraints(exclude=("onion",), exclude_allergens=("egg",)))
    assert res.terms == ["tomato", "rice"] and res.dropped == ["egg", "onion"]


def test_the_matcher_passed_to_match_is_used_when_the_constructor_has_none(tmp_path):
    con = duckdb.connect(str(make_db(tmp_path / "m.duckdb")), read_only=True)
    bare = RecipeMatcher(con, RecipeStats(con, variants=VARIANTS), staples=STAPLES,
                         normalizer=IngredientNormalizer({}))
    res = run(bare, ["egg", "onion"], Constraints(exclude_allergens=("egg",)),
              allergen_matcher=AllergenMatcher(TAXONOMY))
    assert res.dropped == ["egg"]
    con.close()


def test_allergens_without_any_matcher_are_refused_not_ignored(tmp_path):
    con = duckdb.connect(str(make_db(tmp_path / "m.duckdb")), read_only=True)
    bare = RecipeMatcher(con, RecipeStats(con, variants=VARIANTS), staples=STAPLES,
                         normalizer=IngredientNormalizer({}))
    with pytest.raises(ValueError, match="allergen matcher"):
        run(bare, ["egg"], Constraints(exclude_allergens=("egg",)))
    con.close()


def test_without_allergens_no_matcher_is_needed(tmp_path):
    con = duckdb.connect(str(make_db(tmp_path / "m.duckdb")), read_only=True)
    bare = RecipeMatcher(con, RecipeStats(con, variants=VARIANTS), staples=STAPLES,
                         normalizer=IngredientNormalizer({}))
    assert run(bare, ["egg"], Constraints()).hits
    con.close()


# ---- defect 2: extending the ingredient list keeps the step limit ----------------------
def test_adding_an_ingredient_keeps_the_step_limit_and_the_must_contain_list():
    st = SessionState()
    st.apply(U("match", available=["eggs", "onions", "tomatoes"],
               max_steps=6, include=["cheese"], exclude=["dairy"]), MAPPER)
    changes = st.apply(
        U("match", available=["eggs", "onions", "tomatoes", "rice"]), MAPPER)
    assert st.available == ["eggs", "onions", "tomatoes", "rice"]
    assert st.max_steps == 6 and st.include == ["cheese"]
    assert st.exclude_allergens == ["dairy"]
    assert any("extended" in c for c in changes) and not any(
        "New search" in c for c in changes)


def test_a_new_step_limit_in_the_same_message_wins_and_new_includes_are_added():
    st = SessionState()
    st.apply(U("match", available=["egg"],
             max_steps=6, include=["cheese"]), MAPPER)
    st.apply(U("match", available=["egg", "rice"],
             max_steps=4, include=["milk"]), MAPPER)
    assert st.max_steps == 4 and st.include == ["cheese", "milk"]


def test_a_list_that_drops_an_old_ingredient_is_a_new_search():
    st = SessionState()
    st.apply(U("match", available=["egg", "onion"], max_steps=6), MAPPER)
    changes = st.apply(U("match", available=["egg", "rice"]), MAPPER)
    assert st.max_steps is None and any("New search" in c for c in changes)


def test_a_list_with_only_the_new_ingredient_is_a_new_search_and_says_so():
    st = SessionState()
    st.apply(U("match", available=["egg", "onion"], max_steps=6), MAPPER)
    changes = st.apply(U("match", available=["rice"]), MAPPER)
    assert st.available == ["rice"] and st.max_steps is None
    assert any("New search" in c and "step limit" in c for c in changes)


def test_the_first_list_after_a_text_search_still_starts_a_new_search():
    st = SessionState()
    st.apply(U("search", dish_query="soup", include=[
             "tomato"], max_steps=5), MAPPER)
    st.apply(U("match", available=["egg"]), MAPPER)
    assert st.include == [] and st.max_steps is None


def test_plural_and_case_differences_do_not_break_the_extension():
    st = SessionState()
    st.apply(U("match", available=["Tomatoes",
             "Berries", "Eggs"], max_steps=6), MAPPER)
    st.apply(U("match", available=["tomato", "berry", "egg", "rice"]), MAPPER)
    assert st.max_steps == 6


def test_exclusions_are_untouched_by_an_extension():
    st = SessionState()
    st.apply(U("match", available=["egg"], exclude=["dairy", "vegan"]), MAPPER)
    st.apply(U("match", available=["egg", "rice"]), MAPPER)
    assert st.exclude_allergens == ["dairy"] and st.unenforced == ["vegan"]


@pytest.mark.parametrize("raw, key", [
    ("Tomatoes", "tomato"), ("berries", "berry"), ("eggs", "egg"), ("Egg ", "egg"),
    ("  brown   rice", "brown rice"), ("glass", "glass"), ("peas", "pea"),
    ("gas", "gas"), ("potato", "potato"),
])
def test_ingredient_key(raw, key):
    assert ingredient_key(raw) == key


# ---- grammar --------------------------------------------------------------------------------
def test_plural_helper():
    assert (plural(0, "step"), plural(1, "step"), plural(2, "step")) == (
        "0 steps", "1 step", "2 steps")


def test_a_one_step_recipe_is_not_called_1_steps():
    res = StatsResult(
        name="fewest_steps", value=[{"id": "a:9", "title": "Salsa", "n_steps": 1}],
        n_analyzed=1, filters={"all_of": [], "any_of": [], "none_of": [], "max_steps": 1},
        definition="d", sql="", details={"step_rule": "rule"})
    text = compose_stats(res)
    assert "[a:9]  - 1 step" in text and "1 steps" not in text
    assert "at most 1 step" in text
