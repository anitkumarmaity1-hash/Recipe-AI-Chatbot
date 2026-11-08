"""Tests for the understanding layer (Step 8). No network and no real API key:
the Gemini client is replaced by a fake that returns scripted answers.
"""

import json
from dataclasses import fields

import pytest

from recipebot import config
from recipebot.normalization.allergens import load_allergens
from recipebot.retrieval.masks import Constraints
from recipebot.schemas import (
    Intent,
    Understanding,
    UnderstandingError,
    understanding_json_schema,
)
from recipebot.understanding import prompt as prompt_mod
from recipebot.understanding.backend import get_backend
from recipebot.understanding.gemini_backend import ConfigError, GeminiBackend
from recipebot.understanding.restrictions import (
    RestrictionMapper,
    normalize_phrase,
    to_constraints,
)

TERMS = {
    "allergen_phrases": {
        "dairy": ["dairy"], "egg": ["egg"], "eggs": ["egg"],
        "nuts": ["peanut", "tree_nut"], "gluten": ["gluten"],
    },
    "unsupported_phrases": ["vegan", "sugar free"],
}
ALLERGENS = ["dairy", "egg", "peanut", "tree_nut", "gluten"]


def mapper():
    return RestrictionMapper(TERMS, ALLERGENS)


# ---- schema ------------------------------------------------------------------------
def test_schema_properties_match_dataclass_fields():
    schema = understanding_json_schema()
    names = [f.name for f in fields(Understanding)]
    assert list(schema["properties"]) == names
    assert schema["required"] == names
    assert schema["properties"]["intent"]["enum"] == [i.value for i in Intent]
    assert schema["properties"]["include"] == {
        "type": "array", "items": {"type": "string"}}
    assert schema["properties"]["max_steps"] == {"type": "integer"}


def test_from_dict_minimal_and_sentinels():
    u = Understanding.from_dict({
        "intent": "search", "dish_query": "banana bread", "stat_type": "none",
        "restriction_type": "none", "max_steps": 0, "k": 0, "reason": "",
        "target_recipe_id": "", "include": [], "exclude": [],
    })
    assert u.intent is Intent.SEARCH and u.dish_query == "banana bread"
    assert u.stat_type is None and u.restriction_type is None
    assert u.max_steps is None and u.k is None and u.reason is None
    assert u.target_recipe_id is None and u.exclude == []


def test_from_dict_cleans_lists_and_text():
    u = Understanding.from_dict({
        "intent": "refine", "exclude": ["  Dairy ", "dairy", "EGGS", ""],
        "dish_query": "  pasta  ", "max_steps": 8.0,
    })
    assert u.exclude == ["dairy", "eggs"]
    assert u.dish_query == "pasta" and u.max_steps == 8


def test_from_dict_clamps_big_numbers():
    u = Understanding.from_dict({"intent": "refine", "max_steps": 10_000})
    assert u.max_steps == 500


@pytest.mark.parametrize("bad", [
    "not a dict",
    {},
    {"intent": "dance"},
    # stats needs stat_type
    {"intent": "stats"},
    {"intent": "stats", "stat_type": "median_of_doom"},
    {"intent": "search", "exclude": "dairy"},              # must be a list
    {"intent": "search", "exclude": [1, 2]},
    {"intent": "refine", "max_steps": -3},
    {"intent": "refine", "max_steps": "eight"},
    {"intent": "refine", "max_steps": True},
    {"intent": "refine", "max_steps": 2.5},
    {"intent": "refine", "restriction_type": "whim"},
    {"intent": "search", "dish_query": 42},
    {"intent": "search", "include": [f"x{i}" for i in range(21)]},
])
def test_from_dict_rejects_invalid(bad):
    with pytest.raises(UnderstandingError):
        Understanding.from_dict(bad)


def test_to_dict_roundtrip_uses_plain_values():
    u = Understanding.from_dict(
        {"intent": "stats", "stat_type": "count", "include": ["garlic"]})
    d = u.to_dict()
    assert d["intent"] == "stats" and d["stat_type"] == "count"
    # must be JSON-serialisable
    json.dumps(d)
    assert Understanding.from_dict(d).to_dict() == d


