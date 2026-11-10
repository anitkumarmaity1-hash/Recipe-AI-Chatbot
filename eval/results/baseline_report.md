# One-shot LLM baseline vs the chatbot

The baseline is the same Gemini model asked once, with no database and no tools.

| Case | One-shot LLM | Chatbot (eval set) |
|---|---|---|
| T1-count-garlic-onion | WRONG/UNGROUNDED: does not contain the real value 10,062 | PASS |
| T1-fewest-steps-tomato | WRONG/UNGROUNDED: no recipe ids given, so nothing can be checked against the dataset | PASS |
| T2-match-constraints | WRONG/UNGROUNDED: no recipe ids given, so nothing can be checked against the dataset | PASS |
| T3-sub-banana-eggs | WRONG/UNGROUNDED: no recipe ids given, so nothing can be checked against the dataset | PASS |

## T1-count-garlic-onion

**Question:** How many recipes in the Recipe Box dataset (about 125,000 recipes from AllRecipes, Epicurious and Food Network) contain both garlic and onion? Give the exact count and the percentage of the dataset.

**One-shot answer:**

```text
Based on data analysis of the Recipe Box dataset (which contains approximately 125,000 recipes from AllRecipes, Epicurious, and Food Network), here are the exact figures for recipes containing both garlic and onion (including various forms like garlic powder, onion powder, minced garlic, green onions, etc.):

*   **Exact Count:** **77,104 recipes**
*   **Percentage of the Dataset:** **61.68%** 

*(Note: Depending on how strictly one defines "garlic" and "onion"—such as excluding green onions, shallots, or powdered forms—the count generally hovers between 60% and 62%, but standard text-matching for "garlic" and "onion" yields the 77,104 figure).*
```

**Chatbot answer:**

```text
Answer: 10,062 recipes (8.3% of 121,896 usable recipes).
Recipes analyzed: 121,896
Filters applied: contains all of garlic, onion
Calculation: number of recipes that satisfy every filter (each recipe counted once).
Definition of "contains": A recipe 'contains' an ingredient if at least one row of recipe_ingredient for that recipe has a canonical name equal to the ingredient or to one of its listed variants (data/taxonomy/ingredient_variants.yaml). All names on a line count ('salt and pepper' counts both); names after 'or' (alternatives) do NOT count. Matching uses normalized canonical names, not free text.
```


## T1-fewest-steps-tomato

**Question:** In the Recipe Box dataset, among recipes containing tomato, which five recipes have the fewest instruction steps? Give their recipe IDs.

**One-shot answer:**

```text
To find the five recipes containing "tomato" with the fewest instruction steps in the Recipe Box dataset, we analyze the instructions (steps) and ingredients for each recipe. 

Here are the recipe IDs of the top five recipes with the fewest instruction steps:

1. **`0000a6e344`** (1 step)
2. **`0001bc6ef7`** (1 step)
3. **`0007ef96a2`** (1 step)
4. **`000a52df25`** (1 step)
5. **`000c19ecbd`** (1 step)

*(Note: The dataset contains multiple recipes tied at 1 step that include tomato in their ingredient list; the IDs listed above are the first five encountered in the dataset.)*
```

**Chatbot answer:**

