### Turn 1

**User:** I have eggs, onions, tomatoes and rice. Suggest five recipes using as many of these as possible, with no peanuts and at most six instruction steps. Prefer recipes that need the fewest additional ingredients.

Understanding: `{"intent": "match", "dish_query": null, "include": [], "include_any": [], "exclude": ["peanuts"], "allow": [], "max_steps": 6, "available": ["eggs", "onions", "tomatoes", "rice"], "stat_type": null, "k": 5, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": "preference", "reason": null}`

**Chatbot:**

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
   4 steps | score = 4 x 0.50 - 2 x 0.00 - 0.1 x 4 = 1.60
   Check: hard filters re-verified from the database, none violated
3. Kagianas (Greek Eggs and Tomato)  [ar:qBI.d/OwTnbOl8tQaYRtvmZJwpiOREq]  score 1.50
   Matched (2 of 4): egg, tomato
   Missing, you have it but the recipe does not use it (2): onion, rice
   Extra needed, the recipe requires it and it is not in your list (0): none
   Pantry staples assumed, not scored: olive oil, salt, black pepper
   5 steps | score = 4 x 0.50 - 2 x 0.00 - 0.1 x 5 = 1.50
   Check: hard filters re-verified from the database, none violated
4. Anything Rice   [epi:0w3VI3ZrfiqIWvvBoROI4kmyZg3qeRy]  score 1.50
   Matched (3 of 4): egg, onion, rice
   Missing, you have it but the recipe does not use it (1): tomato
   Extra needed, the recipe requires it and it is not in your list (3): cooking oil, green bell pepper, leftover chicken
   5 steps | score = 4 x 0.75 - 2 x 0.50 - 0.1 x 5 = 1.50
   Check: hard filters re-verified from the database, none violated
5. Extreme Veggie Scrambled Eggs  [ar:56smttC.gspsdV5pRtb8NkBrph1HiGW]  score 1.46
   Matched (3 of 4): egg, onion, tomato
   Missing, you have it but the recipe does not use it (1): rice
   Extra needed, the recipe requires it and it is not in your list (4): canned black bean, green bell pepper, milk, cheddar cheese
   Pantry staples assumed, not scored: olive oil
   4 steps | score = 4 x 0.75 - 2 x 0.57 - 0.1 x 4 = 1.46
   Check: hard filters re-verified from the database, none violated

