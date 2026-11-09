"""Tests for substitution evidence mining (Step 11, Task 3).

Tiny synthetic database, no network, no real data, no model. The numbers in the comments
are worked out by hand from RECIPES below, so the logic is checked and not just repeated.

The story: the original is "Banana Bread" (a:T) and the user wants to replace the egg.
  * a:W1..a:W7 are related recipes WITHOUT egg and with steps (the evidence pool)
  * a:W8 is also eggless but has 0 steps (never cited)
  * a:E1..a:E5 are related recipes WITH egg (the baseline)
Core ingredients of a:T (egg and the staple salt left out):
  {banana, flour, sugar, baking soda, butter}  = 5 names
Similarity is Jaccard = shared / (5 + core of the other recipe - shared).
"""

import json

import duckdb
import numpy as np
import pytest

from recipebot.normalization.allergens import AllergenMatcher
from recipebot.retrieval.masks import Constraints, build_sql_mask
from recipebot.tools import substitution
from recipebot.tools.stats import RecipeStats, UnknownIngredientError
from recipebot.tools.substitution import (
    EvidenceRecipe,
    Roles,
    SubstitutionError,
    SubstitutionMiner,
    SubstitutionSettings,
    check_taxonomy,
    format_text,
    load_roles,
)

VARIANTS = {"butter": ["unsalted butter"]}
STAPLES = ["salt", "water", "pepper"]
BASE_BREAD = ["banana", "flour", "sugar", "baking soda", "butter"]

# row_idx, id, title, steps, canonical names (one line each)
RECIPES = [
    (0, "a:T", "Banana Bread", 8, BASE_BREAD + ["egg", "salt"]),
    (1, "a:W1", "Eggless Banana Bread", 6, BASE_BREAD +
     ["applesauce", "salt"]),      # sim 5/6, direct
    (2, "a:W2", "Vegan Banana Bread", 7,
     # sim 4/7, direct
     ["banana", "flour", "sugar", "baking soda", "vegetable oil", "applesauce"]),
    (3, "a:W3", "Banana Yogurt Muffins", 5, BASE_BREAD +
     ["yogurt"]),                 # sim 5/6, direct
    (4, "a:W4", "Yogurt Banana Cake", 6, BASE_BREAD +
     ["yogurt", "vanilla extract"]),  # sim 5/7, direct
    (5, "a:W5", "Pumpkin Loaf", 6,
     # sim 4/7, indirect
     ["flour", "sugar", "baking soda", "butter", "pumpkin puree", "applesauce"]),
    (6, "a:W6", "Walnut Cake", 4, [
     "flour", "sugar", "baking soda", "butter", "walnut"]),  # 4/6, indirect
    (7, "a:W7", "Nut Cake", 4, [
     "flour", "sugar", "baking soda", "butter", "walnut"]),     # 4/6, indirect
    (8, "a:W8", "Eggless Banana Bread No Steps", 0,
     BASE_BREAD + ["applesauce"]),     # 0 steps: never used
    (9, "a:E1", "Banana Bread", 8, BASE_BREAD + ["egg"]),
    (10, "a:E2", "Banana Bread", 8, BASE_BREAD + ["egg"]),
    (11, "a:E3", "Banana Bread", 8, BASE_BREAD + ["egg"]),
    (12, "a:E4", "Banana Bread", 8, BASE_BREAD + ["egg", "vanilla extract"]),
    (13, "a:E5", "Banana Bread", 8, BASE_BREAD +
     ["egg", "vanilla extract", "walnut"]),
    (14, "a:U", "Tofu Stir Fry", 5, [
     "tofu", "soy sauce", "rice"]),                   # unrelated
    # nothing similar
    (15, "a:S", "Saffron Rice", 5, ["rice", "saffron", "onion", "salt"]),
    (16, "a:O", "Oatmeal Cookies", 4,
     ["unsalted butter", "oats", "raisin", "cinnamon", "nutmeg", "egg", "salt"]),
    # only egg + staples
    (17, "a:Z", "Boiled Egg", 3, ["egg", "salt", "water"]),
]
N = len(RECIPES)

