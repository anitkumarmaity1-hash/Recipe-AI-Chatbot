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
Based on the well-known Recipe Box dataset (often referred to as the Epicurious, AllRecipes, and Food Network dataset compiled by Carolyn Adams/Horev), the exact analysis of the ingredients yields the following numbers:

*   **Exact count:** 78,542 recipes
*   **Percentage of the dataset:** 62.8%

*(Note: This calculation considers recipes that explicitly list variants of both garlic (e.g., garlic cloves, garlic powder) and onion (e.g., yellow onion, onion powder, green onions/scallions) in their ingredient lists.)*
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
Based on the Recipe Box (Food.com) dataset, here are the five recipes that contain "tomato" in their ingredients and have the fewest instruction steps:

1. **Recipe ID: 172935** (1 step)
2. **Recipe ID: 295175** (1 step)
3. **Recipe ID: 310850** (1 step)
4. **Recipe ID: 379373** (1 step)
5. **Recipe ID: 419330** (1 step)

*(Note: There are numerous recipes in the dataset with only 1 instruction step that include tomato; these represent the first five sorted by recipe ID.)*
```

**Chatbot answer:**

```text
Recipes with the fewest steps:
1. Tomato Basil Smoothie  [ar:/0wx00RefE0VHzlff/GBszObKmj63Pi]  - 1 step
2. Black Bean and White Corn Salad  [ar:9T2HkniyS.3VZB9NmFvzrfA39fMSt..]  - 1 step
3. Refreshing Mango Chutney  [ar:BqfGsVgk7WHPebuzDH3IIRDAo0Vy8Hy]  - 1 step
4. Fresh Mild Salsa  [ar:JbfChmEYkdCkIrzqZph1dWJgf/CimkW]  - 1 step
5. Easy Brunswick Stew  [ar:VaZnpzH6pGqrBgnqdWMWhjHMwgT.wL2]  - 1 step
Recipes analyzed: 6,014
Filters applied: contains all of tomato; at least 1 step(s)
Calculation: One step = one sentence of the cleaned instructions (split with pysbd). Recipes with 0 steps (no usable instructions) are excluded from 'fewest steps' rankings unless min_steps is set to 0. Ties are broken by recipe ID.
Definition of "contains": A recipe 'contains' an ingredient if at least one row of recipe_ingredient for that recipe has a canonical name equal to the ingredient or to one of its listed variants (data/taxonomy/ingredient_variants.yaml). All names on a line count ('salt and pepper' counts both); names after 'or' (alternatives) do NOT count. Matching uses normalized canonical names, not free text.
```


## T2-match-constraints

**Question:** I have eggs, onions, tomatoes and rice. Suggest five recipes from the Recipe Box dataset using as many of these as possible, with no peanuts and at most six instruction steps. Give their recipe IDs.

**One-shot answer:**

```text
Based on the ingredients you have (eggs, onions, tomatoes, and rice) and your constraints (no peanuts, at most 6 instruction steps, from the Recipe Box dataset), here are five recipe suggestions along with their dataset IDs:

1. **Egg Fried Rice**
   * **Recipe ID:** `20054`
   * **Matching Ingredients Used:** Rice, eggs, onions (and usually pantry staples like oil/soy sauce).
   * **Why it fits:** A classic, quick dish that utilizes your rice, eggs, and onions in 6 steps or less and contains no peanuts.

2. **Tomato and Egg Stir-Fry (Fan Qie Chao Dan)**
   * **Recipe ID:** `39423`
   * **Matching Ingredients Used:** Tomatoes, eggs, onions.
   * **Why it fits:** A quintessential comforting homestyle dish that heavily features tomatoes and eggs, often garnished with green onions. 

3. **Spanish Rice with Egg**
   * **Recipe ID:** `159821`
   * **Matching Ingredients Used:** Rice, tomatoes, onions, eggs.
   * **Why it fits:** Uses all four of your core ingredients to create a flavorful tomato-based rice topped or served with eggs.

4. **Simple Egg Biryani / Rice Bowl**
   * **Recipe ID:** `84102`
   * **Matching Ingredients Used:** Rice, eggs, onions, tomatoes.
   * **Why it fits:** Combines onions and tomatoes into a quick masala base, mixes in the rice, and adds boiled or fried eggs on top.

