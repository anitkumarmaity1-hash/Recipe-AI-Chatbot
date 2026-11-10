"""Tests for the adapted recipe builder and its validator (Step 12, Task 3).

Uses the synthetic database of test_substitution.py (banana bread, egg replaced). No network,
no real data, no model. Expected values are worked out by hand in the comments.
"""

import dataclasses

import numpy as np
import pytest
from test_substitution import (
    DAIRY,
    N,
    ROLES,
    STAPLES,
    VARIANTS,
    make_con,
)

from recipebot.normalization.allergens import AllergenMatcher
from recipebot.retrieval.masks import Constraints, build_sql_mask
from recipebot.tools.adaptation import (
    AdaptedRecipe,
    _line_is_clean,
    adapt,
    choose_candidate,
    form_pattern,
    validate_adaptation,
)
from recipebot.tools.stats import RecipeStats
from recipebot.tools.substitution import SubstitutionMiner

MATCHER = AllergenMatcher(DAIRY)
INSTRUCTIONS = ("Beat the eggs until fluffy. Fold in the flour. "
                "Eggs make it rise. Bake the eggplant slices. Serve egg-free guests first.")


@pytest.fixture()
def setup():
    con = make_con()
    con.execute(
        "UPDATE recipes SET instructions_clean = ? WHERE id = 'a:T'", [INSTRUCTIONS])
    stats = RecipeStats(con, variants=VARIANTS)
    miner = SubstitutionMiner(
        con, stats, staples=STAPLES, roles=ROLES, allergen_matcher=MATCHER)

    def mine(ingredient="egg", constraints=None, allowed=None):
        constraints = constraints or Constraints()
        mask, sql, _ = build_sql_mask(stats, N, constraints)
        if allowed is not None:
            mask &= allowed
        return miner.mine("a:T", ingredient, constraints, mask, sql), constraints

    yield mine
    con.close()


def built(setup):
    ev, constraints = setup()
    cand = choose_candidate(ev)
    return ev, cand, adapt(ev, cand, constraints, MATCHER), constraints


# ---- the form pattern ------------------------------------------------------------------
def test_form_pattern_matches_whole_words_and_plurals_only():
    pat = form_pattern(["egg"])
    assert pat.search("Beat the Eggs") and pat.search("one egg.")
    assert not pat.search("eggplant") and not pat.search(
        "egg-free") and not pat.search("veggie")


def test_form_pattern_prefers_the_longest_form_and_matches_nothing_when_empty():
    assert form_pattern(["butter", "unsalted butter"]).sub(
        "X", "melt unsalted butter") == "melt X"
    assert not form_pattern([]).search("anything")


# ---- choosing and building ------------------------------------------------------------------
def test_the_best_supported_candidate_is_chosen(setup):
    ev, _ = setup()
    # direct, 2 same-dish recipes
    assert choose_candidate(ev).name == "applesauce"


def test_no_candidate_is_chosen_when_the_evidence_is_insufficient(setup):
    ev, _ = setup(constraints=Constraints(exclude_allergens=("dairy",)),
                  allowed=np.array([not any(MATCHER.matches(f"1 cup {n}", "dairy") for n in names)
                                    for *_, names in __import__("test_substitution").RECIPES]))
    assert ev.status == "insufficient_evidence" and choose_candidate(
        ev) is None


def test_only_the_lines_with_the_ingredient_change(setup):
    ev, cand, adapted, _ = built(setup)
    original = ev.original["ingredient_lines"]
    assert [c["position"] for c in adapted.changed_lines] == [5]
    assert adapted.changed_lines[0]["original"] == "1 cup egg"
    assert adapted.ingredient_lines[5] == "applesauce (amount not verified from the dataset)"
    assert adapted.changed_lines[0]["reference_id"] == "a:W1"
    assert adapted.changed_lines[0]["reference_line"] == "1 cup applesauce"
    assert adapted.ingredient_lines[:5] == original[:5]
    assert adapted.ingredient_lines[6:] == original[6:]
    assert adapted.supporting_ids == ["a:W1", "a:W2", "a:W5"]


def test_steps_are_a_word_swap_that_keeps_capitals_and_skips_other_words(setup):
    _, _, adapted, _ = built(setup)
    assert adapted.steps == [
        "Beat the applesauce until fluffy.", "Fold in the flour.", "Applesauce make it rise.",
        "Bake the eggplant slices.", "Serve egg-free guests first."]
    assert [c["position"] for c in adapted.step_changes] == [0, 2]
    assert adapted.step_changes[0]["original"] == "Beat the eggs until fluffy."
    assert adapted.original_steps[0] == "Beat the eggs until fluffy."


def test_the_original_data_is_never_modified(setup):
    ev, _, adapted, _ = built(setup)
    before = list(ev.original["ingredient_lines"])
    adapt(ev, choose_candidate(ev), Constraints(), MATCHER)
    assert ev.original["ingredient_lines"] == before
    assert adapted.ingredient_lines is not ev.original["ingredient_lines"]


def test_building_twice_gives_the_same_result(setup):
    ev, cand, a, c = built(setup)
    assert adapt(ev, cand, c, MATCHER).to_dict() == a.to_dict()


def test_a_reference_line_with_an_excluded_allergen_is_not_used():
    assert _line_is_clean("1 cup applesauce", ["egg"], Constraints(), MATCHER)
    assert not _line_is_clean("1 cup yogurt", ["egg"], Constraints(
        exclude_allergens=("dairy",)), MATCHER)
    assert not _line_is_clean("1 cup egg", ["egg"], Constraints(), MATCHER)
    assert not _line_is_clean(
        "1 cup walnut", ["egg"], Constraints(exclude=("walnut",)), MATCHER)


