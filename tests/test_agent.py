"""Tests for the agent loop (Step 9): tiny database, real BM25/FAISS built from it,
a fake hash encoder and a scripted "language model". No network, no real data.
"""

import zlib

import duckdb
import numpy as np
import pytest

from recipebot.agent.agent import RecipeAgent
from recipebot.normalization.allergens import AllergenMatcher
from recipebot.retrieval.bm25 import Bm25Index, build_bm25
from recipebot.retrieval.common import ids_fingerprint, tokenize
from recipebot.retrieval.embeddings import SemanticIndex, build_embeddings
from recipebot.retrieval.hybrid import HybridRetriever
from recipebot.retrieval.masks import AllergenFlags
from recipebot.schemas import Intent, StatType, Understanding, UnderstandingError
from recipebot.tools.stats import RecipeStats
from recipebot.understanding.restrictions import RestrictionMapper

pytest.importorskip("faiss")
pytest.importorskip("rank_bm25")

TAXONOMY = {
    "dairy": {"include": ["milk", "butter", "cream", "cheese"],
              "exceptions": ["peanut butter", "coconut milk"]},
    "egg": {"include": ["egg"], "exceptions": []},
    "peanut": {"include": ["peanut"], "exceptions": []},
}
TERMS = {"allergen_phrases": {"dairy": ["dairy"], "eggs": ["egg"], "peanuts": ["peanut"]},
         "unsupported_phrases": ["vegan"]}

# row_idx, id, title, cleaned lines, canonical names, instructions, n_steps
RECIPES = [
    (0, "a:1", "Garlic Bread", ["2 cloves garlic", "1/2 cup butter", "1 loaf bread"],
     ["garlic", "butter", "bread"], "Mix. Spread. Bake.", 3),
    (1, "a:2", "Tomato Soup", ["4 tomatoes", "1 onion", "2 cups water"],
     ["tomato", "onion", "water"], "Chop. Simmer. Blend. Serve.", 4),
    (2, "a:3", "Peanut Cookies", ["1 cup peanut butter", "1 cup sugar", "1 egg"],
     ["peanut butter", "sugar", "egg"], "Mix. Shape. Bake. Cool. Eat.", 5),
    (3, "a:4", "Plain Rice", ["1 cup rice",
     "2 cups water"], ["rice", "water"], "", 0),
    (4, "a:5", "Garlic Tomato Pasta", ["2 cloves garlic", "3 tomatoes", "8 oz pasta"],
     ["garlic", "tomato", "pasta"], "Boil the pasta. Fry the garlic. Add tomatoes. Toss. Serve. Enjoy.", 6),
    (5, "a:6", "Coconut Curry", ["1 can coconut milk", "2 tomatoes", "1 onion"],
     ["coconut milk", "tomato", "onion"], "Fry. Add. Simmer. Stir. Cook. Season. Taste. Serve.", 8),
]


def make_db(path):
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE recipes (id VARCHAR, row_idx INTEGER, source VARCHAR, title VARCHAR, "
                "ingredients_clean VARCHAR[], instructions_clean VARCHAR)")
    con.execute("CREATE TABLE recipe_stats (row_idx INTEGER, id VARCHAR, n_ingredients INTEGER, "
                "n_lines INTEGER, n_steps INTEGER)")
    con.execute("CREATE TABLE recipe_ingredient (recipe_id VARCHAR, row_idx INTEGER, position INTEGER, "
                "name_index INTEGER, canonical VARCHAR)")
    for row_idx, rid, title, lines, names, text, steps in RECIPES:
        con.execute("INSERT INTO recipes VALUES (?, ?, 'ar', ?, ?, ?)", [
                    rid, row_idx, title, lines, text])
        con.execute("INSERT INTO recipe_stats VALUES (?, ?, ?, ?, ?)", [
                    row_idx, rid, len(names), len(lines), steps])
        for pos, canon in enumerate(names):
            con.execute("INSERT INTO recipe_ingredient VALUES (?, ?, ?, 0, ?)", [
                        rid, row_idx, pos, canon])
    con.close()
    return path


