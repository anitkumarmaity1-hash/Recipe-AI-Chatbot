"""Tests for the session state and the output guard (Step 9). No database, no model."""

from types import SimpleNamespace

import pytest

from recipebot.agent.guard import check_reply
from recipebot.agent.state import SessionState
from recipebot.retrieval.masks import Constraints
from recipebot.schemas import Intent, StatType, Understanding
from recipebot.understanding.restrictions import RestrictionMapper

TERMS = {
    "allergen_phrases": {"dairy": ["dairy"], "eggs": ["egg"], "nuts": ["peanut", "tree_nut"]},
    "unsupported_phrases": ["vegan"],
}
MAPPER = RestrictionMapper(TERMS, known_allergens=[
                           "dairy", "egg", "peanut", "tree_nut"])


def u(intent, **slots):
    if "stat_type" in slots:
        slots["stat_type"] = StatType(slots["stat_type"])
    return Understanding(intent=Intent(intent), **slots)


def test_restriction_persists_across_searches():
    st = SessionState()
    st.apply(u("search", dish_query="penne pasta"), MAPPER)
    changes = st.apply(u("refine", exclude=["dairy"]), MAPPER)
    assert st.exclude_allergens == ["dairy"]
    assert "Added restriction: no dairy" in changes[0]
    st.apply(u("search", dish_query="banana bread"),
             MAPPER)       # a different dish
    assert st.exclude_allergens == [
        "dairy"]                       # still active
    assert st.last_query == "banana bread"


def test_allow_removes_a_restriction():
    st = SessionState()
    st.apply(u("refine", exclude=["dairy", "eggs"]), MAPPER)
    changes = st.apply(u("refine", allow=["dairy"]), MAPPER)
    assert st.exclude_allergens == ["egg"]
    assert changes == ["Removed restriction: dairy."]


def test_one_phrase_can_map_to_several_categories():
    st = SessionState()
    st.apply(u("refine", exclude=["nuts"]), MAPPER)
    assert st.exclude_allergens == ["peanut", "tree_nut"]


def test_ingredient_and_unenforced_restrictions_are_kept_separately():
    st = SessionState()
    changes = st.apply(u("refine", exclude=["mushrooms", "vegan"]), MAPPER)
    assert st.exclude_ingredients == ["mushrooms"]
    assert st.unenforced == ["vegan"]
    assert any("Cannot enforce: 'vegan'" in c for c in changes)
    st.apply(u("refine", exclude=["mushrooms"]),
             MAPPER)            # no duplicates
    assert st.exclude_ingredients == ["mushrooms"]


def test_new_search_resets_include_and_steps_but_not_exclusions():
    st = SessionState()
    st.apply(u("search", dish_query="soup", include=[
             "garlic"], max_steps=6, exclude=["dairy"]), MAPPER)
    assert st.include == ["garlic"] and st.max_steps == 6
    changes = st.apply(u("search", dish_query="cake"), MAPPER)
    assert st.include == [] and st.max_steps is None
    assert st.exclude_allergens == ["dairy"]
    assert any("New search" in c for c in changes)


def test_refine_adds_include_and_replaces_steps():
    st = SessionState()
    st.apply(u("search", dish_query="soup", include=[
             "garlic"], max_steps=6), MAPPER)
    st.apply(u("refine", include=["onion"], max_steps=4), MAPPER)
    assert st.include == ["garlic", "onion"] and st.max_steps == 4
    # no new steps given: keep 4
    st.apply(u("refine", exclude=["eggs"]), MAPPER)
    assert st.max_steps == 4


def test_stats_and_details_do_not_change_restrictions():
    st = SessionState()
    st.apply(u("refine", exclude=["dairy"]), MAPPER)
    assert st.apply(u("stats", stat_type="count", include=[
                    "garlic"], exclude=["eggs"]), MAPPER) == []
    assert st.apply(u("show_details", target_recipe_id="a:1"), MAPPER) == []
    assert st.exclude_allergens == ["dairy"] and st.include == []


def test_clear_filters_resets_everything_but_the_results():
    st = SessionState(last_results=[{"n": 1, "id": "a:1", "title": "X"}])
    st.apply(u("refine", exclude=["dairy", "vegan"], max_steps=5), MAPPER)
    assert st.apply(u("clear_filters"), MAPPER) == [
        "All restrictions cleared."]
    assert st.constraints().is_empty() and st.unenforced == []
    # results are kept
    assert st.last_results


def test_search_without_dish_uses_include_words_or_keeps_previous_query():
    st = SessionState()
    st.apply(u("search", include=["chickpeas", "garlic"]), MAPPER)
    assert st.last_query == "chickpeas garlic"
    st.apply(u("search"), MAPPER)
    assert st.last_query == "chickpeas garlic"


def test_constraints_and_prompt_state_shape():
    st = SessionState()
    st.apply(u("search", dish_query="soup", include=["garlic"], max_steps=6,
               exclude=["dairy", "mushrooms"]), MAPPER)
    st.set_results([SimpleNamespace(id="a:1", title="One"),
                   SimpleNamespace(id="a:2", title="Two")])
    assert st.constraints() == Constraints(include=("garlic",), exclude=("mushrooms",),
                                           exclude_allergens=("dairy",), max_steps=6)
    prompt = st.to_prompt_state()
    assert prompt["active_filters"] == {"include": ["garlic"], "exclude": ["dairy", "mushrooms"],
                                        "max_steps": 6}
    assert prompt["last_results"][1] == {"n": 2, "id": "a:2", "title": "Two"}
    assert prompt["active_recipe"] is None


# ---- output guard ------------------------------------------------------------
def test_guard_accepts_known_ids_and_numbers():
    text = "1. Garlic Bread  [a:1]\nEligible 5 of 6"
    assert check_reply(text, {"a:1"}, ["5", "6"]) == []


def test_guard_blocks_an_id_that_is_not_in_the_tool_output():
    problems = check_reply("Try [ar:made/up.id] and [a:1]", {"a:1"})
    assert problems == [
        "recipe id not in this turn's tool output: ar:made/up.id"]


def test_guard_blocks_a_missing_or_changed_number():
    problems = check_reply("About 5,000 recipes", set(), ["12,760"])
    assert problems == ["value from the tool output is missing: 12,760"]


@pytest.mark.parametrize("rid", ["ar:vStKVNF5/iKgm/fDEfygCO092InVTpy", "epi:D2lLtfmm2Br05Jy8UDxsv3vJryjgEEG",
                                 "fn:aKF1SeZn14NOzGeQsJgn5QAkLzL.5fu"])
def test_guard_handles_real_id_shapes(rid):
    assert check_reply(f"x  [{rid}]", {rid}) == []
    assert len(check_reply(f"x  [{rid}]", set())) == 1
