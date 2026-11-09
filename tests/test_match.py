"""Tests for ingredient matching (Step 10, Task 2) and the session state it needs.

Tiny synthetic database, no network, no real data. Scores in the comments are
computed by hand with the default weights (4, 2, 0.1) so the formula is checked,
not just reproduced.
"""

import duckdb
import pytest

from recipebot.agent.state import SessionState
from recipebot.normalization.ingredients import IngredientNormalizer
from recipebot.retrieval.masks import Constraints, build_sql_mask
from recipebot.schemas import Intent, Understanding
from recipebot.tools import matching
from recipebot.tools.matching import MatchSettings, RecipeMatcher, load_staples
from recipebot.tools.stats import RecipeStats
from recipebot.understanding.restrictions import RestrictionMapper

VARIANTS = {"butter": ["unsalted butter", "salted butter"]}
STAPLES = ["salt", "water", "pepper"]

# row_idx, id, title, steps, [(canonical, alternatives), ...]
RECIPES = [
    (0, "a:A", "Egg Tomato Scramble", 4, [
     ("egg", []), ("onion", []), ("tomato", [])]),
    (1, "a:B", "Peanut Egg Rice", 5, [
     ("egg", []), ("onion", []), ("rice", []), ("peanut", [])]),
    (2, "a:C", "Tomato Rice Bake", 6, [
     ("onion", []), ("tomato", []), ("rice", []), ("cheese", [])]),
    (3, "a:D", "Butter Cake", 7, [("unsalted butter", []), ("sugar", []), ("egg", []),
                                  ("flour", []), ("salt", [])]),
    (4, "a:E", "Pancakes", 5, [
     ("flour", []), ("milk", []), ("egg", []), ("salt", []), ("water", [])]),
    (5, "a:F", "No Steps Omelette", 0, [("egg", []), ("salt", [])]),
    (6, "a:G", "Margarine Toast", 2, [
     ("bread", []), ("butter", ["margarine"])]),
    (7, "a:H", "Pepper Steak", 3, [
     ("steak", []), ("salt", []), ("pepper", [])]),
    (8, "a:I", "Garlic Powder Chicken", 3, [
     ("chicken", []), ("garlic powder", [])]),
    (9, "a:J", "Garlic Chicken", 3, [("chicken", []), ("garlic", [])]),
    (10, "a:K", "Margarine Cookies", 4, [("margarine", []), ("sugar", [])]),
]
N = len(RECIPES)


def make_db(path, with_base_column=True):
    base_of = {v: b for b, vs in VARIANTS.items() for v in vs}
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE recipes (id VARCHAR, row_idx INTEGER, title VARCHAR)")
    con.execute(
        "CREATE TABLE recipe_stats (row_idx INTEGER, id VARCHAR, n_steps INTEGER)")
    base_col = "canonical_base VARCHAR, " if with_base_column else ""
    con.execute("CREATE TABLE recipe_ingredient (recipe_id VARCHAR, row_idx INTEGER, position INTEGER, "
                f"name_index INTEGER, canonical VARCHAR, {base_col}alternatives VARCHAR[])")
    for row_idx, rid, title, steps, lines in RECIPES:
        con.execute("INSERT INTO recipes VALUES (?, ?, ?)",
                    [rid, row_idx, title])
        con.execute("INSERT INTO recipe_stats VALUES (?, ?, ?)",
                    [row_idx, rid, steps])
        for pos, (canonical, alternatives) in enumerate(lines):
            if with_base_column:
                con.execute("INSERT INTO recipe_ingredient VALUES (?, ?, ?, 0, ?, ?, ?)",
                            [rid, row_idx, pos, canonical, base_of.get(canonical, canonical), alternatives])
            else:
                con.execute("INSERT INTO recipe_ingredient VALUES (?, ?, ?, 0, ?, ?)",
                            [rid, row_idx, pos, canonical, alternatives])
    con.close()
    return path


