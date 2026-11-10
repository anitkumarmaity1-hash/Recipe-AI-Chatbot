"""Agent tests for substitution (Step 12): the real agent loop, composer and guard on the
synthetic database of test_substitution.py (ids renamed to 'ar:...' so the output guard checks
them), a small fake retriever and a scripted "language model". No network, no real data.
"""

from types import SimpleNamespace

import numpy as np
import pytest
from test_substitution import DAIRY, RECIPES, ROLES, STAPLES, VARIANTS, make_con

from recipebot.agent import agent as agent_module
from recipebot.agent.agent import RecipeAgent
from recipebot.normalization.allergens import AllergenMatcher
from recipebot.retrieval.common import tokenize
from recipebot.retrieval.masks import build_sql_mask
from recipebot.schemas import Intent, Understanding
from recipebot.tools.stats import RecipeStats
from recipebot.tools.substitution import SubstitutionMiner
from recipebot.understanding.restrictions import RestrictionMapper

TAXONOMY = {**DAIRY, "egg": {"include": ["egg"], "exceptions": []}}
TERMS = {"allergen_phrases": {"dairy": ["dairy"], "eggs": [
    "egg"]}, "unsupported_phrases": ["vegan"]}
AR_RECIPES = [(r, i.replace("a:", "ar:"), t, s, n)
              for r, i, t, s, n in RECIPES]
N = len(AR_RECIPES)


class FakeRetriever:
    """The parts of HybridRetriever the agent uses for substitution."""

    def __init__(self, con, stats, matcher):
        self.con, self.stats, self.matcher = con, stats, matcher

    def allowed_mask(self, constraints):
        mask, sql, _ = build_sql_mask(self.stats, N, constraints)
        for allergen in constraints.exclude_allergens:
            mask &= np.array([not any(self.matcher.matches(f"1 cup {n}", allergen) for n in names)
                              for *_, names in AR_RECIPES])
        return mask, sql

    def search(self, query, constraints, k=5):
        words = set(tokenize(query))
        hits = [SimpleNamespace(id=i, title=t) for _, i, t, _, _ in AR_RECIPES
                if words <= set(tokenize(t))]
        return SimpleNamespace(hits=hits[:k])


class Scripted:
    def __init__(self, *items):
        self.items = list(items)

    def understand(self, message, state=None):
        return self.items.pop(0)


def U(intent, **slots):
    return Understanding(intent=Intent(intent), **slots)


@pytest.fixture()
def make_agent():
    con = make_con(AR_RECIPES)
    con.execute("UPDATE recipes SET instructions_clean = 'Beat the eggs. Fold in the flour. Bake.' "
                "WHERE id = 'ar:T'")
    stats = RecipeStats(con, variants=VARIANTS)
    matcher = AllergenMatcher(TAXONOMY)
    miner = SubstitutionMiner(
        con, stats, staples=STAPLES, roles=ROLES, allergen_matcher=matcher)
    retriever = FakeRetriever(con, stats, matcher)
    mapper = RestrictionMapper(TERMS, known_allergens=TAXONOMY.keys())

    def build(*script):
        return RecipeAgent(retriever, Scripted(*script), mapper, miner=miner)

    yield build
    con.close()


