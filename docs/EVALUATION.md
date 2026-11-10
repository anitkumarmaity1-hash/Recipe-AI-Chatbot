# Evaluation

## How to reproduce
    python eval/run_eval.py        # 11 cases, real data, writes eval/results/eval_report.md
    python eval/baseline.py        # same questions to Gemini alone, writes eval/results/baseline_report.md
    pytest                         # unit tests on synthetic data

The set is `eval/golden.json`: 11 cases over the three tasks, including multi-turn follow-ups, an aggregate
statistics question, a no-match case, two refusals, and substitution with weak evidence. A case passes only if
every check passes. Checks (`eval/checks.py`) read facts back from the database instead of trusting the chatbot:
recipe ids must exist, step limits and allergens are re-checked line by line, and the output guard must be clean.
Numbers marked "pinned" in `golden.json` were read from the author's own build and act as regression checks.

## What the evaluation does not measure
Retrieval quality (no relevance labels), taste or texture of substitutions, and understanding accuracy over many
phrasings: the set is small on purpose. Allergen detection reads ingredient text only.

## One-shot LLM baseline
The same Gemini model is asked each question once, with no database. A number is correct only if it equals the
computed value; recipe answers count as grounded only if every cited id exists. Report: `eval/results/baseline_report.md`.

## Results of the last run
**Chatbot: 10 of 11 cases passed** (`eval/results/eval_report.md`).

| Task | Cases | Passed |
|---|---|---|
| 1 (search, statistics, refusals) | 5 | 5 |
| 2 (ingredient matching) | 3 | 3 |
| 3 (substitution) | 2 | 1 |

**What worked:** the garlic-and-onion count (10,062 of 121,896 usable recipes, 8.3%), the fewest-steps ranking
over all 6,012 tomato recipes with at least one step, both refusals (cooking time, calories), the no-match case,
the "Exclude eggs too" follow-up that keeps the step limit, and the banana-bread substitution with cited evidence.

**What failed:** `T3-sub-cream-pasta` (the assignment's own example). The recipe chosen for "penne pasta" also
contained butter and parmesan, so the independent final-recipe check refused to present an adapted recipe. The
refusal is correct, because the adapted recipe would still contain dairy, but the case still fails: the system does
not yet pick a recipe where cream is the only dairy ingredient, or try the next candidate.

**One-shot baseline (same model, no database):**

| Question | One-shot LLM | Computed / chatbot |
|---|---|---|
| Recipes with garlic and onion | "77,104 recipes, 61.68%" | 10,062 recipes, 8.3% of 121,896 |
| Five tomato recipes with fewest steps | five ids (`0000a6e344`, ...) that are not in the dataset's id format | ranked from the full filtered set, ids exist |
| Match with eggs, onions, tomatoes, rice | no verifiable recipe ids | eligible ids with matched and missing ingredients |
| Egg-free banana bread | no verifiable recipe ids | evidence ids, or an honest weak-evidence answer |

The one-shot model gave a confident, wrong count and invented recipe ids. The chatbot computes the count in code
and the output guard rejects any id that is not in the database.

## Problems found while building, and what changed
- Replacing eggs in a 4-ingredient banana bread picked peanut butter, supported by two ice-cream recipes. Fix: same-dish-name evidence and a minimum-evidence gate (`docs/DESIGN.md` section 10).
- "Replace the cream in a penne recipe" returned a recipe with cream cheese only and then failed. Fix: the recipe search requires the ingredient.
- "I also have rice" dropped the step limit in an early version of matching (fixed in step 10b).
- Known and not fixed: recipe choice for substitution does not prefer recipes whose only restricted ingredient is the one being replaced (the cream failure above); a restriction added after a substitution starts a new search instead of applying to the adaptation; junk-titled recipes can still appear in some results; "vegan" cannot be enforced; percentages always use the whole dataset as the denominator.