def test_an_unchanged_line_that_still_names_the_ingredient_is_a_warning(setup):
    ev, cand, _, c = built(setup)
    ev.original["ingredient_lines"][0] = "1 egg wash for the top"
    adapted = adapt(ev, cand, c, MATCHER)
    assert any("line 1 still mentions egg" in w for w in adapted.warnings)


# ---- the validator --------------------------------------------------------------------------------
def test_a_correct_adaptation_passes(setup):
    ev, _, adapted, c = built(setup)
    assert validate_adaptation(adapted, ev, c, MATCHER) == []


def test_validator_catches_an_altered_unchanged_line(setup):
    ev, _, adapted, c = built(setup)
    adapted.ingredient_lines[0] = "2 cups sugar"
    assert any("line 1 differs" in p for p in validate_adaptation(
        adapted, ev, c, MATCHER))


def test_validator_catches_the_replaced_ingredient_left_in_a_step_or_line(setup):
    ev, _, adapted, c = built(setup)
    adapted.steps[0] = "Beat the eggs."
    adapted.ingredient_lines[5] = "1 cup egg"
    problems = validate_adaptation(adapted, ev, c, MATCHER)
    assert any("step 1 still names egg" in p for p in problems)
    assert any("changed line 6 still names egg" in p for p in problems)


def test_validator_catches_an_excluded_ingredient_or_allergen_in_the_new_line(setup):
    ev, _, adapted, _ = built(setup)
    adapted.ingredient_lines[5] = "1 cup yogurt"
    problems = validate_adaptation(adapted, ev, Constraints(
        exclude_allergens=("dairy",)), MATCHER)
    assert any("contains dairy" in p for p in problems)
    problems = validate_adaptation(
        adapted, ev, Constraints(exclude=("yogurt",)), MATCHER)
    assert any("excluded ingredient" in p for p in problems)


def test_validator_checks_unchanged_ingredient_lines_for_allergen_conflicts(setup):
    ev, _, adapted, _ = built(setup)
    # The original bread still contains butter outside the replaced-egg line.
    problems = validate_adaptation(
        adapted, ev, Constraints(exclude_allergens=("dairy",)), MATCHER)
    assert any("contains dairy" in p for p in problems)
    assert not any("ADAPTED RECIPE" in p for p in problems)


def test_validator_checks_every_line_for_explicit_ingredient_exclusions(setup):
    ev, _, adapted, _ = built(setup)
    problems = validate_adaptation(
        adapted, ev, Constraints(exclude=("butter",)), MATCHER)
    assert any("ingredient line 5 contains an excluded ingredient" in p for p in problems)


def test_validator_rejects_egg_white_as_an_egg_free_substitute(setup):
    ev, candidate, _, _ = built(setup)
    egg_white = dataclasses.replace(candidate, name="egg white")
    ev.candidates = [egg_white]
    egg_matcher = AllergenMatcher({"egg": {"include": ["egg", "egg white"], "exceptions": []}})
    adapted = adapt(ev, egg_white, Constraints(exclude_allergens=("egg",)), egg_matcher)
    problems = validate_adaptation(
        adapted, ev, Constraints(exclude_allergens=("egg",)), egg_matcher)
    assert any("substitute 'egg white' belongs to excluded allergen egg" in p
               for p in problems)


def test_validator_checks_instruction_steps_for_excluded_ingredients(setup):
    ev, _, adapted, _ = built(setup)
    adapted.steps[0] = "Stir in butter and bake."
    problems = validate_adaptation(
        adapted, ev, Constraints(exclude=("butter",)), MATCHER)
    assert any("step 1 mentions an excluded ingredient" in p for p in problems)


def test_validator_refuses_to_check_allergens_without_a_matcher(setup):
    ev, _, adapted, _ = built(setup)
    problems = validate_adaptation(
        adapted, ev, Constraints(exclude_allergens=("dairy",)), None)
    assert any("allergen matcher is required" in p for p in problems)


def test_validator_catches_a_substitute_without_dataset_evidence(setup):
    ev, _, adapted, c = built(setup)
    # knowledge only, level none
    bad = dataclasses.replace(adapted, substitute="tofu")
    assert any("no dataset evidence" in p for p in validate_adaptation(
        bad, ev, c, MATCHER))
    ghost = dataclasses.replace(adapted, substitute="unicorn")
    assert any("not an evidence candidate" in p for p in validate_adaptation(
        ghost, ev, c, MATCHER))


def test_validator_catches_a_made_up_supporting_id(setup):
    ev, _, adapted, c = built(setup)
    adapted.supporting_ids.append("a:E1")
    assert any("a:E1 is not cited" in p for p in validate_adaptation(
        adapted, ev, c, MATCHER))


def test_validator_catches_a_wrong_set_of_changed_lines(setup):
    ev, _, adapted, c = built(setup)
    adapted.changed_lines.clear()
    problems = validate_adaptation(adapted, ev, c, MATCHER)
    assert any("differ from the lines that contain" in p for p in problems)


def test_a_substitute_whose_name_contains_the_old_word_is_not_flagged_for_it(setup):
    ev, cand, _, c = built(setup)
    renamed = dataclasses.replace(cand, name="egg replacer")
    ev.candidates = [renamed]
    adapted = adapt(ev, renamed, c, MATCHER)
    assert validate_adaptation(adapted, ev, c, MATCHER) == []
    assert isinstance(adapted, AdaptedRecipe)