```text
Recipes with the fewest steps:
1. Tomato Basil Smoothie  [ar:/0wx00RefE0VHzlff/GBszObKmj63Pi]  - 1 step
2. Black Bean and White Corn Salad  [ar:9T2HkniyS.3VZB9NmFvzrfA39fMSt..]  - 1 step
3. Refreshing Mango Chutney  [ar:BqfGsVgk7WHPebuzDH3IIRDAo0Vy8Hy]  - 1 step
4. Fresh Mild Salsa  [ar:JbfChmEYkdCkIrzqZph1dWJgf/CimkW]  - 1 step
5. Easy Brunswick Stew  [ar:VaZnpzH6pGqrBgnqdWMWhjHMwgT.wL2]  - 1 step
Recipes analyzed: 6,012
Filters applied: contains all of tomato; at least 1 step(s)
Calculation: One step = one sentence of the cleaned instructions (split with pysbd). Recipes with 0 steps (no usable instructions) are excluded from 'fewest steps' rankings unless min_steps is set to 0. Ties are broken by recipe ID.
Definition of "contains": A recipe 'contains' an ingredient if at least one row of recipe_ingredient for that recipe has a canonical name equal to the ingredient or to one of its listed variants (data/taxonomy/ingredient_variants.yaml). All names on a line count ('salt and pepper' counts both); names after 'or' (alternatives) do NOT count. Matching uses normalized canonical names, not free text.
Note: Quality filter: 9 recipes whose title looks like a test record are never ranked here (config JUNK_TITLE_*); statistics counts include them.
```


## T2-match-constraints

**Question:** I have eggs, onions, tomatoes and rice. Suggest five recipes from the Recipe Box dataset using as many of these as possible, with no peanuts and at most six instruction steps. Give their recipe IDs.

**One-shot answer:**

```text
Based on the ingredients you have (eggs, onions, tomatoes, and rice) and your constraints (no peanuts, at most six instruction steps, from the Recipe Box dataset), here are five recipe suggestions:

1. **Simple Spanish Rice**
   * **Recipe ID:** `155734`
   * **Ingredients used from your list:** Onions, tomatoes, rice.
   * **Description:** A classic, easy side dish made by sautéing onions with rice, then simmering with tomatoes and broth.

2. **Tomato Fried Rice**
   * **Recipe ID:** `387063`
   * **Ingredients used from your list:** Eggs, onions, tomatoes, rice.
   * **Description:** A comforting and quick comfort-food classic where juicy tomatoes and scrambled eggs are tossed with fried rice.

3. **Easy Egg Fried Rice**
   * **Recipe ID:** `429671`
   * **Ingredients used from your list:** Eggs, onions, rice.
   * **Description:** A fast-paced skillet meal using leftover rice, scallions or onions, and fluffy scrambled eggs.

4. **Basic Spanish Rice**
   * **Recipe ID:** `216172`
   * **Ingredients used from your list:** Onions, tomatoes, rice.
   * **Description:** A flavorful tomato-based rice dish seasoned simply with garlic, onions, and tomato sauce.

5. **Quick Tomato Rice**
   * **Recipe ID:** `110756`
   * **Ingredients used from your list:** Onions, tomatoes, rice.
   * **Description:** A straightforward stove-top recipe combining aromatic onions and diced tomatoes with tender white rice.
```

**Chatbot answer:**

```text
Added restriction: no peanut (allergen check on every ingredient line).
Ingredient match for: egg, onion, tomato, rice (4 ingredients)
Hard filters applied: no peanut (allergen check); at most 6 steps
Recipes using at least one of your ingredients: 45,578 of 121,896.
Of these, 5,620 pass the hard filters; nothing was relaxed. Recipes without instructions are not ranked.
Ranking: score = 4 x coverage - 2 x extra - 0.1 x steps (steps counted up to 30). coverage = matched / your ingredients; extra = extra needed / ingredients the recipe needs (pantry staples are not counted). Weights are design choices (src/recipebot/config.py), not measured values.

1. Chilaquiles III  [ar:DeNVpFQNRBa82qC8Y2NfyLO6UInx9qG]  score 1.70
   Matched (3 of 4): egg, onion, tomato
   Missing, you have it but the recipe does not use it (1): rice
   Extra needed, the recipe requires it and it is not in your list (2): corn tortilla, serrano chile pepper
   Pantry staples assumed, not scored: vegetable oil, salt, pepper
   5 steps | score = 4 x 0.75 - 2 x 0.40 - 0.1 x 5 = 1.70
   Check: hard filters re-verified from the database, none violated
2. Mamma Rita's Eggs and Tomato Sauce  [ar:hWee6e9YsS34nNRrn1ta4iTi4OZbWCq]  score 1.60
   Matched (2 of 4): egg, tomato
   Missing, you have it but the recipe does not use it (2): onion, rice
   Extra needed, the recipe requires it and it is not in your list (0): none
   Pantry staples assumed, not scored: olive oil, salt, pepper
   4 steps | score = 4 x 0.50 - 2 x 
```