ROLES = Roles(
    roles={"egg": ["binding", "leavening", "structure", "moisture", "richness"],
           "applesauce": ["moisture", "sweetness", "binding"],
           "yogurt": ["moisture", "acid", "tenderness", "richness"],
           "tofu": ["binding", "structure", "moisture"],
           "butter": ["fat", "richness", "flavor", "tenderness"]},
    substitutes={"egg": ["applesauce", "yogurt", "tofu", "ground flaxseed"]},
    removal_effects={"egg": "Eggs bind and help the mixture rise."},
)
DAIRY = {"dairy": {"include": ["butter", "yogurt", "milk"], "exceptions": []}}


def make_con(recipes=None):
    base_of = {v: b for b, vs in VARIANTS.items() for v in vs}
    con = duckdb.connect()
    con.execute("CREATE TABLE recipes (id VARCHAR, row_idx INTEGER, title VARCHAR, source VARCHAR, "
                "ingredients_clean VARCHAR[], instructions_clean VARCHAR)")
    con.execute(
        "CREATE TABLE recipe_stats (row_idx INTEGER, id VARCHAR, n_steps INTEGER)")
    con.execute("CREATE TABLE recipe_ingredient (recipe_id VARCHAR, row_idx INTEGER, position INTEGER, "
                "name_index INTEGER, raw_line VARCHAR, canonical VARCHAR, canonical_base VARCHAR, "
                "alternatives VARCHAR[])")
    for row_idx, rid, title, steps, names in (recipes or RECIPES):
        lines = [f"1 cup {name}" for name in names]
        con.execute("INSERT INTO recipes VALUES (?, ?, ?, 'a', ?, ?)",
                    [rid, row_idx, title, lines, "Mix. Bake." if steps else ""])
        con.execute("INSERT INTO recipe_stats VALUES (?, ?, ?)",
                    [row_idx, rid, steps])
        for pos, name in enumerate(names):
            con.execute("INSERT INTO recipe_ingredient VALUES (?, ?, ?, 0, ?, ?, ?, [])",
                        [rid, row_idx, pos, lines[pos], name, base_of.get(name, name)])
    return con


@pytest.fixture()
def miner():
    con = make_con()
    yield SubstitutionMiner(con, RecipeStats(con, variants=VARIANTS), staples=STAPLES, roles=ROLES,
                            allergen_matcher=AllergenMatcher(DAIRY),
                            settings=SubstitutionSettings())
    con.close()


def run(miner, recipe="a:T", ingredient="egg", constraints=None, allowed=None, settings=None):
    """Mine with the mask built from the constraints, like the real application does."""
    constraints = constraints or Constraints()
    if settings:
        miner.settings = settings
    mask, sql, _ = build_sql_mask(miner.stats, N, constraints)
    if allowed is not None:
        mask &= allowed
    return miner.mine(recipe, ingredient, constraints, mask, sql)


def names(res):
    return [c.name for c in res.candidates]


def cand(res, name):
    return next(c for c in res.candidates if c.name == name)


def dairy_free_mask():
    """What the real allergen-flags cache provides: False where a line mentions dairy."""
    matcher = AllergenMatcher(DAIRY)
    return np.array([not any(matcher.matches(f"1 cup {n}", "dairy") for n in names_)
                     for _, _, _, _, names_ in RECIPES])


# ---- the main story ---------------------------------------------------------------------
def test_egg_in_banana_bread_finds_applesauce_and_yogurt(miner):
    res = run(miner)
    assert res.status == "ok"
    assert names(res) == ["applesauce", "yogurt", "tofu", "ground flaxseed"]
    assert [c.level for c in res.candidates] == [
        "direct", "direct", "none", "none"]
    assert [c.source for c in res.candidates] == [
        "both", "both", "knowledge", "knowledge"]


def test_group_sizes_are_stated_with_their_denominators(miner):
    p = run(miner).pools
    # 5 related recipes with egg (a:E1..E5); 8 without (a:W1..W8), 7 of them with steps
    assert (p["n_related_with"], p["n_related_without"],
            p["n_without_allowed"]) == (5, 8, 7)
    assert (p["n_with_used"], p["n_without_used"]) == (5, 7)
    # W1-W4 same dish family; W5-W7 related only
    assert (p["n_direct"], p["n_indirect"]) == (4, 3)
    assert p["pool_cut"] is False and p["n_recipes_total"] == N


