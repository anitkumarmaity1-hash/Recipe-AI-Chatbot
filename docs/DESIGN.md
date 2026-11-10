# Design notes (living document)

## 1. Data and IDs
- Three files, each a JSON object keyed by a hash. Recipe ID = `{source}:{key}` (`ar:`, `epi:`, `fn:`), so IDs are unique even if hashes ever collide across files.
- Raw records read: 125,164 (AllRecipes 39,802; Epicurious 25,323; Food Network 60,039).
- Raw files in `data/raw/` are never modified. Original columns in DuckDB are verified identical to them at build time.

## 2. Cleaning rules (Step 3, applied and verified)
| Rule | Evidence from the real data |
|---|---|
| Strip ADVERTISEMENT from ingredient lines; drop lines that are only ADVERTISEMENT | AllRecipes: 358,409 lines stripped, 39,519 ad-only lines dropped; 2,883 header lines also carried it. Total 400,811 of 400,846 AR lines, matching the EDA |
| Drop section headers ending with ":" from the cleaned list | 3,793 lines (AR 2,883; Epi 33; FN 877) |
| Exact-match undoubling of instructions (cleaned column only) | 5,173 Epicurious (about 20% of that source) and 72 Food Network records; none in AllRecipes. Not systematic, so only exact matches are touched |
| Exclude records with no title / no ingredients / nothing usable after cleaning | 569 empty title, 1,624 empty ingredient list, 3 with no usable ingredient |
| Exclude exact duplicates (first kept); empty records are excluded before duplicate detection; never dedupe by title | 1,072 exact duplicates (AR 15, Epi 47, FN 1,010) |
| Keep recipes with empty instructions, flagged | 33 kept (Epi 15, FN 18) |
- Result: 121,896 usable + 3,268 excluded = 125,164. Excluded records stay in `recipes_excluded` with a reason.

## 3. Step-counting rule
- One step = one sentence of `instructions_clean`, split with pysbd. Empty instructions = 0 steps.
- `n_lines` is stored beside `n_steps` as evidence. Comparison numbers: see `docs/NORMALIZATION_REPORT.md` (generated in Step 4).

## 4. Ingredient normalization: hybrid design (user decision)
- **Why hybrid:** regex alone is hard to maintain over ~125k recipes; a parser gives structure (name, quantity, unit, preparation, comment, purpose); our own rules keep control of forms and synonyms.
- **Parser layer:** `ingredient-parser-nlp` (verified on v2.9.2). Run once per unique cleaned line; raw output cached in table `ingredient_parse`.
- **Rule layer:** descriptor removal, singular form of the last word, `synonyms.yaml`, decision between alternatives (" or ") and required multi-name lines ("salt and pepper").
- **Fallback:** if the parser fails or returns no name, the regex normalizer is used. The regex answer is always stored (`regex_canonical`) so disagreements can be audited.
- **Known library quirks:** raises IndexError on empty input (caught); `parse_multiple_ingredients` failed with its default units system in 2.9.2 (not used); first use downloads a small NLTK tagger.
- Canonical names are used for counting and matching; allergen checks use the full cleaned line.
- Different forms stay distinct (garlic vs garlic powder; coconut milk vs milk).
- Quantities and units are stored (`quantity`, `unit`) for later use; whether they support reliable comparison is decided in the matching step.

## 5. Allergen policy
- Hand-written YAML taxonomy with include terms and exception phrases.
- Limits: hidden ingredients are not detected; the gluten list is a rough proxy. Answers must never claim medical safety.

## 6. Open items
- Tune rules from the Step 4 report (top names, parser-vs-regex disagreements, low-confidence names, skipped lines).
- Decide how "contains X" is defined for statistics answers (canonical match vs word match) after reviewing the report.

