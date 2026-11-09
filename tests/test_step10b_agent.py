"""Step 10b at the level of the whole agent: the two live defects replayed on the tiny
test database of test_agent.py (scripted language model, no network, no real data).
"""

import pytest
from test_agent import U, make_agent  # noqa: F401  (make_agent is a fixture)


def match_ids(reply):
    return [h["id"] for h in reply.payload["hits"]]


def test_live_defect_1_exclude_eggs_removes_egg_from_the_ingredient_list(make_agent):
    # "eggs" maps to the allergen `egg` (like in the live Step 10 run)
    agent, _ = make_agent(U("match", available=["tomato", "egg"]),
                          U("refine", exclude=["eggs"]))
    first = agent.handle("I have tomatoes and eggs")
    assert first.payload["terms"] == ["tomato", "egg"]
    second = agent.handle("Exclude eggs too")
    assert second.tool == "match" and second.guard_problems == []
    assert second.payload["terms"] == [
        "tomato"] and second.payload["dropped"] == ["egg"]
    assert "Not counted: 'egg' is in your ingredient list but you also excluded it." in second.text
    assert "Ingredient match for: tomato (1 ingredient)" in second.text
    assert "Matched (1 of 1)" in second.text and "Missing, you have it but the recipe does not use it (0)" in second.text
    assert all("egg" not in h["unused"] and "egg" not in h["matched"]
               for h in second.payload["hits"])
    # the hard constraint still holds: a:3 (peanut cookies) contains egg
    assert "a:3" not in match_ids(second)
    assert "no egg (allergen check)" in second.text


def test_removing_the_restriction_brings_the_ingredient_back(make_agent):
    agent, _ = make_agent(U("match", available=["tomato", "egg"], exclude=["eggs"]),
                          U("refine", allow=["eggs"]))
    assert agent.handle("tomato and egg, no eggs").payload["terms"] == [
        "tomato"]
    assert agent.handle("eggs are fine now").payload["terms"] == [
        "tomato", "egg"]


def test_live_defect_2_i_also_have_rice_keeps_the_step_limit(make_agent):
    agent, _ = make_agent(U("match", available=["garlic", "tomato"], max_steps=4),
                          U("match", available=["garlic", "tomato", "onion"]))
    first = agent.handle("garlic and tomato, at most 4 steps")
    assert match_ids(first) == ["a:2", "a:1"]
    second = agent.handle("I also have onion")
    assert agent.state.max_steps == 4
    assert "Ingredient list extended: your 'must contain' list and step limit were kept." in second.text
    assert "New search" not in second.text and "at most 4 steps" in second.text
    assert second.payload["hits"] and all(
        h["n_steps"] <= 4 for h in second.payload["hits"])


def test_a_different_list_still_starts_a_new_search(make_agent):
    agent, _ = make_agent(U("match", available=["garlic", "tomato"], max_steps=4),
                          U("match", available=["onion"]))
    agent.handle("garlic and tomato, at most 4 steps")
    second = agent.handle("actually I only have onion")
    assert agent.state.max_steps is None and "New search" in second.text