def test_applesauce_numbers_match_the_hand_calculation(miner):
    c = cand(run(miner), "applesauce")
    # W1, W2 (direct) and W5 (indirect)
    assert (c.n_support, c.n_direct) == (3, 2)
    assert c.rate_without == pytest.approx(3 / 7)
    # no recipe with egg uses it
    assert c.rate_with == pytest.approx(0.0)
    assert c.enrichment == pytest.approx(3 / 7)
    assert c.shared_roles == ["binding", "moisture"]
    assert c.in_vocabulary is True


def test_cited_recipes_are_direct_first_then_most_similar_and_show_their_lines(miner):
    c = cand(run(miner), "applesauce")
    assert [e.id for e in c.evidence] == ["a:W1", "a:W2", "a:W5"]
    assert [e.tier for e in c.evidence] == ["direct", "direct", "indirect"]
    assert c.evidence[0].similarity == pytest.approx(5 / 6)
    assert c.evidence[1].similarity == pytest.approx(4 / 7)
    assert c.evidence[0].lines == ["1 cup applesauce"]
    assert c.evidence[0].n_steps == 6


def test_a_recipe_without_steps_is_never_cited(miner):
    res = run(miner)
    cited = {e.id for c in res.candidates for e in c.evidence}
    assert "a:W8" not in cited
    assert cited <= {"a:W1", "a:W2", "a:W3", "a:W4", "a:W5"}


def test_knowledge_only_substitutes_have_no_evidence_and_say_so(miner):
    res = run(miner)
    tofu, flax = cand(res, "tofu"), cand(res, "ground flaxseed")
    assert (tofu.level, tofu.n_support, tofu.evidence,
            tofu.in_vocabulary) == ("none", 0, [], True)
    assert (flax.level, flax.in_vocabulary) == (
        "none", False)      # not an ingredient in the dataset


def test_a_candidate_with_no_shared_role_is_filtered_and_counted(miner):
    res = run(miner)
    # used by 2 related recipes, but not an egg-like role
    assert "walnut" not in names(res)
    assert res.pools["n_filtered_no_shared_role"] == 1
    assert res.pools["role_filter_applied"] is True


def test_ingredients_already_in_the_recipe_are_not_offered(miner):
    res = run(miner)
    assert not {"banana", "flour", "sugar",
                "baking soda", "butter"} & set(names(res))
    assert res.pools["n_filtered_already_in_recipe"] == 5


def test_the_ingredient_itself_is_never_its_own_substitute(miner):
    assert "egg" not in names(run(miner))


def test_original_target_lines_role_and_effect_are_returned(miner):
    res = run(miner)
    assert res.original["id"] == "a:T" and res.original["n_steps"] == 8
    assert res.target["base"] == "egg"
    assert res.target["lines"] == [{"position": 5, "line": "1 cup egg"}]
    assert res.role["known"] is True and "binding" in res.role["roles"]
    assert res.role["removal_effect"].startswith("Eggs bind")
    assert "not evidence from the dataset" in res.role["source"]


def test_plural_and_case_in_the_users_words_are_accepted(miner):
    assert run(miner, ingredient="Eggs").target["base"] == "egg"


# ---- hard constraints --------------------------------------------------------------------
def test_an_excluded_ingredient_is_rejected_with_a_reason_and_its_recipes_are_not_used(miner):
    res = run(miner, constraints=Constraints(exclude=("applesauce",)))
    assert names(res) == ["yogurt", "tofu", "ground flaxseed"]
    assert any(r["name"] == "applesauce" and "excluded" in r["reason"]
               for r in res.rejected)
    cited = {e.id for c in res.candidates for e in c.evidence}
    # recipes with applesauce are masked out
    assert not cited & {"a:W1", "a:W2", "a:W5"}
    assert res.pools["n_without_allowed"] == 4               # W3, W4, W6, W7


def test_an_allergen_removes_unsafe_evidence_and_unsafe_substitutes(miner):
    res = run(miner, constraints=Constraints(
        exclude_allergens=("dairy",)), allowed=dairy_free_mask())
    # only a:W2 has no butter / yogurt, so nothing reaches the minimum support of 2
    assert res.pools["n_without_allowed"] == 1
    assert res.status == "insufficient_evidence" and res.note
    assert all(c.level == "none" for c in res.candidates)
    assert any(r["name"] == "yogurt" and "dairy" in r["reason"]
               for r in res.rejected)
    assert "yogurt" not in names(res)


