"""P2 (A6): the junk-title filter. Rules are checked on examples; no database needed."""

from types import SimpleNamespace

import numpy as np
import pytest
from test_agent_substitute import U, make_agent  # noqa: F401  (make_agent is a pytest fixture)

from recipebot.normalization.titles import is_junk_title, junk_mask


@pytest.mark.parametrize("title", [
    "Tst", "Tstcgdgdgdgdgdgdgd", "trrr", "ttt", "QA", "KCB ", "ab", "", None, "  ", "xxxxxxxxx", "Qwrtpsdfghk soup"])
def test_test_records_are_junk(title):
    assert is_junk_title(title)


@pytest.mark.parametrize("title", [
    "Banana Bread", "BLT", "BBQ Ribs", "Pie", "Mango Relish", "Chiles Rellenos", "Crêpes Suzette",
    "Spaghetti alla Carbonara", "Schnitzel", "Strengths Stew", "Mac & Cheese", "7-Up Cake",
    "寿司", "Fish Fry (Southern)", "Pb&j Bites",
    "Momma's Mmm-Mmm-Magnificent Meatloaf", "Mmmmmmmud Pie", "CBLT'S", "\"Pbj's\" "])
def test_real_titles_are_kept(title):
    assert not is_junk_title(title)


def test_junk_mask_keeps_the_input_order():
    assert junk_mask(["Banana Bread", "Tst", None, "Pie"]
                     ).tolist() == [False, True, True, False]


def test_thresholds_can_be_changed():
    assert not is_junk_title(
        "Pie", min_letters=3) and is_junk_title("Pie", min_letters=4)
    assert is_junk_title("Strengths", max_run=5) and not is_junk_title(
        "Strengths", max_run=9)


def test_the_answer_says_how_many_recipes_are_hidden(make_agent):
    agent = make_agent(U("search"))
    # no filter on a fake retriever
    assert agent._quality_note() == ""
    agent.retriever.junk = np.array([True, False, True])
    note = agent._quality_note("\n")
    assert note.startswith(
        "\nQuality filter: 2 recipes") and "statistics counts include them" in note
    agent.retriever.junk = np.zeros(3, dtype=bool)
    assert agent._quality_note() == ""