# ---- prompt ------------------------------------------------------------------------
def test_every_prompt_example_is_a_valid_understanding():
    for state, message, output in prompt_mod.EXAMPLES:
        u = Understanding.from_dict(prompt_mod.full_output(output))
        assert u.intent.value == output["intent"], message
        if u.target_recipe_id:                              # examples must use ids from their state
            ids = {r["id"] for r in state.get("last_results", [])}
            if state.get("active_recipe"):
                ids.add(state["active_recipe"]["id"])
            assert u.target_recipe_id in ids, message


def test_prompt_mentions_every_intent_and_payload_roundtrips():
    text = prompt_mod.build_system_prompt()
    for intent in Intent:
        assert intent.value in text
    payload = json.loads(prompt_mod.build_payload(
        "hi", {"active_filters": {}}))
    assert payload == {"session_state": {
        "active_filters": {}}, "user_message": "hi"}
    assert json.loads(prompt_mod.build_payload("hi", None))[
        "session_state"] == {}


# ---- restriction mapping -------------------------------------------------------------------
def test_normalize_phrase():
    assert normalize_phrase("  Dairy-Free ") == "dairy free"


def test_mapper_classifies_phrases():
    m = mapper().map(["dairy", "Dairy-Free", "eggs", "nuts", "butter", "vegan",
                      "sugar free", "no mushrooms", "gluten free", "", "butter"])
    assert m.allergens == ["dairy", "egg", "peanut", "tree_nut", "gluten"]
    assert m.ingredients == ["butter", "mushrooms"]
    # not turned into 'sugar'
    assert m.unsupported == ["vegan", "sugar free"]


def test_mapper_rejects_unknown_allergen_category():
    with pytest.raises(ValueError):
        RestrictionMapper(
            {"allergen_phrases": {"soy": ["soybean"]}}, ALLERGENS)


def test_to_constraints_bridges_to_step7():
    u = Understanding.from_dict({
        "intent": "refine", "include": ["garlic"], "exclude": ["dairy", "butter", "vegan"],
        "max_steps": 6,
    })
    constraints, unsupported = to_constraints(u, mapper())
    assert constraints == Constraints(include=("garlic",), exclude=("butter",),
                                      exclude_allergens=("dairy",), max_steps=6)
    assert unsupported == ["vegan"]


@pytest.mark.skipif(not (config.TAXONOMY_DIR / "allergens.yaml").exists(),
                    reason="real allergens.yaml not present")
def test_real_restriction_terms_match_real_allergen_taxonomy():
    real = RestrictionMapper.from_files(
        known_allergens=load_allergens().keys())
    mapped = real.map(["dairy", "eggs", "peanuts", "nuts",
                      "gluten-free", "vegan", "butter"])
    assert {"dairy", "egg", "peanut", "tree_nut",
            "gluten"} <= set(mapped.allergens)
    assert mapped.ingredients == ["butter"] and mapped.unsupported == ["vegan"]


# ---- Gemini backend with a fake client -------------------------------------------------------
genai_types = pytest.importorskip("google.genai.types")
genai_errors = pytest.importorskip("google.genai.errors")

GOOD = json.dumps(prompt_mod.full_output({"intent": "refine", "exclude": ["dairy"],
                                          "restriction_type": "allergy"}))


class FakeModels:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(
            {"model": model, "contents": contents, "config": config})
        item = self.outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        part = genai_types.Part(text=item)
        return genai_types.GenerateContentResponse(
            candidates=[genai_types.Candidate(content=genai_types.Content(parts=[part]))])


class FakeClient:
    def __init__(self, outputs):
        self.models = FakeModels(outputs)


def api_error(code, message="boom"):
    return genai_errors.APIError(code, {"error": {"message": message, "status": "X"}})


def backend(outputs, **kwargs):
    sleeps = []
    client = FakeClient(outputs)
    b = GeminiBackend(api_key="SECRET-KEY-123", model="test-model", client=client,
                      sleep=sleeps.append, max_retries=2, **kwargs)
    return b, client, sleeps


def test_happy_path_and_request_shape():
    b, client, _ = backend([GOOD])
    state = {"active_filters": {"include": ["pasta"]}}
    u = b.understand("I cannot have dairy", state)
    assert u.intent is Intent.REFINE and u.exclude == ["dairy"]
    call = client.models.calls[0]
    assert call["model"] == "test-model"
    cfg = call["config"]
    assert cfg.temperature == 0
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema == understanding_json_schema()
    assert "ONE user message" in cfg.system_instruction
    sent = json.loads(call["contents"])
    assert sent == {"session_state": state,
                    "user_message": "I cannot have dairy"}
    assert b.last_call["raw"] == GOOD and b.last_call["attempts"] == 1
    assert b.last_call["latency_ms"] >= 0


