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
Based on the standard analysis of the Recipe Box dataset (often referred to as the Epicurious, AllRecipes, and Food Network dataset compiled on Kaggle), **48,938** recipes contain both garlic and onion. 

Out of the total 124,943 recipes in the dataset, this represents **39.17%** of the recipes.
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
To find the five recipes containing "tomato" with the fewest instruction steps in the Recipe Box dataset (assuming the standard Kaggle dataset containing fields like `title`, `ingredients`, `directions`, and `id`/index), we look for recipes where the ingredient list includes "tomato" and the instructions (`directions` array) have the minimum length.

*(Note: Since I do not have a live execution environment connected to your specific local file of the Recipe Box dataset loaded into my context, I will provide the query/code method to extract this exact answer, along with the expected result structure. If you are running this in Python with Pandas, here is the exact code to get your answer:)*

### Python Code to Extract the Answer:
```python
import ast
import pandas as pd

# Load the dataset (adjust path as needed)
df = pd.read_csv("full_dataset.csv")

# Ensure directions and ingredients are parsed correctly (they are often stored as string representations of lists)
# If they are already lists, you can skip the literal_eval step.


def safe_eval(val):
    if isinstance(val, str):
        try:
            return ast.literal_eval(val)
        except:
            return []
    return val if isinstance(val, list) else []


df["directions_list"] = df["directions"].apply(safe_eval)
df["ingredients_list"] = df["ingredients"].apply(safe_eval)

# Filter for recipes containing 'tomato' in the ingredients
tomato_mask = df["ingredients_list"].apply(
    lambda ingredients: any(
        "tom
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
Based on the ingredients you have (eggs, onions, tomatoes, and rice) and your constraints (no peanuts, at most six instruction steps, selected from the Recipe Box dataset), here are five recipe suggestions along with their dataset IDs:

1. **Egg Fried Rice**
   * **Recipe ID:** `506c117eb931d87e1f41d996`
   * **Ingredients used:** Eggs, onions, rice.
   * **Description:** A classic, quick stir-fry combining leftover rice with scrambled eggs and aromatics.

2. **Tomato and Egg Stir-Fry (Fan Qie Chao Dan)**
   * **Recipe ID:** `8997a47ef0e85efca9e7eef2`
   * **Ingredients used:** Eggs, tomatoes, onions.
   * **Description:** A comforting homestyle Chinese dish featuring juicy tomatoes and soft scrambled eggs, great served over a bowl of rice.

3. **Simple Spanish Rice with Fried Egg**
   * **Recipe ID:** `785d0d1b61972bcfdca6d093`
   * **Ingredients used:** Rice, tomatoes, onions, eggs.
   * **Description:** Savory tomato-infused rice topped with a crispy-edged fried egg for a complete, hearty meal.

4. **Persian-Style Tomato Rice (Dami-ye Goje-Farangi)**
   * **Recipe ID:** `788647bdf2f919f2913b482b`
   * **Ingredients used:** Rice, tomatoes, onions.
   * **Description:** A fragrant one-pot rice dish cooked down with grated tomatoes, onions, and spices. (You can easily fry an egg to put on top!)

5. **Quick Egg and Tomato Curry with Rice**
   * **Recipe ID:** `4201c1074e019688dfca7cb7`
   * **Ingredients used:** Eggs, tomatoes, onions, rice.
   * **Description:** Hard-boiled o
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
Because I don't have access to the specific underlying database of the "Recipe Box" dataset (such as the Epicurious dataset commonly hosted on Kaggle) loaded into my immediate memory, I can't query specific internal recipe IDs. 

However, I can tell you how this is typically handled using the dataset's logic, and what data-driven substitutes you would find by analyzing related baked goods in that specific corpus.

### Standard Banana Bread (Egg-Free Modification)
In a standard banana bread recipe from the Recipe Box dataset (which usually relies on standard baking chemistry), eggs provide **structure, moisture, and leavening**. 

If you remove 2 eggs from a standard recipe, you need to replace them with an equivalent volume and binding agent. 

### Supported Egg Replacements in the Recipe Box Dataset
If you were to query the dataset for baked goods (muffins, quick breads, and vegan/allergy-friendly cakes) that omit eggs, the most common data-supported replacements for binding and moisture are:

1. **Mashed Banana (Extra):** 
   * *Dataset Context:* Since it's banana bread, increasing the banana content is the most frequent internal substitution. 
   * *Ratio:* 1/4 cup of mashed banana per egg.
2. **Applesauce:** 
   * *Dataset Context:* Frequently used in quick breads and muffins as a fat and egg binder substitute.
   * *Ratio:* 1/4 cup unsweetened applesauce per egg.
3. **Yogurt or Sour Cream:** 
   * *Dataset Context:* Often found in quick breads in this dataset to add mois
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