@pytest.fixture()
def matcher(tmp_path):
    con = duckdb.connect(str(make_db(tmp_path / "m.duckdb")), read_only=True)
    stats = RecipeStats(con, variants=VARIANTS)
    yield RecipeMatcher(con, stats, staples=STAPLES, normalizer=IngredientNormalizer({}))
    con.close()


def run(matcher, available, constraints=None, k=20):
    constraints = constraints or Constraints()
    mask, sql, _ = build_sql_mask(matcher.stats, N, constraints)
    return matcher.match(available, constraints, mask, sql, k=k)


def ids(res):
    return [h.id for h in res.hits]


def hit(res, rid):
    return next(h for h in res.hits if h.id == rid)


# ---- the assignment's A / B / C example ----------------------------------------------
def test_assignment_example_ranks_a_before_c_and_rejects_b_for_peanut(matcher):
    res = run(matcher, ["egg", "onion", "tomato"],
              Constraints(exclude=("peanut",)))
    # A 3.60 (all 3 matched, nothing extra, 4 steps)   C 1.07   E -0.50   D -0.87
    assert ids(res) == ["a:A", "a:C", "a:E", "a:D"]
    assert "a:B" not in ids(res)
    c = hit(res, "a:C")
    assert (c.matched, c.unused, c.extra) == (
        ["onion", "tomato"], ["egg"], ["rice", "cheese"])
    assert c.score == pytest.approx(4 * (2 / 3) - 2 * (2 / 4) - 0.1 * 6)
    assert hit(res, "a:A").score == pytest.approx(3.6)


def test_counts_state_the_denominators(matcher):
    res = run(matcher, ["egg", "onion", "tomato"],
              Constraints(exclude=("peanut",)))
    # A, B, C, D, E, F use at least one ingredient; B (peanut) and F (0 steps) drop out
    assert (res.n_total, res.n_candidates, res.n_eligible) == (N, 6, 4)


def test_every_score_follows_the_documented_formula(matcher):
    res = run(matcher, ["egg", "flour", "milk"])
    for h in res.hits:
        expected = 4 * h.coverage - 2 * \
            h.extra_ratio - 0.1 * min(h.n_steps, 30)
        assert h.score == pytest.approx(expected)
        assert h.coverage == pytest.approx(h.n_matched / 3)


# ---- pantry staples -------------------------------------------------------------------
def test_staples_the_user_did_not_list_are_shown_but_never_extra(matcher):
    res = run(matcher, ["flour", "egg"])
    e = hit(res, "a:E")
    assert (e.matched, e.extra, e.staples) == (
        ["flour", "egg"], ["milk"], ["salt", "water"])
    # flour, egg, milk; salt and water are not counted
    assert e.n_core == 3


def test_a_staple_the_user_lists_is_matched_like_any_ingredient(matcher):
    res = run(matcher, ["salt", "flour"])
    e = hit(res, "a:E")
    assert e.matched == ["salt", "flour"]
    assert e.staples == ["water"] and e.n_core == 5 - \
        1   # water still not counted


# ---- forms, variants, alternatives --------------------------------------------------------
def test_variant_forms_of_butter_match_in_both_directions(matcher):
    # recipe has unsalted butter
    assert {"a:D", "a:G"} <= set(ids(run(matcher, ["butter"])))
    both = run(matcher, ["unsalted butter"])
    assert {"a:D", "a:G"} <= set(ids(both)) and both.terms == [
        "butter"]    # recipe says plain butter


def test_a_line_with_alternatives_is_satisfied_by_either_name(matcher):
    res = run(matcher, ["margarine"])
    toast = hit(res, "a:G")
    assert toast.matched == ["margarine"] and toast.extra == ["bread"]
    assert "a:K" in ids(res)


def test_different_forms_stay_different(matcher):
    res = run(matcher, ["garlic"])
    assert "a:J" in ids(res) and "a:I" not in ids(
        res)           # garlic != garlic powder