def test_a_full_substitution_answer_is_grounded_and_complete(make_agent):
    agent = make_agent(
        U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg"))
    reply = agent.handle("replace the egg in ar:T")
    t = reply.text
    assert reply.guard_problems == [] and reply.tool == "substitute"
    assert "Substitution: replace egg in \"Banana Bread\" [ar:T]" in t
    assert "DIRECT evidence" in t and "[ar:W1]" in t
    assert "ADAPTED RECIPE" in t and "<- CHANGED" in t and "<- REVISED" in t
    assert "5 related recipes with egg, 8 without" in t
    for label in ("Supported by the dataset:", "Inferred from similar recipes:",
                  "Predicted taste/texture:", "Unknown or unverified:"):
        assert label in t
    assert "not medical or allergy advice" in t
    assert agent.state.mode == "substitute" and agent.state.active_recipe["id"] == "ar:T"


def test_the_original_recipe_is_not_changed_by_a_substitution(make_agent):
    agent = make_agent(
        U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg"))
    before = agent.con.execute("SELECT ingredients_clean, instructions_clean FROM recipes "
                               "WHERE id = 'ar:T'").fetchone()
    agent.handle("replace the egg")
    assert agent.con.execute("SELECT ingredients_clean, instructions_clean FROM recipes "
                             "WHERE id = 'ar:T'").fetchone() == before


def test_a_recipe_named_by_title_is_found_and_the_user_is_told(make_agent):
    agent = make_agent(
        U("substitute", target_recipe_title="Banana Bread", ingredient_to_replace="egg"))
    reply = agent.handle("take the banana bread and remove the egg")
    assert "No recipe id was given" in reply.text and "[ar:T]" in reply.text
    assert reply.payload["evidence"]["original"]["id"] == "ar:T"


def test_the_active_recipe_is_used_when_no_recipe_is_named(make_agent):
    agent = make_agent(U("substitute", ingredient_to_replace="egg"))
    agent.state.active_recipe = {"id": "ar:T", "title": "Banana Bread"}
    assert "ADAPTED RECIPE" in agent.handle("replace the egg").text


def test_a_new_restriction_in_the_same_message_is_applied_and_remembered(make_agent):
    agent = make_agent(U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg",
                         exclude=["walnut"]))
    # walnut is not in the vocabulary of the tiny database as an ingredient name? it is, so:
    reply = agent.handle("replace the egg, no walnut")
    assert agent.state.exclude_ingredients == ["walnut"]
    assert "no walnut (ingredient)" in reply.text


def test_weak_evidence_is_refused_and_conflicts_are_shown(make_agent):
    agent = make_agent(U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg",
                         exclude=["dairy"]))
    reply = agent.handle("replace the egg, I cannot have dairy")
    t = reply.text
    assert reply.guard_problems == [] and reply.payload["adapted"] is None
    assert "INSUFFICIENT EVIDENCE" in t and "I did not build an adapted recipe" in t
    assert "ADAPTED RECIPE" not in t
    assert "STILL CONFLICTS" in t and "1 cup butter" in t
    assert "Allergen checks read the ingredient text only" in t


def test_a_follow_up_restriction_reruns_the_substitution(make_agent):
    agent = make_agent(U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg"),
                       U("refine", exclude=["dairy"]))
    assert "ADAPTED RECIPE" in agent.handle("replace the egg").text
    reply = agent.handle("I cannot have dairy")
    assert agent.state.exclude_allergens == ["dairy"]
    assert "INSUFFICIENT EVIDENCE" in reply.text and reply.tool == "substitute"


def test_the_agent_asks_which_ingredient_when_none_is_named(make_agent):
    agent = make_agent(U("substitute", target_recipe_id="ar:T"))
    reply = agent.handle("make this recipe different")
    assert "Which ingredient should I replace" in reply.text and "banana" in reply.text
    assert reply.payload is None


def test_the_agent_asks_which_recipe_when_none_is_known(make_agent):
    reply = make_agent(U("substitute", ingredient_to_replace="egg")).handle(
        "replace the egg")
    assert reply.text.startswith("Which recipe?")


def test_an_ingredient_that_is_not_in_the_recipe_is_explained(make_agent):
    reply = make_agent(U("substitute", target_recipe_id="ar:T",
                         ingredient_to_replace="walnut")).handle("replace the walnut")
    assert "not an ingredient of 'Banana Bread'" in reply.text


def test_an_unknown_recipe_id_is_refused(make_agent):
    reply = make_agent(U("substitute", target_recipe_id="ar:NOPE",
                         ingredient_to_replace="egg")).handle("replace the egg")
    assert "no recipe with the id 'ar:NOPE'" in reply.text


def test_an_unknown_ingredient_changes_nothing(make_agent):
    agent = make_agent(U("substitute", target_recipe_id="ar:T", ingredient_to_replace="unicorn",
                         exclude=["dairy"]))
    reply = agent.handle("replace the unicorn, no dairy")
    assert "Nothing was changed" in reply.text
    assert agent.state.exclude_allergens == [] and agent.state.mode == "search"


def test_a_failed_validation_withholds_the_answer(make_agent, monkeypatch):
    monkeypatch.setattr(agent_module, "validate_adaptation",
                        lambda *a, **k: ["boom"])
    agent = make_agent(
        U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg"))
    reply = agent.handle("replace the egg")
    assert reply.text.startswith("I can't provide an adapted recipe") and "boom" in reply.text
    assert "ADAPTED RECIPE" not in reply.text and agent.state.mode == "search"
    assert reply.payload["adapted"] is None
    assert reply.payload["adaptation_validation"]["passed"] is False
