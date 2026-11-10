"""P1 output fixes: ingredient lines shown as evidence in search answers, clean amount line in substitutions."""

from types import SimpleNamespace

from test_agent_substitute import U, make_agent  # noqa: F401  (make_agent is a pytest fixture)

from recipebot.agent.composer import MAX_EVIDENCE_LINES, compose_search


def result(constraints, row_idx=7):
    hit = SimpleNamespace(row_idx=row_idx, title="Penne",
                          id="ar:P", bm25_rank=1, semantic_rank=2)
    return SimpleNamespace(constraints=constraints, query="penne", n_allowed=1, n_total=5, hits=[hit], note="")


NONE = {"include": [], "exclude": [],
        "exclude_allergens": [], "max_steps": None}
DAIRY = {**NONE, "exclude_allergens": ["dairy"]}


def test_ingredient_lines_are_printed_when_a_filter_is_active():
    text = compose_search(result(DAIRY), [], {7: (5, 2)}, ingredient_lines={
                          7: ["1 cup penne", "2 tbsp olive oil"]})
    assert "Ingredient lines (the evidence for the check):" in text
    assert "- 1 cup penne" in text and "- 2 tbsp olive oil" in text


def test_ingredient_lines_are_not_printed_without_filters_or_lines():
    lines = {7: ["1 cup penne"]}
    assert "Ingredient lines" not in compose_search(
        result(NONE), [], {7: (5, 1)}, ingredient_lines=lines)
    assert "Ingredient lines" not in compose_search(
        result(DAIRY), [], {7: (5, 1)})


def test_a_step_limit_alone_also_shows_the_lines():
    assert "Ingredient lines" in compose_search(
        result({**NONE, "max_steps": 6}), [], {7: (5, 1)}, ingredient_lines={7: ["1 cup penne"]})


def test_long_ingredient_lists_are_cut_and_counted():
    many = [f"{i} cup thing" for i in range(MAX_EVIDENCE_LINES + 3)]
    text = compose_search(result(DAIRY), [], {7: (
        5, len(many))}, ingredient_lines={7: many})
    assert "... and 3 more" in text and many[MAX_EVIDENCE_LINES -
                                             1] in text and many[MAX_EVIDENCE_LINES] not in text


def test_the_substitute_line_is_clean_and_the_reference_amount_sits_beside_it(make_agent):
    agent = make_agent(
        U("substitute", target_recipe_id="ar:T", ingredient_to_replace="egg"))
    text = agent.handle("replace the egg in ar:T").text
    assert "  - applesauce (amount not verified from the dataset)   <- CHANGED" in text
    assert 'for scale: [ar:W1] uses "1 cup applesauce"' in text
