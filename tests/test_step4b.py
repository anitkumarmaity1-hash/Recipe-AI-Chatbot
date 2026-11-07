"""Step 4b tests: line filter, extra descriptors, variant map, cached step table."""
import duckdb
import pytest

from recipebot.build_db import build_database
from recipebot.build_normalized import build_parse_cache, build_recipe_tables
from recipebot.normalization.ingredients import IngredientNormalizer, load_extra_descriptors
from recipebot.normalization.line_filter import DROP, KEEP, STRIP, LineFilter, load_line_filter
from recipebot.tools.stats import load_variants

FILTER = LineFilter(
    drop=["special equipment", "equipment", "ingredient info", "note", "serving suggestion",
          "accompaniment"],
    strip=["garnish", "optional garnish", "optional", "toppings"],
)


@pytest.mark.parametrize(
    "line, action, prefix, text",
    [
        ("Special equipment: Eight 6-ounce aluminum tins",
         DROP, "special equipment", ""),
        ("SPECIAL EQUIPMENT: Eight tins", DROP, "special equipment", ""),
        ('**Special Equipment:**10" springform pan', DROP, "special equipment", ""),
        ("Special equipment : a 1- to 1 1/2-quart teapot",
         DROP, "special equipment", ""),
        ("Serving Suggestion: Tartar sauce", DROP, "serving suggestion", ""),
        ("Garnish: 1 (1 1/2-inch-long) lemon twist", STRIP,
         "garnish", "1 (1 1/2-inch-long) lemon twist"),
        ("Optional garnish: 1/2 cup pomegranate seeds", STRIP,
         "optional garnish", "1/2 cup pomegranate seeds"),
        ("Optional: 1 jalapeno, chopped", STRIP, "optional", "1 jalapeno, chopped"),
        ("Garnish:", DROP, "garnish", ""),
        ("1 teaspoon hot sauce (recommended: Frank's Red Hot)", KEEP, None, ""),
        ("Notes on the dough", KEEP, None, ""),
    ],
)
def test_line_decisions(line, action, prefix, text):
    decision = FILTER.classify(line)
    assert (decision.action, decision.prefix,
            decision.text) == (action, prefix, text)


def test_real_line_filter_file():
    real = load_line_filter()
    assert real.classify("Special equipment: a pan").action == DROP
    assert real.classify("Garnish: 1 lemon").action == STRIP
    assert real.classify("2 cups flour").action == KEEP


EXTRA = {"homemade", "store-bought", "reduced-sodium"}


def test_extra_descriptors_removed():
    norm = IngredientNormalizer({}, EXTRA)
    assert norm.normalize_name("homemade chicken stock") == "chicken stock"
    assert norm.normalize_name("store-bought pizza dough") == "pizza dough"
    assert norm.normalize_name("reduced-sodium soy sauce") == "soy sauce"
    assert norm.canonical("2 cups homemade chicken stock") == "chicken stock"


def test_default_normalizer_unchanged():
    assert IngredientNormalizer({}).normalize_name(
        "homemade chicken stock") == "homemade chicken stock"


def test_real_extra_descriptors_file():
    words = load_extra_descriptors()
    assert "homemade" in words
    assert "light" not in words and "dried" not in words


def test_real_variants_file():
    variants = load_variants()
    assert "unsalted butter" in variants["butter"]
    assert "peanut butter" not in variants["butter"]


def _raw():
    return {
        "ar": {
            "r1": {
                "title": "Cake",
                "ingredients": ["Special equipment: 9-inch pan", "Garnish: 1 lemon",
                                "1 cup unsalted butter", "2 large eggs"],
                "instructions": "Mix the flour. Bake it.",
            },
            "r2": {"title": "Toast", "ingredients": ["2 slices bread"], "instructions": ""},
        }
    }


def test_stage_b_filter_variants_and_cached_steps(tmp_path):
    pytest.importorskip("ingredient_parser")
    from recipebot.normalization.parser_layer import warmup

    warmup()
    db_path = tmp_path / "tiny.duckdb"
    build_database(_raw(), db_path)
    build_parse_cache(db_path)
    norm = IngredientNormalizer({})
    variants = {"butter": ["unsalted butter"]}

    first = build_recipe_tables(
        db_path, norm, line_filter=FILTER, variants=variants)
    assert first.steps_recomputed is True
    assert dict(first.dropped_by_prefix) == {"special equipment": 1}
    assert dict(first.stripped_by_prefix) == {"garnish": 1}

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT canonical, canonical_base FROM recipe_ingredient "
            "WHERE recipe_id = 'ar:r1' ORDER BY position"
        ).fetchall()
        assert rows == [("lemon", "lemon"),
                        ("unsalted butter", "butter"), ("egg", "egg")]
        assert con.execute(
            "SELECT n_ingredients, n_steps FROM recipe_stats WHERE id = 'ar:r1'"
        ).fetchone() == (3, 2)  # 4 lines minus 1 dropped note
        assert con.execute(
            "SELECT count(*) FROM recipe_steps").fetchone()[0] == 2
    finally:
        con.close()

    # second run reuses the cached step table; --recount-steps forces a recompute
    assert build_recipe_tables(
        db_path, norm, line_filter=FILTER, variants=variants).steps_recomputed is False
    assert build_recipe_tables(
        db_path, norm, line_filter=FILTER, variants=variants, recount_steps=True
    ).steps_recomputed is True
