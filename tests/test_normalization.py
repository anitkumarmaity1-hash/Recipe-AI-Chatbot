"""Step 4 tests (rule layer): regex normalizer, name cleanup, step counting, allergens."""
import pytest

from recipebot.normalization.allergens import AllergenMatcher
from recipebot.normalization.ingredients import IngredientNormalizer, load_synonyms, singularize
from recipebot.normalization.steps import count_lines, count_steps, split_steps

NORMALIZER = IngredientNormalizer(
    {"scallion": "green onion", "garbanzo bean": "chickpea",
        "confectioners sugar": "powdered sugar"}
)


@pytest.mark.parametrize(
    "line, expected",
    [
        ("1/2 medium onion, diced", "onion"),
        ("2 cloves garlic, minced", "garlic"),
        ("1 teaspoon garlic powder", "garlic powder"),
        ("1 (13.5 ounce) can coconut milk", "coconut milk"),
        ("1/2 cup peanut butter", "peanut butter"),
        ("2 tablespoons cocoa butter", "cocoa butter"),
        ("3 large eggs", "egg"),
        ("2 cups all-purpose flour, sifted", "all-purpose flour"),
        ("1 pound ground beef", "ground beef"),
        ("Salt and pepper to taste", "salt and pepper"),
        ("2 tbsp. butter or margarine", "butter"),
        ("4 ripe tomatoes, chopped", "tomato"),
        ("1 bunch scallions", "green onion"),
        ("1 \u00bd cups milk", "milk"),
        ("2 (8 ounce) packages cream cheese, softened", "cream cheese"),
        ("1 1/2 to 2 pounds chicken breasts", "chicken breast"),
        ("1 can (14 ounce) diced tomatoes, drained", "tomato"),
        ("1/4 cup half-and-half", "half-and-half"),
        ("8 oz. spaghetti", "spaghetti"),
        ("2 cups strawberries", "strawberry"),
        ("2 bay leaves", "bay leaf"),
        ("1 tablespoon molasses", "molasses"),
        ("To taste", ""),
        ("", ""),
    ],
)
def test_regex_canonical_names(line, expected):
    assert NORMALIZER.canonical(line) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("fresh basil leaves", "basil leaf"),
        ("ripe tomatoes", "tomato"),
        ("Salt", "salt"),
        ("dried oregano", "dried oregano"),
        ("confectioners' sugar", "powdered sugar"),
        ("eggs", "egg"),
        ("coconut milk", "coconut milk"),
        ("garlic powder", "garlic powder"),
    ],
)
def test_normalize_name_for_parser_output(name, expected):
    assert NORMALIZER.normalize_name(name) == expected


def test_forms_stay_distinct():
    assert NORMALIZER.canonical(
        "1 tsp garlic powder") != NORMALIZER.canonical("1 clove garlic")
    assert NORMALIZER.canonical(
        "1 cup coconut milk") != NORMALIZER.canonical("1 cup milk")


def test_canonical_is_cached_and_stable():
    assert NORMALIZER.canonical(
        "3 large eggs") == NORMALIZER.canonical("3 large eggs") == "egg"


@pytest.mark.parametrize(
    "word, expected",
    [("tomatoes", "tomato"), ("berries", "berry"), ("cheeses", "cheese"), ("peaches", "peach"),
     ("radishes", "radish"), ("asparagus",
                              "asparagus"), ("hummus", "hummus"), ("swiss", "swiss"),
     ("molasses", "molasses"), ("eggs",
                                "egg"), ("leaves", "leaf"), ("cookies", "cookie"),
     ("peas", "pea"), ("oats", "oat"), ("pies", "pie")],
)
def test_singularize(word, expected):
    assert singularize(word) == expected


def test_real_synonyms_file_loads():
    assert load_synonyms().get("scallion") == "green onion"


def test_count_steps_basic():
    assert count_steps("Mix the flour. Bake for 20 minutes.") == 2
    assert count_steps("Stir in 1.5 cups of milk. Serve.") == 2
    assert count_steps("") == 0
    assert count_steps(None) == 0
    assert split_steps("   ") == []


def test_count_lines():
    assert count_lines("a\n\nb\n") == 2
    assert count_lines("") == 0


MATCHER = AllergenMatcher()  # uses data/taxonomy/allergens.yaml


@pytest.mark.parametrize(
    "line, allergen, expected",
    [
        ("1 cup whole milk", "dairy", True),
        ("1 (14 ounce) can coconut milk", "dairy", False),
        ("2 tablespoons butter", "dairy", True),
        ("1/2 cup peanut butter", "dairy", False),
        ("1/2 cup peanut butter", "peanut", True),
        ("2 tablespoons cocoa butter", "dairy", False),
        ("1 teaspoon cream of tartar", "dairy", False),
        ("1 cup heavy cream", "dairy", True),
        ("1 butternut squash", "dairy", False),
        ("1 cup buttermilk", "dairy", True),
        ("1 cup almond milk", "dairy", False),
        ("1 cup almond milk", "tree_nut", True),
        ("2 eggs", "egg", True),
        ("1 eggplant, sliced", "egg", False),
        ("1 cup all-purpose flour", "gluten", True),
        ("1 cup rice flour", "gluten", False),
        ("1 pound spaghetti", "gluten", True),
    ],
)
def test_allergen_matching(line, allergen, expected):
    assert bool(MATCHER.matches(line, allergen)) is expected


def test_allergen_detect_and_unknown():
    assert set(MATCHER.detect("1/2 cup peanut butter")) == {"peanut"}
    assert "dairy" in MATCHER.detect(
        "butter or margarine")  # the FULL line is checked
    with pytest.raises(KeyError):
        MATCHER.matches("x", "unicorn")