# ---- hard constraints ---------------------------------------------------------------------
def test_recipes_without_instructions_are_counted_but_never_ranked(matcher):
    res = run(matcher, ["egg"])
    assert "a:F" not in ids(res)
    assert res.n_candidates - res.n_eligible >= 1


def test_max_steps_is_enforced(matcher):
    res = run(matcher, ["egg", "onion", "tomato"], Constraints(max_steps=4))
    assert ids(res) == ["a:A"] and all(h.n_steps <= 4 for h in res.hits)


def test_no_eligible_recipe_says_so_and_relaxes_nothing(matcher):
    res = run(matcher, ["rice"], Constraints(
        include=("peanut",), exclude=("peanut",)))
    assert res.hits == [] and res.n_candidates > 0 and res.n_eligible == 0
    assert "nothing was relaxed" in res.note


# ---- reading the user's words ---------------------------------------------------------------
def test_unknown_excluded_and_quantity_words(matcher):
    res = run(matcher, ["2 Eggs", "zorblax", "onions",
              "Tomatoes"], Constraints(exclude=("onion",)))
    assert res.terms == ["egg", "tomato"]
    assert [u["term"] for u in res.unknown] == [
        "zorblax"] and res.dropped == ["onion"]


def test_nothing_usable_gives_a_note_and_no_hits(matcher):
    res = run(matcher, ["zorblax"])
    assert res.hits == [] and res.terms == [] and "could be used" in res.note


def test_duplicate_terms_and_variants_count_once(matcher):
    res = run(matcher, ["butter", "unsalted butter", "Butter"])
    assert res.terms == ["butter"]


# ---- determinism, k, settings -----------------------------------------------------------------
def test_results_are_deterministic_and_k_is_respected(matcher):
    first = ids(run(matcher, ["egg", "flour"], k=3))
    assert len(first) == 3 and first == ids(
        run(matcher, ["egg", "flour"], k=3))


def test_weights_come_from_the_settings(matcher):
    heavy = RecipeMatcher(matcher.con, matcher.stats, staples=STAPLES,
                          normalizer=IngredientNormalizer({}),
                          settings=MatchSettings(w_coverage=0, w_extra=0, w_steps=1, step_cap=30))
    res = run(heavy, ["egg", "onion", "tomato"])
    assert res.hits[0].n_steps == min(h.n_steps for h in res.hits)
    assert [h.n_steps for h in res.hits] == sorted(h.n_steps for h in res.hits)
    assert res.settings["w_steps"] == 1


# ---- SQL versus an independent pure-Python reference ----------------------------------------------
def reference(user_terms):
    """Straight set logic over the fixture, written without the matcher's helpers."""
    base_of = {v: b for b, vs in VARIANTS.items() for v in vs}
    out = {}
    for row_idx, rid, _title, steps, lines in RECIPES:
        reqs = {}
        for canonical, alternatives in lines:
            base = base_of.get(canonical, canonical)
            entry = reqs.setdefault(
                base, {"staple": False, "covered": False, "terms": set()})
            entry["staple"] |= canonical in STAPLES or base in STAPLES
            for term in user_terms:
                forms = {term, *VARIANTS.get(term, [])}
                if base == term or forms & set(alternatives):
                    entry["covered"] = True
                    entry["terms"].add(term)
        matched = {t for e in reqs.values() for t in e["terms"]}
        if not matched:
            continue
        out[rid] = (sum(1 for e in reqs.values() if not e["staple"] or e["covered"]),
                    sum(1 for e in reqs.values()
                        if not e["staple"] and not e["covered"]),
                    len(matched), steps)
    return out


@pytest.mark.parametrize("user", [["egg"], ["egg", "onion", "tomato"], ["butter"],
                                  ["margarine", "flour"], ["salt", "flour"], ["pepper", "steak", "garlic"]])