def fake_encoder(texts):
    out = np.zeros((len(texts), 256), dtype="float32")
    for i, text in enumerate(texts):
        for tok in tokenize(text):
            out[i, zlib.crc32(tok.encode()) % 256] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return out / norms


class Scripted:
    """Stands in for Gemini: returns the next prepared Understanding (or raises it)."""

    def __init__(self, *items):
        self.items = list(items)
        self.calls = []

    def understand(self, message, state=None):
        self.calls.append((message, state))
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def U(intent, **slots):
    if "stat_type" in slots:
        slots["stat_type"] = StatType(slots["stat_type"])
    return Understanding(intent=Intent(intent), **slots)


@pytest.fixture()
def make_agent(tmp_path):
    db_path = make_db(tmp_path / "t.duckdb")
    idx = tmp_path / "idx"
    build_bm25(db_path, idx / "bm25.pkl")
    build_embeddings(db_path, idx, encoder=fake_encoder, shard_size=4)
    con = duckdb.connect(str(db_path), read_only=True)
    ids = [r[1] for r in RECIPES]
    flags = AllergenFlags.load_or_build(
        con, TAXONOMY, ids_fingerprint(ids), tmp_path / "flags.npz")
    retriever = HybridRetriever(con, Bm25Index.load(idx / "bm25.pkl"),
                                SemanticIndex.load(idx, encoder=fake_encoder),
                                RecipeStats(con, variants={}), flags, AllergenMatcher(TAXONOMY), pool_size=50)
    mapper = RestrictionMapper(TERMS, known_allergens=TAXONOMY.keys())

    def build(*script):
        model = Scripted(*script)
        return RecipeAgent(retriever, model, mapper, default_k=5), model

    yield build
    con.close()


def shown_ids(reply):
    return [h["id"] for h in reply.payload["hits"]]


# ---- search and follow-ups (Task 1) ----------------------------------------------
def test_first_search_returns_grounded_results(make_agent):
    agent, _ = make_agent(U("search", dish_query="garlic"))
    reply = agent.handle("Find me a garlic recipe")
    assert reply.guard_problems == []
    assert set(shown_ids(reply)[:2]) == {"a:1", "a:5"}
    assert "Eligible recipes: 6 of 6" in reply.text
    assert "[a:1]" in reply.text
    assert [r["id"] for r in agent.state.last_results] == shown_ids(reply)


def test_follow_up_restriction_refines_the_previous_search_and_persists(make_agent):
    agent, model = make_agent(U("search", dish_query="garlic"),
                              U("refine", exclude=["dairy"]),
                              U("search", dish_query="tomato"))
    first = agent.handle("garlic please")
    assert "a:1" in shown_ids(first)
    # no dish named: re-runs "garlic"
    second = agent.handle("I cannot have dairy")
    assert "a:1" not in shown_ids(second)                    # butter is dairy
    assert "a:5" in shown_ids(second)
    assert "Added restriction: no dairy" in second.text
    assert "no dairy (allergen check)" in second.text
    assert "not medical advice" in second.text
    # restriction is still active
    third = agent.handle("now something with tomato")
    assert "a:1" not in shown_ids(third)
    assert "no dairy" in third.text
    assert model.calls[2][1]["active_filters"]["exclude"] == [
        "dairy"]   # sent to the model as state


def test_allow_removes_the_restriction_and_results_return(make_agent):
    agent, _ = make_agent(U("search", dish_query="garlic", exclude=[
                          "dairy"]), U("refine", allow=["dairy"]))
    assert "a:1" not in shown_ids(agent.handle("garlic, no dairy"))
    assert "a:1" in shown_ids(agent.handle("dairy is fine now"))


def test_no_match_says_so_and_relaxes_nothing(make_agent):
    agent, _ = make_agent(U("search", dish_query="rice",
                          include=["rice"], max_steps=3))
    # the only rice recipe has 0 steps
    reply = agent.handle("rice in at most 3 steps")
    assert reply.payload["hits"] == []
    assert "Eligible recipes: 0 of 6" in reply.text and "nothing was relaxed" in reply.text.lower()


