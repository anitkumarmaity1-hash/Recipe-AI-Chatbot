"""Tests for the two Task 3 evidence fixes: the same-dish-name pool and the evidence gate.

Tiny synthetic database, no network, no real data, no model.
"""

from types import SimpleNamespace

import numpy as np
import pytest
from test_substitution import ROLES, STAPLES, VARIANTS, make_con

from recipebot.retrieval.masks import Constraints, build_sql_mask
from recipebot.tools.adaptation import choose_candidate
from recipebot.tools.stats import RecipeStats
from recipebot.tools.substitution import SubstitutionMiner

BREAD = ["banana", "flour", "sugar", "baking soda", "butter"]
# Title-related recipes with LOW ingredient overlap: they share only "banana" with the original
# (Jaccard about 0.09), so the ingredient similarity alone would never make them related.
RECIPES = [
    (0, "a:T", "Banana Bread", 8, BREAD + ["egg", "salt"]),
    (1, "a:B1", "Quick Banana Bread", 5, [
     "banana", "applesauce", "oats", "honey", "cinnamon", "nutmeg", "raisin"]),
    (2, "a:B2", "Healthy Banana Bread", 5, [
     "banana", "applesauce", "oats", "honey", "cinnamon", "nutmeg", "date"]),
    (3, "a:B3", "Banana Bread Muffins", 4, [
     "banana", "applesauce", "oats", "maple syrup", "cinnamon", "nutmeg", "pecan"]),
    (4, "a:E1", "Banana Bread", 8, BREAD + ["egg"]),
    (5, "a:E2", "Banana Bread", 8, BREAD + ["egg"]),
    (6, "a:X", "Banana Smoothie", 2, [
     "banana", "milk", "ice", "honey", "vanilla extract", "cinnamon", "oats"]),
]


@pytest.fixture()
def miner():
    con = make_con(RECIPES)
    yield SubstitutionMiner(con, RecipeStats(con, variants=VARIANTS), staples=STAPLES, roles=ROLES)
    con.close()


def mine(miner):
    constraints = Constraints()
    mask, sql, _ = build_sql_mask(miner.stats, len(RECIPES), constraints)
    return miner.mine("a:T", "egg", constraints, mask, sql)


def test_recipes_with_the_same_dish_name_are_related_even_with_low_ingredient_overlap(miner):
    res = mine(miner)
    # B1, B2, B3 share "banana" and "bread" with the title; the smoothie shares only "banana"
    assert res.pools["n_related_without"] == 3
    applesauce = next(c for c in res.candidates if c.name == "applesauce")
    assert applesauce.n_support == 3 and applesauce.n_direct == 3
    assert applesauce.level == "direct"
    assert {e.id for e in applesauce.evidence} == {"a:B1", "a:B2", "a:B3"}


def test_a_recipe_that_shares_only_one_title_word_stays_unrelated(miner):
    res = mine(miner)
    cited = {e.id for c in res.candidates for e in c.evidence}
    assert "a:X" not in cited


def _cand(level, n_support, with_evidence=True):
    return SimpleNamespace(level=level, n_support=n_support, evidence=[1] if with_evidence else [])


def _ev(*cands, status="ok"):
    return SimpleNamespace(status=status, candidates=list(cands))


def test_gate_direct_evidence_is_always_strong_enough():
    assert choose_candidate(_ev(_cand("direct", 2))) is not None


def test_gate_two_indirect_recipes_are_too_weak_to_build_a_recipe():
    assert choose_candidate(_ev(_cand("indirect", 2))) is None


def test_gate_three_indirect_recipes_are_enough():
    assert choose_candidate(_ev(_cand("indirect", 3))) is not None


def test_gate_min_support_can_be_changed():
    assert choose_candidate(_ev(_cand("indirect", 2)),
                            min_support=2) is not None
    assert choose_candidate(_ev(_cand("indirect", 3)), min_support=4) is None


def test_gate_knowledge_only_and_failed_status_never_pass():
    assert choose_candidate(_ev(_cand("none", 0, with_evidence=False))) is None
    assert choose_candidate(
        _ev(_cand("direct", 5), status="insufficient_evidence")) is None


def test_gate_skips_a_weak_first_candidate_and_takes_the_next_strong_one():
    weak, strong = _cand("indirect", 2), _cand("indirect", 4)
    assert choose_candidate(_ev(weak, strong)) is strong