def test_retries_on_429_then_succeeds():
    b, client, sleeps = backend([api_error(429), GOOD])
    assert b.understand("hi").intent is Intent.REFINE
    assert len(client.models.calls) == 2 and sleeps == [1.0]
    assert b.last_call["attempts"] == 2


def test_gives_up_after_max_retries():
    b, client, sleeps = backend([api_error(503)] * 3)
    with pytest.raises(UnderstandingError, match="503"):
        b.understand("hi")
    assert len(client.models.calls) == 3 and sleeps == [1.0, 2.0]


def test_client_error_is_not_retried_and_key_is_scrubbed():
    b, client, sleeps = backend(
        [api_error(400, "bad key SECRET-KEY-123 rejected")])
    with pytest.raises(UnderstandingError) as info:
        b.understand("hi")
    assert "SECRET-KEY-123" not in str(info.value) and "***" in str(info.value)
    assert len(client.models.calls) == 1 and sleeps == []


def test_network_errors_are_retried_then_reported():
    b, client, sleeps = backend([TimeoutError("slow"), GOOD])
    assert b.understand("hi").intent is Intent.REFINE
    b2, _, _ = backend([ConnectionError("down")] * 3)
    with pytest.raises(UnderstandingError, match="Could not reach Gemini"):
        b2.understand("hi")


def test_invalid_json_gets_one_repair_attempt():
    b, client, _ = backend(["not json at all", GOOD])
    assert b.understand("hi").intent is Intent.REFINE
    repair_prompt = client.models.calls[1]["contents"]
    assert "previous output was invalid" in repair_prompt and '"user_message": "hi"' in repair_prompt


def test_invalid_slot_values_are_repaired_or_rejected():
    bad = json.dumps({"intent": "dance"})
    b, client, _ = backend([bad, GOOD])
    assert b.understand("hi").intent is Intent.REFINE
    b2, _, _ = backend([bad, bad])
    with pytest.raises(UnderstandingError, match="stayed invalid"):
        b2.understand("hi")


def test_empty_answer_and_empty_message():
    empty = genai_types.GenerateContentResponse(candidates=[])

    class EmptyModels:
        def generate_content(self, model, contents, config):
            return empty

    b = GeminiBackend(api_key="k", model="m", client=type("C", (), {"models": EmptyModels()})(),
                      sleep=lambda s: None)
    with pytest.raises(UnderstandingError, match="empty"):
        b.understand("hi")
    b2, client, _ = backend([GOOD])
    with pytest.raises(UnderstandingError, match="Empty message"):
        b2.understand("   ")
    assert client.models.calls == []                       # the model is not called


def test_missing_key_or_model_gives_clear_config_error():
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        GeminiBackend(api_key="", model="m")
    with pytest.raises(ConfigError, match="GEMINI_MODEL"):
        GeminiBackend(api_key="k", model="")


def test_target_recipe_id_must_come_from_session_state():
    made_up = json.dumps(prompt_mod.full_output(
        {"intent": "substitute", "target_recipe_id": "ar:999", "ingredient_to_replace": "butter"}))
    b, _, _ = backend([made_up])
    u = b.understand("replace the butter", {"last_results": [
                     {"n": 1, "id": "ar:1", "title": "x"}]})
    assert u.target_recipe_id is None and u.ingredient_to_replace == "butter"

    known = json.dumps(prompt_mod.full_output(
        {"intent": "show_details", "target_recipe_id": "ar:2"}))
    b2, _, _ = backend([known])
    assert b2.understand("steps", {"active_recipe": {
                         "id": "ar:2", "title": "y"}}).target_recipe_id == "ar:2"
    b3, _, _ = backend([known])
    assert b3.understand("steps", {"last_results": [{"n": 2, "id": "ar:2", "title": "y"}]}
                         ).target_recipe_id == "ar:2"


# ---- factory ------------------------------------------------------------------------------------
def test_factory():
    assert get_backend("gemini", api_key="k", model="m").name == "gemini"
    with pytest.raises(NotImplementedError, match="Step 13"):
        get_backend("lora")
    with pytest.raises(ValueError):
        get_backend("magic")