def test_unknown_ingredient_rolls_the_session_back(make_agent):
    agent, _ = make_agent(U("refine", exclude=["unobtainium"]))
    reply = agent.handle("no unobtainium please")
    assert "not in the dataset vocabulary" in reply.text and "Nothing was changed" in reply.text
    assert agent.state.exclude_ingredients == []


def test_unenforced_restriction_is_reported_not_dropped(make_agent):
    agent, _ = make_agent(U("search", dish_query="garlic", exclude=["vegan"]))
    reply = agent.handle("vegan garlic dishes")
    assert "NOT enforced" in reply.text and "vegan" in reply.text


# ---- statistics ------------------------------------------------------------------
def test_count_states_value_denominator_filters_and_definition(make_agent):
    agent, _ = make_agent(U("stats", stat_type="count", include=["garlic"]))
    reply = agent.handle("How many recipes contain garlic?")
    assert reply.payload["value"] == 2 and reply.payload["n_analyzed"] == 6
    assert "Answer: 2 recipes (33.3% of 6 usable recipes)." in reply.text
    assert "contains all of garlic" in reply.text and 'Definition of "contains"' in reply.text


def test_percentage_and_any_of(make_agent):
    agent, _ = make_agent(U("stats", stat_type="percentage", include=["garlic", "tomato"]),
                          U("stats", stat_type="count", include_any=["garlic", "rice"]))
    reply = agent.handle("percent with both garlic and tomato")
    assert reply.payload["value"] == pytest.approx(
        100 * 1 / 6)              # only a:5
    assert "Calculation: 1 / 6 x 100 = 16.7%" in reply.text
    # a:1, a:5, a:4
    assert agent.handle("garlic or rice").payload["value"] == 3


def test_dish_name_that_is_not_an_ingredient_is_refused_not_ignored(make_agent):
    agent, _ = make_agent(
        U("stats", stat_type="count", dish_query="banana bread"))
    reply = agent.handle("how many banana bread recipes")
    assert reply.tool is None and "only filter by ingredient names" in reply.text


def test_stats_do_not_apply_or_change_session_restrictions(make_agent):
    agent, _ = make_agent(U("refine", exclude=["dairy"]), U(
        "stats", stat_type="count", include=["garlic"]))
    agent.handle("no dairy")
    reply = agent.handle("how many have garlic")
    # a:1 still counted
    assert reply.payload["value"] == 2
    assert "NOT applied to this dataset-wide number" in reply.text
    assert agent.state.exclude_allergens == ["dairy"]


def test_fewest_steps_matches_the_stats_tool_without_restrictions(make_agent):
    agent, _ = make_agent(U("stats", stat_type="fewest_steps", k=5))
    reply = agent.handle("five recipes with the fewest steps")
    expected = RecipeStats(agent.con, variants={}
                           ).fewest_steps(None, k=5).value
    # same ids, same order
    assert reply.payload["value"] == expected
    assert [r["id"] for r in expected] == [
        "a:1", "a:2", "a:3", "a:5", "a:6"]  # a:4 has 0 steps


def test_fewest_steps_respects_the_session_allergen_restriction(make_agent):
    agent, _ = make_agent(U("refine", exclude=["dairy"]),
                          U("stats", stat_type="fewest_steps", k=3, include=["tomato"]))
    agent.handle("no dairy")
    reply = agent.handle("3 tomato recipes with the fewest steps")
    assert [r["id"] for r in reply.payload["value"]] == ["a:2", "a:5", "a:6"]
    assert reply.payload["n_analyzed"] == 3
    assert "active restrictions were applied" in reply.text
    agent2, _ = make_agent(U("refine", exclude=["dairy"]), U(
        "stats", stat_type="fewest_steps", k=3))
    agent2.handle("no dairy")
    assert "a:1" not in [r["id"]
                         for r in agent2.handle("fewest steps").payload["value"]]