def test_other_lines_that_still_break_a_constraint_are_reported(miner):
    res = run(miner, constraints=Constraints(
        exclude_allergens=("dairy",)), allowed=dairy_free_mask())
    assert [c["line"] for c in res.residual_conflicts] == ["1 cup butter"]
    assert "dairy" in res.residual_conflicts[0]["constraint"]


def test_no_residual_conflicts_without_constraints(miner):
    assert run(miner).residual_conflicts == []


def test_max_steps_limits_the_cited_recipes(miner):
    res = run(miner, constraints=Constraints(max_steps=5),
              settings=SubstitutionSettings(min_support=1, min_direct_support=1))
    cited = [e for c in res.candidates for e in c.evidence]
    assert cited and all(e.n_steps <= 5 for e in cited)
    assert miner.verify(res, Constraints(max_steps=5)) == []


def test_the_baseline_group_is_not_limited_by_the_constraints(miner):
    """With no dairy, every recipe WITH egg has butter, yet the baseline must stay intact."""
    res = run(miner, constraints=Constraints(
        exclude_allergens=("dairy",)), allowed=dairy_free_mask())
    assert res.pools["n_related_with"] == 5 and res.pools["n_with_used"] == 5
    assert cand(res, "applesauce").rate_with == pytest.approx(0.0)


def test_an_ingredient_that_is_just_as_common_with_the_original_is_not_a_replacement():
    mini = [
        (0, "m:T", "Cake", 5, ["flour", "sugar", "egg"]),
        (1, "m:W1", "Eggless Cake", 5, [
         "flour", "sugar", "vanilla extract", "applesauce"]),
        (2, "m:W2", "Eggless Cake", 5, [
         "flour", "sugar", "vanilla extract", "applesauce"]),
        (3, "m:E1", "Cake", 5, ["flour", "sugar", "egg", "vanilla extract"]),
        (4, "m:E2", "Cake", 5, ["flour", "sugar", "egg", "vanilla extract"]),
    ]
    roles = Roles(roles={"egg": ["binding", "flavor"], "applesauce": ["binding"],
                         "vanilla extract": ["flavor"]})
    con = make_con(mini)
    m = SubstitutionMiner(con, RecipeStats(
        con, variants=VARIANTS), roles=roles)
    res = m.mine("m:T", "egg")
    # vanilla: 2 of 2 related recipes without egg, but also 2 of 2 with egg -> enrichment 0
    assert [c.name for c in res.candidates] == ["applesauce"]
    assert res.candidates[0].enrichment == pytest.approx(1.0)
    con.close()


# ---- weak and missing evidence --------------------------------------------------------------
def test_raising_the_thresholds_turns_the_same_data_into_insufficient_evidence(miner):
    res = run(miner, settings=SubstitutionSettings(
        min_support=4, min_direct_support=3))
    assert res.status == "insufficient_evidence"
    assert all(c.level == "none" for c in res.candidates)
    # the count is still reported honestly
    assert cand(res, "applesauce").n_support == 3


def test_a_recipe_with_no_similar_recipes_gives_insufficient_evidence(miner):
    res = run(miner, recipe="a:S", ingredient="saffron")
    assert res.status == "insufficient_evidence"
    assert res.pools["n_without_allowed"] == 0
    assert res.role["known"] is False and res.pools["role_filter_applied"] is False


def test_a_recipe_with_only_the_ingredient_and_staples_cannot_find_neighbours(miner):
    # salt and water are staples
    res = run(miner, recipe="a:Z", ingredient="egg")
    assert res.status == "insufficient_evidence"
    assert res.pools["original_core_ingredients"] == []
    assert "no ingredients besides" in res.note


def test_the_core_ingredients_exclude_the_replaced_one_and_staples(miner):
    res = run(miner, recipe="a:S", ingredient="saffron")
    assert res.pools["original_core_ingredients"] == ["onion", "rice"]


def test_forms_of_an_ingredient_count_as_the_ingredient(miner):
    # the line says "unsalted butter"
    res = run(miner, recipe="a:O", ingredient="butter")
    assert res.target["base"] == "butter"
    assert "unsalted butter" in res.target["forms"]
    assert res.target["lines"] == [
        {"position": 0, "line": "1 cup unsalted butter"}]
    assert not {"butter", "unsalted butter"} & set(names(res))


