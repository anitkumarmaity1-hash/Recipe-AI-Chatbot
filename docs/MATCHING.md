# Ingredient matching (Task 2)

Code: `src/recipebot/tools/matching.py` (SQL + scoring), `src/recipebot/agent/match_composer.py` (answer text).
Weights: `src/recipebot/config.py` (`MATCH_*`).

## Steps
1. Your ingredient words are normalized like dataset lines (quantity removed, plural removed, synonyms and variants mapped). Different forms stay different (garlic is not garlic powder). Unknown words are reported, never ignored silently.
2. An ingredient that you also excluded is dropped and the answer says so.
3. Hard constraints (excluded ingredients, allergen categories, maximum steps) are applied first as a mask. A recipe with no instructions is counted but never ranked.
4. Every remaining recipe that uses at least `MATCH_MIN_MATCHED` of your ingredients is scored.

## Score
    score = W_COVERAGE x coverage - W_EXTRA x extra_ratio - W_STEPS x min(steps, STEP_CAP)
    coverage    = matched / number of ingredients you listed
    extra_ratio = extra required ingredients / ingredients the recipe needs (pantry staples not counted)
Defaults: 4.0, 2.0, 0.1, cap 30. These are design choices, not measured values. Ties: fewer steps, then recipe order.

Each result shows matched, "missing" (you have it, the recipe does not use it), extra needed, pantry staples assumed
(`data/taxonomy/pantry_staples.yaml`), steps and the score arithmetic.

## Hard constraints are never relaxed
If nothing passes, the answer says no recipe was found and that nothing was relaxed. Results are re-verified from the database before they are shown.

## Quantities
Quantities you give are not compared: the answer states that name-level matching was done and that quantity sufficiency was not verified.

## When nothing is eligible: closest alternatives (clearly marked)
If no recipe passes the hard constraints, the answer says so and that nothing was relaxed. It then lists up to `k`
recipes that use your ingredients but BREAK a constraint, under the heading "NOT ELIGIBLE ... VIOLATE a hard
constraint". They use the same score, each one names every rule it breaks with the evidence (the step count, the
excluded ingredient, the ingredient line that contains the allergen word), and they are never counted as results
or selectable as "the first one". A recipe whose violation cannot be proven from the database is not shown.
Code: `RecipeMatcher._closest_violating` in `src/recipebot/tools/matching.py`.