## 7. Hybrid retrieval (Step 7)
- **Order of operations:** hard constraints first (a boolean "allowed" mask over `row_idx`), then BM25 and FAISS rankings restricted to allowed recipes, then Reciprocal Rank Fusion. A forbidden recipe can never be ranked, so a constraint is never "relaxed by accident".
- **RRF:** `score(d) = sum over rankings of weight / (k + rank)`, rank starting at 1, `k = 60`, equal weights, 200 candidates per retriever. All four values are in `src/recipebot/retrieval/common.py` and are untuned.
- **Why RRF:** BM25 scores (about 5 to 15) and cosine similarities (0 to 1) are on different scales; RRF uses only ranks, so no score normalisation is needed.
- **Constraint sources:** SQL over `recipe_stats` / `recipe_ingredient` (required ingredients, excluded ingredients, maximum steps; same "contains" definition as the statistics tool) and allergen categories checked on the full cleaned ingredient line.
- **Allergen flags** are computed once per recipe in Python and cached in `data/index/allergen_flags.npz`; the cache stores the recipe-ID fingerprint and a hash of `allergens.yaml`, so a changed database or taxonomy triggers a rescan.
- **Maximum steps:** a recipe with 0 steps (no usable instructions) is not eligible for a maximum-steps constraint, because its length is unknown.
- **Semantic search with a mask:** the FAISS index is exact (`IndexFlatIP`), so we search all vectors, drop forbidden ones and keep the first 200. Simple, and it cannot lose an allowed recipe when the constraint is restrictive.
- **Negation:** neither retriever understands "without eggs". The understanding layer (Step 8) must turn it into a constraint; the query text sent to the retrievers is the dish only.
- **Unknown ingredient in a constraint** raises `UnknownIngredientError` with suggestions; it is never ignored silently.
- **Independent verification:** `HybridRetriever.verify()` re-checks returned recipes without using the mask (allergens line by line, steps and ingredients from the database). Tests assert it returns no violations; the output guard will reuse it.
- **Limits:** allergen detection is a text check (hidden ingredients are not found); equal RRF weights and `k = 60` are defaults, not tuned; no evaluation of retrieval quality yet (planned with the golden set, Step 14).

## 8. Understanding layer (Step 8)
- **Job of the LLM:** turn one user message into an `Understanding` (an intent plus slots, `src/recipebot/schemas.py`). It never produces recipe facts, counts or ingredient lists.
- **Structured output:** Gemini is called with `response_mime_type="application/json"`, a JSON schema generated from the dataclass, and temperature 0. A test keeps schema and dataclass identical. "Not given" is `""`, `0` or `"none"` instead of null (a simpler schema for the API).
- **Validation, never guessing:** `Understanding.from_dict` rejects unknown intents, wrong types and negative numbers. Invalid output gets ONE repair attempt (the model sees its own error), then `UnderstandingError`.
- **Safety decisions are not made by the model:** the model copies phrases such as "dairy" or "butter" into `exclude`; `RestrictionMapper` plus `data/taxonomy/restriction_terms.yaml` decides whether each phrase is an allergen category, an ingredient or an unsupported diet. "nuts" blocks both peanut and tree_nut. Vegan, keto and similar are reported as not enforceable.
- **Made-up recipe ids are dropped:** `target_recipe_id` must appear in the session state's `last_results` or `active_recipe`.
- **Failures:** 429 / 5xx / network errors are retried with backoff (`GEMINI_MAX_RETRIES`); other API errors fail immediately; the API key is scrubbed from error messages.
- **Backend switch:** `UNDERSTANDING_BACKEND=gemini|lora`; `lora` raises a clear "built in Step 13" error until then.
- **Models (docs page read on 2026-11-08):** stable `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`; `gemini-2.0-*` already shut down; `gemini-2.5-*` restricted to earlier users. Free-tier rate limits were NOT verified (the limits page I could read was outdated); check them in AI Studio.
- **Limits:** the first call against the real API is the author's smoke test; prompt examples are not an evaluation. Understanding accuracy is measured later on the golden conversations (Step 14).

