"""Step 3 tests: cleaning rules and database build, on small synthetic records."""
import copy

import duckdb

from recipebot.build_db import build_database
from recipebot.cleaning import (
    REASON_DUPLICATE,
    REASON_NO_INGREDIENTS,
    REASON_NO_TITLE,
    REASON_NO_USABLE,
    clean_ingredient_line,
    clean_ingredients,
    process_sources,
    undouble_instructions,
)


def rec(title="T", ingredients=("1 cup flour",), instructions="Mix. Bake."):
    return {"title": title, "ingredients": list(ingredients), "instructions": instructions}


A1 = rec("Pancakes", ["1 cup flour ADVERTISEMENT", "2 eggs ADVERTISEMENT", "ADVERTISEMENT", "TOPPING:", "syrup"],
         "Mix. Cook.")


def make_raw():
    ar = {
        "a1": copy.deepcopy(A1),
        "a2": rec("", ["x"]),                                  # empty title
        # empty ingredient list
        "a3": rec("No ingredients", []),
        # nothing usable left
        "a4": rec("Only ads", ["ADVERTISEMENT", "FOR THE SAUCE:"]),
        # exact duplicate of a1
        "a5": copy.deepcopy(A1),
        # same title, different content: kept
        "a6": rec("Pancakes", ["3 apples"], "Peel."),
        # empty instructions: kept, flagged
        "a7": rec("No steps", ["1 egg"], ""),
        "a8": {"title": "", "ingredients": [], "instructions": ""},
        # identical to a8, must not count as duplicate
        "a9": {"title": "", "ingredients": [], "instructions": ""},
    }
    epi = {
        # doubled instructions
        "e1": rec("Soup", ["water", "salt"], "Boil.\nBoil."),
        # cross-file duplicate of ar:a1
        "e2": copy.deepcopy(A1),
    }
    return {"ar": ar, "epi": epi}


def reasons(result):
    return {e["id"]: e["reason"] for e in result.excluded}


def test_clean_ingredient_line_strips_advertisement():
    assert clean_ingredient_line("1 cup flour ADVERTISEMENT") == (
        "1 cup flour", "ad_stripped")
    assert clean_ingredient_line(
        "2 eggs\nADVERTISEMENT") == ("2 eggs", "ad_stripped")
    assert clean_ingredient_line("  1 onion ") == ("1 onion", "kept")


def test_clean_ingredient_line_drops_ad_only_header_empty():
    assert clean_ingredient_line("ADVERTISEMENT")[1] == "ad_only"
    assert clean_ingredient_line("TOPPING:")[1] == "header"
    assert clean_ingredient_line("   ")[1] == "empty"
    assert clean_ingredient_line(None)[1] == "empty"
    assert clean_ingredients(
        ["a ADVERTISEMENT", "ADVERTISEMENT", "SAUCE:", "b"]) == ["a", "b"]


def test_undouble_exact_copy():
    assert undouble_instructions("Boil.\nBoil.") == ("Boil.", True)
    assert undouble_instructions(
        "Mix well. Bake.\nMix well. Bake.\n") == ("Mix well. Bake.", True)


def test_undouble_leaves_other_text():
    assert undouble_instructions("Boil.\nSimmer.") == ("Boil.\nSimmer.", False)
    assert undouble_instructions("abc") == ("abc", False)
    assert undouble_instructions("") == ("", False)


def test_process_counts_add_up():
    raw = make_raw()
    result = process_sources(raw)
    total_raw = sum(len(v) for v in raw.values())
    assert total_raw == 11
    assert len(result.usable) + len(result.excluded) == total_raw
    assert [u["id"] for u in result.usable] == [
        "ar:a1", "ar:a6", "ar:a7", "epi:e1"]
    assert result.stats["ar"]["raw_records"] == 9
    assert result.stats["epi"]["raw_records"] == 2


def test_process_reasons():
    result = process_sources(make_raw())
    r = reasons(result)
    assert r["ar:a2"] == REASON_NO_TITLE
    assert r["ar:a3"] == REASON_NO_INGREDIENTS
    assert r["ar:a4"] == REASON_NO_USABLE
    assert r["ar:a5"] == REASON_DUPLICATE
    assert r["epi:e2"] == REASON_DUPLICATE
    assert len(r) == 7


def test_empty_records_not_counted_as_duplicates():
    result = process_sources(make_raw())
    r = reasons(result)
    assert r["ar:a8"] == REASON_NO_TITLE
    assert r["ar:a9"] == REASON_NO_TITLE          # not exact_duplicate
    assert sum(1 for v in r.values() if v == REASON_DUPLICATE) == 2


def test_duplicates_keep_first_and_never_by_title():
    result = process_sources(make_raw())
    dups = {e["id"]: e["duplicate_of"]
            for e in result.excluded if e["reason"] == REASON_DUPLICATE}
    assert dups == {"ar:a5": "ar:a1", "epi:e2": "ar:a1"}
    kept_ids = {u["id"] for u in result.usable}
    # both "Pancakes", different content
    assert {"ar:a1", "ar:a6"} <= kept_ids


def test_empty_instructions_kept_and_flagged():
    result = process_sources(make_raw())
    by_id = {u["id"]: u for u in result.usable}
    assert by_id["ar:a7"]["instructions_empty"] is True
    assert by_id["ar:a1"]["instructions_empty"] is False
    assert result.stats["ar"]["empty_instructions"] == 1


def test_doubled_instructions_cleaned_only():
    result = process_sources(make_raw())
    e1 = {u["id"]: u for u in result.usable}["epi:e1"]
    assert e1["instructions"] == "Boil.\nBoil."          # original untouched
    assert e1["instructions_clean"] == "Boil."
    assert e1["instructions_was_doubled"] is True
    assert result.stats["epi"]["doubled_instructions"] == 1


def test_originals_untouched():
    result = process_sources(make_raw())
    a1 = {u["id"]: u for u in result.usable}["ar:a1"]
    assert a1["title"] == A1["title"]
    # still contains ADVERTISEMENT
    assert a1["ingredients"] == A1["ingredients"]
    assert a1["instructions"] == A1["instructions"]
    assert a1["ingredients_clean"] == ["1 cup flour", "2 eggs", "syrup"]
    assert result.stats["ar"]["lines_ad_only"] == 3      # a1, a4, a5
    assert result.stats["ar"]["lines_header"] == 3


def test_row_idx_contiguous_and_ordered():
    result = process_sources(make_raw())
    assert [u["row_idx"] for u in result.usable] == [0, 1, 2, 3]


def test_build_database_end_to_end(tmp_path):
    db_path = tmp_path / "test.duckdb"
    result, check_lines = build_database(make_raw(), db_path)
    assert db_path.exists()
    assert not (tmp_path / "test.duckdb.tmp").exists()
    assert len(check_lines) >= 6
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM recipes").fetchone()[0] == 4
        assert con.execute(
            "SELECT count(*) FROM recipes_excluded").fetchone()[0] == 7
        assert con.execute("SELECT ingredients_clean FROM recipes WHERE id = 'ar:a1'").fetchone()[0] == [
            "1 cup flour", "2 eggs", "syrup"]
    finally:
        con.close()
