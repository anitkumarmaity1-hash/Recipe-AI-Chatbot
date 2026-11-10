### Turn 1

**User:** I have eggs and I cannot have eggs.

Understanding: `{"intent": "match", "dish_query": null, "include": [], "include_any": [], "exclude": ["eggs"], "allow": [], "max_steps": null, "available": ["eggs"], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": "allergy", "reason": null}`

**Chatbot:**

```text
Added restriction: no egg (allergen check on every ingredient line).
Not counted: 'egg' is in your ingredient list but you also excluded it.
None of your ingredients could be used (unknown names or excluded ingredients).
Tell me which ingredients you have, for example 'I have eggs, flour and milk'.
Quality filter: 9 recipes whose title looks like a test record are never ranked here (config JUNK_TITLE_*); statistics counts include them.
```

### Turn 2

**User:** I have tomato and rice. No dairy, and at most 1 step.

Understanding: `{"intent": "match", "dish_query": null, "include": [], "include_any": [], "exclude": ["dairy"], "allow": [], "max_steps": 1, "available": ["eggs", "tomato", "rice"], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": null, "reason": null}`

**Chatbot:**

```text
Added restriction: no dairy (allergen check on every ingredient line).
Ingredient list extended: your 'must contain' list and step limit were kept.
Ingredient match for: tomato, rice (2 ingredients)
Not counted: 'egg' is in your ingredient list but you also excluded it.
Hard filters applied: no egg, dairy (allergen check); at most 1 step
Recipes using at least one of your ingredients: 6,534 of 121,896.
Of these, 17 pass the hard filters; nothing was relaxed. Recipes without instructions are not ranked.
Ranking: score = 4 x coverage - 2 x extra - 0.1 x steps (steps counted up to 30). coverage = matched / your ingredients; extra = extra needed / ingredients the recipe needs (pantry staples are not counted). Weights are design choices (src/recipebot/config.py), not measured values.

1. Tomato Salsa  [fn:Cv.LzyOIGtSJN3dvLIBqPQo8ac.K97G]  score 0.90
   Matched (1 of 2): tomato
   Missing, you have it but the recipe does not use it (1): rice
   Extra needed, the recipe requires it and it is not in your list (1): vinaigrette
   1 step | score = 4 x 0.50 - 2 x 0.50 - 0.1 x 1 = 0.90
   Check: hard filters re-verified from the database, none violated
2. QATEST44  [fn:uJQ/BFKwfjgq1TbJyTPgBuSt3pt4sV2]  score 0.57
   Matched (1 of 2): rice
   Missing, you have it but the recipe does not use it (1): tomato
   Extra needed, the recipe requires it and it is not in your list (2): mik, haldi
   1 step | score = 4 x 0.50 - 2 x 0.67 - 0.1 x 1 = 0.57
   Check: hard filters re-verified from the database, none violated
3. Refreshing Mango Chutney  [ar:BqfGsVgk7WHPebuzDH3IIRDAo0Vy8Hy]  score 0.40
   Matched (1 of 2): tomato
   Missing, you have it but the recipe does not use it (1): rice
   Extra needed, the recipe requires it and it is not in your list (3): red onion, mango, cilantro
   1 step | score = 4 x 0.50 - 2 x 0.75 - 0.1 x 1 = 0.40
   Check: hard filters re-verified from the database, none violated
4. Tomato Vinaigrette  [fn:1aUc3u7ilBze2F6UmtZy0ZIC2fYMAUK]  score 0.40
   Matched (1 of 2): tomato
   Missing, you have it but the recipe does not use it (1): rice
   Extra needed, the recipe requires it and it is not in your list (3): champagne vinegar, chive, tarragon
   Pantry staples assumed, not scored: olive oil, salt, black pepper
   1 step | score = 4 x 0.50 - 2 x 0.75 - 0.1 x 1 = 0.40
   Check: hard filters re-verified from the database, none violated
5. Pico de Gallo  [fn:EWHbufOf9ClZGXSRSuzOyPPSitd4DCO]  score 0.40
   Matched (1 of 2): tomato
   Missing, you have it but the recipe does not use it (1): rice
   Extra needed, the recipe requires it and it is not in your list (3): white onion, lime, cilantro
   Pantry staples assumed, not scored: salt, black pepper
   1 step | score = 4 x 0.50 - 2 x 0.75 - 0.1 x 1 = 0.40
   Check: hard filters re-verified from the database, none violated

Ask for 'the second one' to see its ingredients and steps.
Quantities: Ingredient names match, but quantity sufficiency could not be verified from the dataset.
Allergen checks read the ingredient text only; hidden sources (for example milk inside chocolate chips) cannot be detected. This is not medical advice: always check the real labels.
Quality filter: 9 recipes whose title looks like a test record are never ranked here (config JUNK_TITLE_*); statistics counts include them.
```

### Turn 3

**User:** Clear all my restrictions.

Understanding: `{"intent": "clear_filters", "dish_query": null, "include": [], "include_any": [], "exclude": [], "allow": [], "max_steps": null, "available": [], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": null, "reason": null}`

**Chatbot:**

```text
All restrictions cleared. Tell me what you would like to search for.
```

