"""Step 1 (hard restrictions in substitution): message safety net and implied allergen group.

Uses the synthetic database and scripted model of test_agent_substitute.py. No network.
"""

from test_agent_substitute import TERMS, U, make_agent  # noqa: F401  (make_agent is a fixture)

from recipebot.understanding.message_hints import merge_hints, restriction_hints
from recipebot.understanding.restrictions import RestrictionMapper

MAPPER = RestrictionMapper({
    "allergen_phrases": {**TERMS["allergen_phrases"], "nuts": ["dairy"], "gluten": ["dairy"]},
    "unsupported_phrases": ["vegan", "sugar free"]})


def test_hint_without_dairy():
    assert restriction_hints(
        "Take a penne pasta recipe and replace the cream without dairy.", MAPPER) == ["dairy"]


def test_hint_free_suffix_and_hyphen():
    assert restriction_hints("make it dairy-free", MAPPER) == ["dairy-free"]
    assert restriction_hints(
        "I need a gluten free version", MAPPER) == ["gluten"]


def test_hint_picks_the_known_word_from_a_longer_phrase():
    assert restriction_hints("no nuts either", MAPPER) == ["nuts"]


def test_hint_unsupported_diet_is_kept_so_it_can_be_reported():
    assert restriction_hints("a sugar free version please", MAPPER) == [
        "sugar free"]


def test_hint_ignores_ingredient_phrases_and_plain_requests():
    assert restriction_hints("remove the eggs", MAPPER) == []
    assert restriction_hints("make it without butter", MAPPER) == []
    assert restriction_hints("", MAPPER) == []


def test_merge_keeps_the_model_list_and_adds_nothing_twice():
    assert merge_hints("without dairy", [], MAPPER) == ["dairy"]
    assert merge_hints("without dairy", ["Dairy"], MAPPER) == ["Dairy"]
    assert merge_hints("without dairy", ["walnut"], MAPPER) == [
        "walnut", "dairy"]


def test_agent_applies_a_restriction_the_model_missed(make_agent):
    agent = make_agent(
        U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg"))
    agent.handle("replace the egg, I cannot have dairy")
    assert agent.state.exclude_allergens == ["dairy"]


def test_replacing_egg_closes_the_egg_group_for_substitutes(make_agent):
    agent = make_agent(
        U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg"))
    reply = agent.handle("take the banana bread and remove the egg")
    ev = reply.payload["evidence"]
    assert "egg" in ev["constraints"]["exclude_allergens"]
    assert "same allergen group as the ingredient being replaced" in reply.text
    # implied, not remembered as a user rule
    assert agent.state.exclude_allergens == []
    matcher = agent.retriever.matcher
    assert all(not matcher.matches(c["name"], "egg") for c in ev["candidates"])