Ask for 'the second one' to see its ingredients and steps.
Quantities: Ingredient names match, but quantity sufficiency could not be verified from the dataset.
Allergen checks read the ingredient text only; hidden sources (for example milk inside chocolate chips) cannot be detected. This is not medical advice: always check the real labels.
Quality filter: 9 recipes whose title looks like a test record are never ranked here (config JUNK_TITLE_*); statistics counts include them.
```

### Turn 2

**User:** Exclude eggs too.

Understanding: `{"intent": "refine", "dish_query": null, "include": [], "include_any": [], "exclude": ["eggs"], "allow": [], "max_steps": null, "available": [], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": null, "reason": null}`

**Chatbot:**

```text
Added restriction: no egg (allergen check on every ingredient line).
Ingredient match for: onion, tomato, rice (3 ingredients)
Not counted: 'egg' is in your ingredient list but you also excluded it.
Hard filters applied: no peanut, egg (allergen check); at most 6 steps
Recipes using at least one of your ingredients: 23,290 of 121,896.
Of these, 3,409 pass the hard filters; nothing was relaxed. Recipes without instructions are not ranked.
Ranking: score = 4 x coverage - 2 x extra - 0.1 x steps (steps counted up to 30). coverage = matched / your ingredients; extra = extra needed / ingredients the recipe needs (pantry staples are not counted). Weights are design choices (src/recipebot/config.py), not measured values.

1. Hoppin' John   [epi:4UUQ6uRJcpuLIZPkPud5UWwRkViq0Z.]  score 2.35
   Matched (3 of 3): onion, tomato, rice
   Missing, you have it but the recipe does not use it (0): none
   Extra needed, the recipe requires it and it is not in your list (5): slab bacon, celery, garlic, black-eyed pea, red pepper flake
   Pantry staples assumed, not scored: salt, black pepper, water
   4 steps | score = 4 x 1.00 - 2 x 0.62 - 0.1 x 4 = 2.35
   Check: hard filters re-verified from the database, none violated
2. String Beans and Tomatoes  [fn:CFfp23vqCnmrQBvLVFdWd/qLrmsS0f.]  score 2.05
   Matched (3 of 3): onion, tomato, rice
   Missing, you have it but the recipe does not use it (0): none
   Extra needed, the recipe requires it and it is not in your list (8): red bell pepper, garlic, butter, ketchup, carrot, dried basil, tomatoes with chile, string bean
   Pantry staples assumed, not scored: salt, pepper
   5 steps | score = 4 x 1.00 - 2 x 0.73 - 0.1 x 5 = 2.05
   Check: hard filters re-verified from the database, none violated
3. Vegetarian Southwest One-Pot Dinner  [ar:HlBLVYXlxk2ky1lf6PDYuUEV642OYYa]  score 2.00
   Matched (3 of 3): onion, tomato, rice
   Missing, you have it but the recipe does not use it (0): none
   Extra needed, the recipe requires it and it is not in your list (7): dried black-eyed pea, green bell pepper, garlic, sweet corn, chili powder, ground cumin, cheddar cheese
   6 steps | score = 4 x 1.00 - 2 x 0.70 - 0.1 x 6 = 2.00
   Check: hard filters re-verified from the database, none violated
4. Peruvian Meat and Rice  [ar:MkERS7slxjrIYZxp8FN4SUUTkPo0Q1i]  score 1.95
   Matched (3 of 3): onion, tomato, rice
   Missing, you have it but the recipe does not use it (0): none
   Extra needed, the recipe requires it and it is not in your list (8): ground pork, garlic, ground cumin, southern-style hash brown potato, soy sauce, parsley, oregano, cilantro
   Pantry staples assumed, not scored: vegetable oil, salt, black pepper
   6 steps | score = 4 x 1.00 - 2 x 0.73 - 0.1 x 6 = 1.95
   Check: hard filters re-verified from the database, none violated
5. Slow Cooker Jambalaya  [fn:1CD3HIGht0jcS8vEMxkdy/rC1oAGSOi]  score 1.93
   Matched (3 of 3): onion, tomato, rice
   Missing, you have it but the recipe does not use it (0): none
   Extra needed, the recipe requires it and it is not in your list (11): chicken breast, andouille sausage, green bell pepper, celery, chicken broth, dried oregano, cajun seasoning, hot sauce, bay leaf, dried thyme, shrimp
   5 steps | score = 4 x 1.00 - 2 x 0.79 - 0.1 x 5 = 1.93
   Check: hard filters re-verified from the database, none violated

Ask for 'the second one' to see its ingredients and steps.
Quantities: Ingredient names match, but quantity sufficiency could not be verified from the dataset.
Allergen checks read the ingredient text only; hidden sources (for example milk inside chocolate chips) cannot be detected. This is not medical advice: always check the real labels.
Quality filter: 9 recipes whose title looks like a test record are never ranked here (config JUNK_TITLE_*); statistics counts include them.
```

### Turn 3

**User:** I also have garlic.

Understanding: `{"intent": "match", "dish_query": null, "include": [], "include_any": [], "exclude": [], "allow": [], "max_steps": null, "available": ["eggs", "onions", "tomatoes", "rice", "garlic"], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": null, "reason": null}`

**Chatbot:**

```text
Ingredient list extended: your 'must contain' list and step limit were kept.
Ingredient match for: onion, tomato, rice, garlic (4 ingredients)
Not counted: 'egg' is in your ingredient list but you also excluded it.
Hard filters applied: no peanut, egg (allergen check); at most 6 steps
Recipes using at least one of your ingredients: 43,543 of 121,896.
Of these, 6,263 pass the hard filters; nothing was relaxed. Recipes without instructions are not ranked.
Ranking: score = 4 x coverage - 2 x extra - 0.1 x steps (steps counted up to 30). coverage = matched / your ingredients; extra = extra needed / ingredients the recipe needs (pantry staples are not counted). Weights are design choices (src/recipebot/config.py), not measured values.

1. Hoppin' John   [epi:4UUQ6uRJcpuLIZPkPud5UWwRkViq0Z.]  score 2.60
   Matched (4 of 4): onion, tomato, rice, garlic
   Missing, you have it but the recipe does not use it (0): none
   Extra needed, the recipe requires it and it is not in your list (4): slab bacon, celery, black-eyed pea, red pepper flake
   Pantry staples assumed, not scored: salt, black pepper, water
   4 steps | score = 4 x 1.00 - 2 x 0.50 - 0.1 x 4 = 2.60
   Check: hard filters re-verified from the database, none violated
2. String Beans and Tomatoes  [fn:CFfp23vqCnmrQBvLVFdWd/qLrmsS0f.]  score 2.23
   Matched (4 of 4): onion, tomato, rice, garlic
   Missing, you have it but the recipe does not use it (0): none
   Extra needed, the recipe requires it and it is not in your list (7): red bell pepper, butter, ketchup, carrot, dried basil, tomatoes with chile, string bean
   Pantry staples assumed, not scored: salt, pepper
   5 steps | score = 4 x 1.00 - 2 x 0.64 - 0.1 x 5 = 2.23
   Check: hard filters re-verified from the database, none violated
3. Vegetarian Southwest One-Pot Dinner  [ar:HlBLVYXlxk2ky1lf6PDYuUEV642OYYa]  score 2.20
   Matched (4 of 4): onion, tomato, rice, garlic
   Missing, you have it but the recipe does not use it (0): none
   Extra needed, the recipe requires it and it is not in your list (6): dried black-eyed pea, green bell pepper, sweet corn, chili powder, ground cumin, cheddar cheese
   6 steps | score = 4 x 1.00 - 2 x 0.60 - 0.1 x 6 = 2.20
   Check: hard filters re-verified from the database, none violated
4. Peruvian Meat and Rice  [ar:MkERS7slxjrIYZxp8FN4SUUTkPo0Q1i]  score 2.13
   Matched (4 of 4): onion, tomato, rice, garlic
   Missing, you have it but the recipe does not use it (0): none
   Extra needed, the recipe requires it and it is not in your list (7): ground pork, ground cumin, southern-style hash brown potato, soy sauce, parsley, oregano, cilantro
   Pantry staples assumed, not scored: vegetable oil, salt, black pepper
   6 steps | score = 4 x 1.00 - 2 x 0.64 - 0.1 x 6 = 2.13
   Check: hard filters re-verified from the database, none violated
5. Fresh Tomato Basil Sauce  [ar:tULU2LBLcoRpDaEr8zomOkuIi6h8cQq]  score 2.10
   Matched (3 of 4): onion, tomato, garlic
   Missing, you have it but the recipe does not use it (1): rice
   Extra needed, the recipe requires it and it is not in your list (1): basil
   Pantry staples assumed, not scored: olive oil, salt, pepper
   4 steps | score = 4 x 0.75 - 2 x 0.25 - 0.1 x 4 = 2.10
   Check: hard filters re-verified from the database, none violated

Ask for 'the second one' to see its ingredients and steps.
Quantities: Ingredient names match, but quantity sufficiency could not be verified from the dataset.
Allergen checks read the ingredient text only; hidden sources (for example milk inside chocolate chips) cannot be detected. This is not medical advice: always check the real labels.
Quality filter: 9 recipes whose title looks like a test record are never ranked here (config JUNK_TITLE_*); statistics counts include them.
```

### Turn 4

**User:** Show me the first one.

Understanding: `{"intent": "show_details", "dish_query": null, "include": [], "include_any": [], "exclude": [], "allow": [], "max_steps": null, "available": [], "stat_type": null, "k": null, "target_recipe_id": "epi:4UUQ6uRJcpuLIZPkPud5UWwRkViq0Z.", "target_recipe_title": "Hoppin' John", "ingredient_to_replace": null, "restriction_type": null, "reason": null}`

**Chatbot:**

```text
Hoppin' John   [epi:4UUQ6uRJcpuLIZPkPud5UWwRkViq0Z.]  (source: Epicurious)

Ingredients:
  - 1/4 pound slab bacon, cut into 1/4-inch cubes
  - 1 small onion, finely chopped
  - 1 celery rib, finely chopped
  - 1 garlic clove, minced
  - 2 pounds black-eyed peas (fresh or frozen)
  - Salt and freshly ground black pepper to taste
  - Red pepper flakes to taste
  - 3 cups water
  - Hot cooked rice
  - 3 large ripe tomatoes, chopped or stewed

Instructions (4 steps, one sentence = one step):
  1. In a large saucepan, fry the bacon over moderate heat till almost crisp and pour off all but about 1 tablespoon of the grease.
  2. Add the onion, celery, and garlic and cook, stirring, for 2 minutes.
  3. Add the peas, salt and pepper, red pepper flakes, and water, bring to a boil, reduce the heat to low, cover, and simmer till the peas are tender but not mushy, about 1 hour.
  4. Drain the peas, then serve them in small bowls over mounds of hot rice with a few spoonfuls of tomatoes on the tops.

Note: this is the cleaned text (ADVERTISEMENT markers and section-header lines removed); the original text is stored unchanged in the database.
```

