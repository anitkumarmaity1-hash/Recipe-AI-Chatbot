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
the pass count from eval_report.md;
the count case: what the one-shot LLM said versus your 10,062, taken from baseline_report.md;
one sentence that the three recipe questions got no verifiable IDs from the one-shot LLM.

## Problems found while building, and what changed
- Replacing eggs in a 4-ingredient banana bread picked peanut butter, supported by two ice-cream recipes. Fix: same-dish-name evidence and a minimum-evidence gate (`docs/DESIGN.md` section 10).
- "Replace the cream in a penne recipe" returned a recipe with cream cheese only and then failed. Fix: the recipe search requires the ingredient.
- "I also have rice" dropped the step limit in an early version of matching (fixed in step 10b).
- Known and not fixed: junk-titled recipes from the source data can appear in results; "vegan" cannot be enforced; percentages always use the whole dataset as the denominator.