## 9. Agent loop, session state and output guard (Step 9)
- **Flow of one message:** keyword refusal (cooking time, calories: no model call) -> understanding (LLM, Step 8) -> merge into `SessionState` -> deterministic tool (`search`, `stats`, `details`) -> composer (templates) -> output guard. Code: `src/recipebot/agent/` (`state.py`, `agent.py`, `composer.py`, `guard.py`) and `src/recipebot/cli.py`.
- **Session rules:** allergen and ingredient exclusions persist until the user removes them ("dairy is fine now" -> `allow`) or clears everything. "Must contain" ingredients and the step limit belong to ONE search: a new search resets them, a refinement adds to them. Statistics and show_details never change restrictions. Phrases that cannot be enforced (vegan) are kept in `unenforced` and printed in every search answer.
- **Follow-ups:** a `refine` without a dish re-runs the last query with the new constraints (the "penne pasta" then "I cannot have dairy" example). If a restriction names an ingredient that is not in the vocabulary, the whole message is rolled back and the user gets suggestions; nothing is ignored silently.
- **Two independent safety nets for search:** the hard constraints are applied as a mask before ranking (Step 7), then `HybridRetriever.verify()` re-checks every returned recipe from the database. If it finds a violation the results are withheld.
- **Statistics policy:** aggregates (count, percentage, mean/median, top ingredients) are computed over the whole dataset using only the filters in the question; the answer says that the session restrictions were not applied. An answer that LISTS recipes (fewest steps) does apply the session restrictions, including allergen categories, through the same mask code as search. It sorts the eligible recipes by `(n_steps, id)`; a test checks that it returns the same ids as `RecipeStats.fewest_steps` when no restriction is active.
- **Dish names in statistics:** "how many pasta recipes" is only answered if the word is an ingredient name in the vocabulary (then it is stated). A dish name such as "banana bread" is refused with suggestions, because the statistics tool filters ingredient names, not titles.
- **Output guard:** recipe ids are printed in square brackets; every bracketed id must come from this turn's tool output and every formatted number the tool returned must appear in the text. Today the composer is deterministic, so this passes by construction; the guard is built now because the optional LLM wording layer can write anything.
- **Recipe details** show the cleaned ingredients and sentence-split steps (the same rule as step counting) and warn if the recipe breaks an active restriction.
- **Later steps:** ingredient matching (Step 10, `docs/MATCHING.md`) and substitution (Steps 11 and 12, section 10 and `docs/SUBSTITUTION.md`) are built. LLM wording of answers is not built: answers are templates.
- **Known limits:** `percentage` always uses "all recipes" as the denominator (the schema has one ingredient list, so "percent of tomato recipes that contain garlic" is not expressible yet); allergen categories cannot be used inside aggregate statistics; the keyword refusal ("how long") can over-refuse a harmless sentence.
- **Latency (measured by the author, Step 7 log):** the semantic part took about 12 to 15 s per query in command-line runs. Part of that is probably the one-time model load inside the first call and part the full 121,896-vector search; this was not separated. The chat loads the model once at start-up and prints per-turn timings with `--debug`, so the real per-turn cost will be measured in Step 9 before anything is changed.

## 10. Substitution evidence rules (Task 3, fixes after the first live runs)
- **Problem seen live:** "replace the eggs" in a 4-ingredient banana bread chose peanut butter, backed by two ice-cream recipes, because related recipes were found by ingredient overlap alone and the pool was tiny.
- **Same dish name counts as related:** a recipe that shares at least `SUB_TITLE_MATCH_MIN_WORDS` (2) non-generic title words with the original is related even with low ingredient overlap, and is "direct" (same dish family). So "Banana Bread" evidence comes from other banana breads and muffins.
- **Evidence gate:** an adapted recipe is built only from a substitute with level direct, or level indirect with at least `SUB_ADAPT_MIN_SUPPORT` (3) recipes. Otherwise the answer says WEAK EVIDENCE, lists what was found and builds nothing.
- **Recipe lookup:** when the user names a dish and an ingredient ("replace the cream in a penne recipe"), only recipes that contain that ingredient are searched, so the original always has the ingredient to replace.
- **Limits:** thresholds are design choices, not measured; title words are a rough proxy for "same dish"; evidence shows other recipes use the substitute, not that it works in this recipe.

## 11. Junk-title filter (query time)
- **Problem:** the source data has test records such as "Tst" that rank in search, matching and fewest-steps lists.
- **Choice:** a rebuild would change recipe row order and invalidate the 25-minute embeddings index, so the filter runs at query time instead: `HybridRetriever.allowed_mask` also excludes junk titles (`src/recipebot/normalization/titles.py`, thresholds `JUNK_TITLE_*` in `config.py`). Nothing is deleted from the database.
- **Rules:** fewer than 3 letters, no vowel (except BLT, BBQ), or 8+ consonants in a row. Conservative on purpose.
- **Disclosure:** answers that rank recipes end with a "Quality filter" line giving the number hidden. Statistics (counts, percentages, medians) still count every recipe. `python -m recipebot.diagnose_titles` lists what is hidden.
- **Limit:** rules are heuristics; some junk titles with vowels remain visible.