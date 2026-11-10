"""Tests for the evaluation set: the checks themselves, the case runner and golden.json."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

from checks import KNOWN_CHECKS, ids_in, run_checks  # noqa: E402
from run_eval import run_case  # noqa: E402


class FakeFacts:
    def existing_ids(self, ids):
        return {i for i in ids if i != "ar:fake"}

    def n_steps(self, ids):
        return {"ar:a": 4, "ar:b": 9}

    def allergen_hits(self, ids, allergen):
        return ["ar:b: 1 cup milk"] if "ar:b" in ids else []


def check(text, checks, intent="search", guard=()):
    return run_checks(text, intent, guard, checks, FakeFacts())


def test_ids_are_read_from_square_brackets_only():
    assert ids_in(
        "[ar:a] and [epi:b/c] and ar:plain and [zz:x]") == ["ar:a", "epi:b/c"]


def test_a_clean_reply_passes():
    assert check("Found [ar:a] and [ar:c]", {"intent": "search", "min_ids": 2, "ids_exist": True,
                                             "max_steps_ids": 10, "contains": ["Found"]}) == []


def test_each_failure_is_reported():
    out = check("Found [ar:b] [ar:fake]", {"intent": "stats", "contains": ["zzz"], "not_contains": ["Found"],
                                           "n_ids": 1, "ids_exist": True, "max_steps_ids": 5, "no_allergen": "dairy"})
    text = " | ".join(out)
    for part in ("intent was", "does not contain", "must not contain", "expected 1",
                 "not in the database", "over the 5-step", "mention dairy"):
        assert part in text


def test_guard_problems_always_fail_the_turn():
    assert any("guard" in f for f in check(
        "ok", {}, guard=["id not in tool output"]))


def test_unknown_check_names_are_rejected():
    assert check("x", {"contanis": ["x"]})[0].startswith("unknown check")


def test_run_case_judges_only_turns_with_checks():
    replies = iter([SimpleNamespace(text="first", intent="search", guard_problems=[]),
                    SimpleNamespace(text="Found [ar:a]", intent="refine", guard_problems=[])])
    agent = SimpleNamespace(
        reset=lambda: None, handle=lambda message: next(replies))
    case = {"id": "x", "task": 1, "what": "demo",
            "turns": [{"say": "a"}, {"say": "b", "checks": {"intent": "refine", "n_ids": 1}}]}
    result = run_case(agent, case, FakeFacts())
    assert result["passed"] and result["last_reply"] == "Found [ar:a]"


def test_golden_file_is_valid():
    cases = json.loads(
        (ROOT / "eval" / "golden.json").read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 10 and len({c["id"] for c in cases}) == len(cases)
    assert {c["task"] for c in cases} == {1, 2, 3}
    for case in cases:
        assert case["turns"] and all("say" in t for t in case["turns"])
        assert any("checks" in t for t in case["turns"]), case["id"]
        for turn in case["turns"]:
            assert set(turn.get("checks", {})) <= KNOWN_CHECKS, case["id"]
        if "baseline" in case:
            assert case["baseline"]["kind"] in ("number", "recipes")