def test_sql_counts_equal_the_python_reference(matcher, user):
    terms, _, _ = matcher.prepare_terms(user)
    sql, params = matcher._candidate_query(terms)
    rows = matcher.con.execute(sql, params).fetchall()
    got = {RECIPES[r][1]: (core, extra, matched, steps)
           for r, core, extra, matched, steps in rows}
    assert got == reference([t.base for t in terms])


def test_verify_accepts_real_results_and_catches_a_tampered_one(matcher):
    res = run(matcher, ["egg", "onion", "tomato"])
    assert matcher.verify(res) == []
    res.hits[0].n_matched += 1
    assert any("matched by SQL" in p for p in matcher.verify(res))


# ---- setup errors and the staples file -------------------------------------------------------------
def test_a_database_without_canonical_base_gives_a_clear_error(tmp_path):
    con = duckdb.connect(
        str(make_db(tmp_path / "old.duckdb", with_base_column=False)), read_only=True)
    with pytest.raises(RuntimeError, match="build_normalized"):
        RecipeMatcher(con, RecipeStats(con, variants={}), staples=[])
    con.close()


def test_missing_staples_file_means_no_staples_and_a_warning(tmp_path, caplog):
    assert load_staples(tmp_path / "nope.yaml") == []
    assert "not found" in caplog.text


def test_the_shipped_staples_file_is_valid():
    names = load_staples()
    assert names and all(n == n.lower().strip() for n in names)
    assert {"salt", "water"} <= set(names)


# ---- session state used by matching ------------------------------------------------------------------
MAPPER = RestrictionMapper(
    {"allergen_phrases": {"dairy": ["dairy"]}, "unsupported_phrases": ["vegan"]})


def U(intent, **slots):
    return Understanding(intent=Intent(intent), **slots)


def test_match_sets_the_ingredients_and_the_mode_and_refine_keeps_them():
    st = SessionState()
    st.apply(U("match", available=["egg", "flour"],
             include=["milk"], max_steps=6), MAPPER)
    assert (st.available, st.mode, st.include, st.max_steps) == (
        ["egg", "flour"], "match", ["milk"], 6)
    st.apply(U("refine", exclude=["dairy"]), MAPPER)
    assert st.mode == "match" and st.available == [
        "egg", "flour"] and st.exclude_allergens == ["dairy"]


def test_a_new_ingredient_list_resets_one_search_settings_but_not_exclusions():
    st = SessionState()
    st.apply(U("match", available=["egg"],
             max_steps=6, exclude=["dairy"]), MAPPER)
    changes = st.apply(U("match", available=["rice"]), MAPPER)
    assert st.available == [
        "rice"] and st.max_steps is None and st.exclude_allergens == ["dairy"]
    assert any("New search" in c for c in changes)


def test_match_without_a_list_keeps_the_previous_one():
    st = SessionState()
    st.apply(U("match", available=["egg"]), MAPPER)
    st.apply(U("match", max_steps=5), MAPPER)
    assert st.available == ["egg"] and st.max_steps == 5


def test_a_text_search_switches_back_and_clear_filters_keeps_the_ingredients():
    st = SessionState()
    st.apply(U("match", available=["egg"], exclude=["dairy"]), MAPPER)
    st.apply(U("search", dish_query="pasta"), MAPPER)
    assert st.mode == "search"
    st.apply(U("clear_filters"), MAPPER)
    assert st.available == ["egg"] and st.exclude_allergens == []


def test_the_prompt_state_lists_the_ingredients_only_when_there_are_some():
    st = SessionState()
    assert "available" not in st.to_prompt_state()
    st.apply(U("match", available=["egg", "flour"]), MAPPER)
    assert st.to_prompt_state()["available"] == ["egg", "flour"]


def test_module_exposes_the_quantity_sentence_required_by_the_assignment():
    assert matching.QUANTITY_NOTE == ("Ingredient names match, but quantity sufficiency "
                                      "could not be verified from the dataset.")
