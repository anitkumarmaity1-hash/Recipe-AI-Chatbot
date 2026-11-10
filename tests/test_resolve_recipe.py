"""Agent tests for the recipe lookup of a substitution request, and for the weak-evidence answer.

Uses the synthetic database and scripted model of test_agent_substitute.py. No network.
"""

from test_agent_substitute import U, make_agent  # noqa: F401  (make_agent is a pytest fixture)

from recipebot.agent import agent as agent_module


def spy_on_search(agent):
    """Record the constraints of every retriever.search call."""
    calls, original = [], agent.retriever.search

    def search(query, constraints, k=5):
        calls.append(constraints)
        return original(query, constraints, k=k)

    agent.retriever.search = search
    return calls


def test_the_original_recipe_must_contain_the_ingredient_to_replace(make_agent):
    agent = make_agent(
        U("substitute", target_recipe_title="Banana Bread", ingredient_to_replace="egg"))
    calls = spy_on_search(agent)
    reply = agent.handle("take a banana bread recipe and replace the egg")
    assert calls[0].include == ("egg",)
    assert "that contains egg" in reply.text and "[ar:T]" in reply.text


def test_no_recipe_with_that_ingredient_gives_a_clear_message(make_agent):
    agent = make_agent(
        U("substitute", target_recipe_title="Pizza", ingredient_to_replace="egg"))
    reply = agent.handle("replace the egg in a pizza recipe")
    assert "I could not find a recipe for 'Pizza' that contains egg." in reply.text
    assert "ADAPTED RECIPE" not in reply.text


def test_weak_evidence_lists_the_options_but_builds_no_recipe(make_agent, monkeypatch):
    # force "the evidence is below the bar" without changing the data
    monkeypatch.setattr(agent_module, "choose_candidate",
                        lambda evidence: None)
    agent = make_agent(
        U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg"))
    reply = agent.handle("replace the egg in ar:T")
    t = reply.text
    assert reply.guard_problems == [] and reply.tool == "substitute"
    assert "Result: WEAK EVIDENCE" in t and "I did not build an adapted recipe" in t
    assert "ADAPTED RECIPE" not in t and "[ar:W1]" in t