def test_top_ingredients_leaves_out_the_filter_ingredient(make_agent):
    agent, _ = make_agent(
        U("stats", stat_type="top_ingredients", include=["tomato"], k=2))
    reply = agent.handle("what goes with tomato most often")
    names = [r["ingredient"] for r in reply.payload["value"]]
    # onion in a:2 and a:6
    assert "tomato" not in names and names[0] == "onion"


# ---- recipe details ----------------------------------------------------------------
def test_details_shows_ingredients_and_steps_and_sets_active_recipe(make_agent):
    agent, _ = make_agent(U("show_details", target_recipe_id="a:5"))
    reply = agent.handle("show me the first one")
    assert "Garlic Tomato Pasta  [a:5]" in reply.text and "  - 8 oz pasta" in reply.text
    assert "6 steps" in reply.text and "1. Boil the pasta." in reply.text
    assert agent.state.active_recipe == {
        "id": "a:5", "title": "Garlic Tomato Pasta"}


def test_details_warns_when_the_recipe_breaks_an_active_restriction(make_agent):
    agent, _ = make_agent(U("refine", exclude=["dairy"]), U(
        "show_details", target_recipe_id="a:1"))
    agent.handle("no dairy")
    assert "WARNING: this recipe mentions dairy ('butter'" in agent.handle(
        "show a:1").text


def test_details_without_a_target_asks_which_recipe(make_agent):
    agent, _ = make_agent(U("show_details"))
    assert "Which recipe?" in agent.handle("show the steps").text


def test_details_for_an_unknown_id(make_agent):
    agent, _ = make_agent(U("show_details", target_recipe_id="zz:9"))
    assert "no recipe with the id 'zz:9'" in agent.handle("show zz:9").text


# ---- refusals, errors and guards ------------------------------------------------------
def test_unsupported_attribute_is_refused_without_calling_the_model(make_agent):
    agent, model = make_agent()
    reply = agent.handle("How many calories does banana bread have?")
    assert "no cooking-time or nutrition" in reply.text and model.calls == []


def test_model_failure_changes_nothing_and_is_explained(make_agent):
    agent, _ = make_agent(
        U("refine", exclude=["dairy"]), UnderstandingError("bad json"))
    agent.handle("no dairy")
    reply = agent.handle("something confusing")
    assert "could not understand" in reply.text and "bad json" in reply.text
    assert agent.state.exclude_allergens == ["dairy"]


def test_match_and_substitute_are_honest_placeholders(make_agent):
    agent, _ = make_agent(U("match", available=["eggs"]), U(
        "substitute", ingredient_to_replace="butter"))
    assert "not built yet" in agent.handle("I have eggs").text
    assert "not built yet" in agent.handle("replace the butter").text


def test_clear_filters_empties_the_restrictions(make_agent):
    agent, _ = make_agent(U("refine", exclude=["dairy"]), U("clear_filters"))
    agent.handle("no dairy")
    assert "All restrictions cleared" in agent.handle(
        "forget my restrictions").text
    assert agent.state.constraints().is_empty()


def test_a_constraint_violation_found_by_verify_withholds_the_results(make_agent):
    agent, _ = make_agent(U("search", dish_query="garlic", exclude=["dairy"]))
    agent.retriever.verify = lambda hits, constraints: [
        "a:1: dairy (butter) in '1/2 cup butter'"]
    reply = agent.handle("garlic, no dairy")
    assert "Results withheld" in reply.text and "[a:" not in reply.text
    assert agent.state.last_results == []


def test_the_output_guard_blocks_an_answer_with_an_invented_id(make_agent):
    agent, _ = make_agent(U("show_details", target_recipe_id="a:5"))
    from recipebot.agent import composer
    original = composer.compose_details
    composer.compose_details = lambda *a, **k: original(
        *a, **k) + "\nTry also [ar:invented]"
    try:
        reply = agent.handle("show a:5")
    finally:
        composer.compose_details = original
    assert "withheld" in reply.text and "ar:invented" in reply.guard_problems[0]