# ---- errors are explicit, never silent ---------------------------------------------------------
def test_unknown_recipe_id_raises(miner):
    with pytest.raises(SubstitutionError, match="no recipe with the id"):
        run(miner, recipe="a:NOPE")


def test_an_ingredient_that_is_not_in_the_recipe_raises_and_lists_what_is(miner):
    with pytest.raises(SubstitutionError, match="not an ingredient of 'Banana Bread'") as err:
        run(miner, ingredient="walnut")
    assert "banana" in str(err.value)


def test_an_ingredient_outside_the_vocabulary_raises(miner):
    with pytest.raises(UnknownIngredientError):
        run(miner, ingredient="unicorn")


def test_a_short_mask_is_refused(miner):
    with pytest.raises(ValueError, match="mask is shorter"):
        miner.mine("a:T", "egg", Constraints(), np.ones(3, dtype=bool))


def test_allergens_without_a_matcher_are_refused_not_ignored():
    con = make_con()
    bare = SubstitutionMiner(con, RecipeStats(
        con, variants=VARIANTS), staples=STAPLES, roles=ROLES)
    mask = np.ones(N, dtype=bool)
    with pytest.raises(ValueError, match="allergen matcher"):
        bare.mine("a:T", "egg", Constraints(
            exclude_allergens=("dairy",)), mask)
    con.close()


# ---- the independent check and the output -------------------------------------------------------
def test_verify_passes_on_a_correct_result_and_catches_a_wrong_citation(miner):
    constraints = Constraints()
    res = run(miner)
    assert miner.verify(res, constraints) == []
    # tamper: cite a recipe that contains the egg for applesauce
    cand(res, "applesauce").evidence.append(EvidenceRecipe(
        row_idx=9, id="a:E1", title="Banana Bread", tier="direct", similarity=1.0, n_steps=8, lines=[]))
    problems = miner.verify(res, constraints)
    assert any("a:E1" in p and "ingredient being replaced" in p for p in problems)
    assert any("does not contain it" in p for p in problems)


def test_verify_catches_a_forbidden_substitute(miner):
    res = run(miner)
    problems = miner.verify(res, Constraints(exclude=("yogurt",)))
    assert any("'yogurt'" in p and "excluded" in p for p in problems)


def test_results_are_deterministic_and_json_serialisable(miner):
    a, b = run(miner).to_dict(), run(miner).to_dict()
    assert a == b
    # no numpy types leak into the result
    json.dumps(a)


def test_text_report_names_the_ids_and_the_denominators(miner):
    text = format_text(run(miner))
    assert "[a:W1]" in text and "evidence: DIRECT" in text
    assert "5 with egg, 8 without" in text
    assert "general knowledge" in text


# ---- the knowledge file ----------------------------------------------------------------------------
def test_check_taxonomy_reports_names_the_dataset_does_not_know(miner):
    report = "\n".join(check_taxonomy(
        miner.stats, ROLES, AllergenMatcher(DAIRY)))
    assert "'ground flaxseed' is NOT in the dataset vocabulary" in report
    assert "'yogurt' (for egg) is flagged as dairy" in report


def test_missing_roles_file_gives_empty_roles(tmp_path):
    roles = load_roles(tmp_path / "nope.yaml")
    assert roles.roles == {} and roles.substitutes == {}


def test_the_shipped_roles_file_is_valid():
    path = substitution.config.INGREDIENT_ROLES_PATH
    if not path.exists():
        pytest.skip("data/taxonomy/ingredient_roles.yaml is not present")
    roles = load_roles()
    assert roles.vocabulary and roles.roles and roles.substitutes and roles.removal_effects
    for name, role_list in roles.roles.items():
        assert name == name.lower() and role_list, name
        assert set(role_list) <= set(roles.vocabulary), f"{name}: {role_list}"
    for target, subs in roles.substitutes.items():
        assert target in roles.roles, f"substitutes key '{target}' has no roles entry"
        for sub in subs:
            assert sub in roles.roles, f"substitute '{sub}' (for {target}) has no roles entry"
            assert sub != target
    for name in roles.removal_effects:
        assert name in roles.roles, name
