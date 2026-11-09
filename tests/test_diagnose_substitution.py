"""The substitution diagnostic runs on the synthetic database of test_substitution.py."""

import pytest
from test_substitution import ROLES, STAPLES, VARIANTS, make_con

from recipebot.diagnose_substitution import diagnose
from recipebot.tools.stats import RecipeStats
from recipebot.tools.substitution import SubstitutionMiner


@pytest.fixture()
def parts():
    con = make_con()
    yield con, SubstitutionMiner(con, RecipeStats(con, variants=VARIANTS),
                                 staples=STAPLES, roles=ROLES)
    con.close()


def test_diagnose_reports_groups_and_title_check(parts):
    con, miner = parts
    text = "\n".join(diagnose(con, miner, "a:T",
                     "egg", title_like="banana bread"))
    assert "Core ingredients (5)" in text
    assert "WITH egg: 5 recipes" in text and "WITHOUT egg: 8 recipes" in text
    assert "Recipes whose title contains 'banana bread'" in text
    assert "Lowest-scoring recipes" in text


def test_diagnose_handles_a_recipe_with_no_core(parts):
    con, miner = parts
    text = "\n".join(diagnose(con, miner, "a:Z", "egg"))
    assert "No core ingredients" in text
