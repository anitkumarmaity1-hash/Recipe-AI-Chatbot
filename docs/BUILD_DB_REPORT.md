# Build DB report (Step 3)

| Metric | AllRecipes | Epicurious | Food Network | Total |
|---|---:|---:|---:|---:|
| Raw records read | 39,802 | 25,323 | 60,039 | 125,164 |
| Usable (table `recipes`) | 39,507 | 25,229 | 57,160 | 121,896 |
| Excluded (table `recipes_excluded`) | 295 | 94 | 2,879 | 3,268 |
| - excluded: malformed_record | 0 | 0 | 0 | 0 |
| - excluded: empty_title | 280 | 0 | 289 | 569 |
| - excluded: empty_ingredients | 0 | 47 | 1,577 | 1,624 |
| - excluded: no_usable_ingredients_after_cleaning | 0 | 0 | 3 | 3 |
| - excluded: exact_duplicate | 15 | 47 | 1,010 | 1,072 |
| Usable with empty instructions (kept, flagged) | 0 | 15 | 18 | 33 |
| Doubled instructions (exact match, all non-malformed records) | 0 | 5,173 | 72 | 5,245 |
| Ingredient lines seen (records with a list of ingredients) | 400,846 | 246,780 | 669,324 | 1,316,950 |
| - kept unchanged | 35 | 246,746 | 668,399 | 915,180 |
| - ADVERTISEMENT stripped, text kept | 358,409 | 0 | 0 | 358,409 |
| - dropped: ADVERTISEMENT only | 39,519 | 0 | 0 | 39,519 |
| - dropped: section header ending with ':' | 2,883 | 33 | 877 | 3,793 |
| - dropped: empty | 0 | 1 | 48 | 49 |
| Non-string instructions (expected 0) | 0 | 0 | 0 | 0 |
| Non-string ingredient items in usable records (expected 0) | 0 | 0 | 0 | 0 |

## Checks

- PASS usable (121,896) + excluded (3,268) = raw records (125,164)
- PASS row_idx is 0..121,895, unique, in build order
- PASS no cleaned ingredient line contains ADVERTISEMENT, is empty, or ends with ':'
- PASS instructions_empty flag is consistent
- PASS original columns (title, ingredients, instructions) are identical to the raw files
- PASS excluded records are recoverable and every duplicate points to a kept recipe