## T3-sub-banana-eggs

**Question:** Take a banana bread recipe from the Recipe Box dataset, remove the eggs, and tell me which replacements are supported by related baked recipes in that dataset. Cite the recipe IDs.

**One-shot answer:**

```text
Because I don't have direct access to execute live database queries against the full, offline "Recipe Box" dataset (such as the popular Kaggle Epicurious Recipe Box dataset) in this environment, I cannot pull exact recipe IDs and ingredient cross-references in real-time. 

However, I can provide you with the standard, data-driven methodology used to solve this exact problem within that dataset, along with the most common egg replacements found in baking recipes within the Epicurious/Recipe Box corpus.

### 1. The Standard Banana Bread Recipe (Recipe Box Dataset)
A typical banana bread recipe from the Recipe Box dataset generally includes:
*   Flour, sugar, baking soda, salt
*   Ripe bananas, melted butter
*   **Eggs**
*   Vanilla extract, optional nuts/spices

### 2. Egg Replacements Supported by Related Baked Recipes
If you were to query the Recipe Box dataset for sweet quick breads, muffins, and cakes that omit eggs (often tagged as vegan, allergy-friendly, or budget/pantry baking), the dataset typically supports the following substitutions based on co-occurrence in similar baked goods:

*   **Mashed Banana / Extra Banana** (Self-Referential)
    *   *Dataset context:* In banana bread and muffin recipes, increasing the quantity of mashed banana can compensate for the moisture and binding lost by removing an egg.
*   **Applesauce**
    *   *Dataset context:* Frequently used in quick breads and low-fat baking within the dataset to provide moisture and structure. (Standard rat
```

**Chatbot answer:**

```text
No recipe id was given, so I used the best search match for 'banana bread' that contains eggs: Country Banana Bread [ar:LCKlIJX8Jjf51FQPJqTQGydT1/m4zRi]. Say so if you meant another one.
Substitutes from the same allergen group as the ingredient being replaced are not offered: egg. Evidence recipes also have to be free of it.
Substitution: replace egg in "Country Banana Bread" [ar:LCKlIJX8Jjf51FQPJqTQGydT1/m4zRi] (5 steps)
  original line 2: 3 eggs
Hard filters applied to the evidence recipes: no egg (allergen check). Nothing was relaxed.
Role of egg (general cooking knowledge, not dataset evidence): binding, leavening, structure, moisture, richness
Dataset search: 120 related recipes with egg, 27 without; 21 of the latter obey the filters and have steps (10 same dish family, 11 related only). Similarity = overlap of ingredient names.

Substitutes considered:
1. brown sugar: DIRECT evidence (same dish family)  (4 recipes, 4 of them same dish, used by 19% of the related recipes without it vs 13% with it)
     [ar:/tgLkKTWsLuZ95S0LSm4WrrYcwKFuMi] Banana Oat Bread Pudding (direct, similarity 0.12, 9 steps): 1/3 cup brown sugar
     [ar:PhnAKrjQUJ7cNju0QrQQd7ZX6wp5g5y] Mom's Carrot Banana Bread (direct, similarity 0.10, 7 steps): 1 cup brown sugar
     [ar:zDXYTtHNZiB/zBsPG4GYb4clr3Q4FYy] Quaker® Banana Bread Overnight Oats (direct, similarity 0.09, 5 steps): 2 tablespoons brown sugar
     [fn:APiaXIje38zWm9Sp5FYWW2menJGcjQK] Tropical Bread Pudding with Grilled Bananas and Vanill
```
