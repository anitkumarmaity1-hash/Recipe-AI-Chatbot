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