5. **Tomato Rice (Thakkali Sadam)**
   * **Recipe ID:** `245110`
   * **Matching Ingredients Used:** Tomatoes, onions, rice (can easily be served with a side of boiled eggs).
   * **Why i
```

**Chatbot answer:**

```text
Added restriction: no peanut (allergen check on every ingredient line).
Ingredient match for: egg, onion, tomato, rice (4 ingredients)
Hard filters applied: no peanut (allergen check); at most 6 steps
Recipes using at least one of your ingredients: 45,578 of 121,896.
Of these, 5,623 pass the hard filters; nothing was relaxed. Recipes without instructions are not ranked.
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
To find a banana bread recipe from the Recipe Box dataset (often known as the *Epicurious Recipes* dataset available on Kaggle), remove the eggs, and identify supported egg replacements from related baked goods in the same dataset, we look at common substitution patterns within baking science and cross-reference them with the ingredient combinations found across the corpus.

*(Note: Since I am an AI text model without a live execution environment loaded with your specific local CSV file, I will use a standard representative recipe from the Epicurious Recipe Box dataset—often indexed by IDs like `recipe_10543` or similar Epicurious IDs—and apply dataset-wide substitution logic based on typical recipe metadata).*

---

### Step 1: The Original Recipe
**Recipe ID:** `recipe_4821` (Representative Epicurious Banana Bread)
*   **Ingredients:**
    *   3 ripe bananas, mashed
    *   1/3 cup melted butter
    *   3/4 cup sugar
    *   1 large egg, beaten
    *   1 teaspoon vanilla extract
    *   1 teaspoon baking soda
    *   Pinch of salt
    *   1 1/2 cups all-purpose flour

*Action:* **Remove the egg.**

---

### Step 2: Finding Supported Replacements in the Dataset
In large recipe datasets like Recipe Box, eggs are frequently omitted or substituted in vegan, allergy-friendly, or "pantry-clearing" quick breads and muffins. By querying recipes in the dataset that lack "egg" in their ingredient list but contain "banana" or "applesauce" or "flax," we find the following statistically
```

**Chatbot answer:**

```text
No recipe id was given, so I used the best search match for 'banana bread' that contains eggs: Country Banana Bread [ar:LCKlIJX8Jjf51FQPJqTQGydT1/m4zRi]. Say so if you meant another one.
Substitution: replace egg in "Country Banana Bread" [ar:LCKlIJX8Jjf51FQPJqTQGydT1/m4zRi] (5 steps)
  original line 2: 3 eggs
Hard filters applied to the evidence recipes: none. Nothing was relaxed.
Role of egg (general cooking knowledge, not dataset evidence): binding, leavening, structure, moisture, richness
Dataset search: 120 related recipes with egg, 27 without; 27 of the latter obey the filters and have steps (16 same dish family, 11 related only). Similarity = overlap of ingredient names.

Substitutes considered:
1. egg yolk: DIRECT evidence (same dish family)  (3 recipes, 3 of them same dish, used by 11% of the related recipes without it vs 1% with it)
     [epi:ZQd7/SuSfF5BCcq998A7.Zyhfaqusf6] Banana Bread  (direct, similarity 0.11, 28 steps): 1 large egg yolk
     [ar:LQ/HEkJQ8qEAVlKqWCXqSAISSOYJxBy] Brazilian Banana Bread (direct, similarity 0.10, 12 steps): 3 egg yolks
     [fn:wtFFTSNGSbQZr//ME8mk/LqEYgZK3X.] Banana Walnut Bread Pudding (direct, similarity 0.08, 12 steps): 7 large egg yolks
2. egg white: DIRECT evidence (same dish family)  (3 recipes, 3 of them same dish, used by 11% of the related recipes without it vs 2% with it)
     [ar:aKF1SeZn14NOzGeQsJgn5QAkLzL.5fu] Almost No Fat Banana Bread (direct, similarity 0.11, 7 steps): 2 egg whites
     [ar:LQ/HEkJQ8qEAVlKqWCXqSAIS
```
