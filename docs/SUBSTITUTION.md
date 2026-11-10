# Substitution evidence and adaptation (Task 3, Steps 11–12)

Evidence mining is Step 11 (`src/recipebot/tools/substitution.py`). Building and independently
validating a separate adapted recipe is Step 12 (`src/recipebot/tools/adaptation.py` and
`src/recipebot/agent/agent.py`).

## What it answers

"Recipe R uses ingredient X. Which ingredients do other recipes in the dataset use instead of
X, and which recipe ids prove it?" No LLM and no embeddings are involved, so the result is
the same every run and every number has a denominator.

## Definitions (change them in `config.py`, `SUB_*`)

| Term | Definition |
|---|---|
| core ingredients | distinct `canonical_base` names of a recipe, without X and without pantry staples |
| similarity | Jaccard overlap of two core sets: shared / (size A + size B - shared) |
| WITH group | recipes that contain X (base or any variant) and have similarity >= 0.30 |
| WITHOUT group | recipes that do not contain X, similarity >= 0.30, obey every hard constraint, have at least one step |
| direct recipe | in the WITHOUT group, similarity >= 0.50 and it shares a title word (generic words like "easy" ignored) |
| indirect recipe | in the WITHOUT group but not direct |
| support | number of WITHOUT recipes that use the substitute |
| enrichment | share of the WITHOUT group using it minus share of the WITH group using it |
| level `direct` | support >= 2 and at least 2 of those recipes are direct |
| level `indirect` | support >= 2 |
| level `none` | anything less: cooking knowledge only, no dataset evidence |

## Rules a substitute must pass

1. Used by at least 2 related recipes without X (data candidates), or listed in `ingredient_roles.yaml` (knowledge candidates, shown with their real evidence, often `none`).
2. Enrichment >= 0.02 (a data candidate that is as common in recipes with X is not a replacement).
3. Shares a cooking role with X, from `data/taxonomy/ingredient_roles.yaml`. When the file has no role for X, this filter is off and the result says so (`role_filter_applied: false`).
4. Not already an ingredient of the original recipe.
5. Not excluded by the user and not matching an excluded allergen. Dropped substitutes are listed in `rejected` with the reason, never silently.

## Hard constraints

Only the WITHOUT group (the cited recipes) is filtered by allergens, excluded ingredients and
maximum steps. The WITH group is not, otherwise "no dairy" would empty the baseline when X is
cream. `residual_conflicts` lists other lines of the original recipe that still break a
constraint after X is replaced (for example butter or Parmesan in a "no dairy" pasta). Such
conflicts are not silently carried into an adapted recipe: Step 12 checks EVERY adapted ingredient
line and instruction step. If any hard exclusion remains, the agent refuses to return the adapted
recipe and does not expose the failed adapted object in its payload. The user can then ask to
replace the additional conflicting ingredient. The chatbot never claims the result is allergy-safe.

## Independent check

`SubstitutionMiner.verify()` re-reads every cited recipe from the database (not through the mask)
and checks: it exists, it does not contain X, it contains the substitute, no excluded ingredient,
no excluded allergen, it has steps and obeys the step limit. The agent runs it on every substitution.
`validate_adaptation()` then checks the whole proposed recipe, including unchanged lines, every
revised instruction, and the substitute name itself. Missing allergen-matcher capability fails closed.

## Honest limits

- `ingredient_roles.yaml` is hand-written general cooking knowledge, not dataset evidence. It is always labelled that way.
- Similarity uses ingredient names, not quantities or methods, so "same dish family" is an approximation.
- Evidence shows other recipes use the substitute; it does not prove the result tastes good in this recipe.
- The roles file may contain names that the dataset spells differently. `--check-taxonomy` lists them.
- Two or more recipes is a low bar chosen for a small take-home; raise `SUB_MIN_SUPPORT` for stricter evidence.
- No medical or allergy-safety claim is made.

## Commands (project root, venv active)

```powershell
python -m recipebot.tools.substitution --check-taxonomy
python -m recipebot.tools.substitution --recipe-id <ID> --replace egg
python -m recipebot.tools.substitution --recipe-id <ID> --replace cream --exclude-allergen dairy
python -m recipebot.tools.substitution --recipe-id <ID> --replace butter --max-steps 8 --json
```

Find a recipe id with `python -m recipebot.retrieval.hybrid "banana bread" -k 5`.

## Interview questions

1. Why is the baseline (WITH) group not filtered by the allergen constraint?
2. Why Jaccard on ingredient names, and what does it miss?
3. Why must a substitute be enriched, not just frequent?
4. What is the difference between "direct" and "indirect" evidence here?
5. Why is the roles file kept separate from dataset evidence?
6. Why does an adaptation get refused when an unchanged line still contains dairy?
7. Why is checking the candidate name itself necessary for egg-free substitutions?