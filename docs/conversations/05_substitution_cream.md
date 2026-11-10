### Turn 1

**User:** Take a penne pasta recipe and replace the cream without dairy.

Understanding: `{"intent": "substitute", "dish_query": "penne pasta", "include": [], "include_any": [], "exclude": ["dairy"], "allow": [], "max_steps": null, "available": [], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": "cream", "restriction_type": null, "reason": null}`

**Chatbot:**

```text
I can't provide an adapted recipe for [fn:6Vi.RvXGd.fVPiUz10UWjlpt.bzgnXW] that satisfies your hard restrictions. The independent final-recipe check found: ingredient line 10 contains dairy (excluded allergen; 'butter'); ingredient line 11 contains dairy (excluded allergen; 'parmesan'); step 7 mentions excluded allergen dairy ('butter'); step 8 mentions excluded allergen dairy ('cheese'). No adapted recipe is shown, and the original database recipe is unchanged.
```

### Turn 2

**User:** No nuts either.

Understanding: `{"intent": "refine", "dish_query": null, "include": [], "include_any": [], "exclude": ["nuts"], "allow": [], "max_steps": null, "available": [], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": "allergy", "reason": null}`

**Chatbot:**

```text
Added restriction: no peanut (allergen check on every ingredient line).
Added restriction: no tree nut (allergen check on every ingredient line).
Search: "penne pasta"
Hard filters applied: no dairy, peanut, tree nut (allergen check)
Eligible recipes: 44,506 of 121,896 pass these filters; nothing was relaxed.
Ranking: BM25 + embeddings fused with RRF (k=60, weights 1.0/1.0).

1. Penne Pasta with Spinach and Bacon  [ar:23to8XzUux0FF.g5ZFsqnxvhByMzfJ.]
   8 steps | 6 ingredients | BM25 #1, embeddings #1
   Check: no dairy, peanut, tree nut terms in its 6 ingredient lines
   Ingredient lines (the evidence for the check):
     - 1 (12 ounce) package penne pasta
     - 2 tablespoons olive oil, divided
     - 6 slices bacon, chopped
     - 2 tablespoons minced garlic
     - 1 (14.5 ounce) can diced tomatoes
     - 1 bunch fresh spinach, rinsed and torn into bite-size pieces
2. Penne Pasta with Cannellini Beans and Escarole  [ar:zwRAInNlhnKD1jMf/HOm5a9oKhjC8Om]
   4 steps | 5 ingredients | BM25 #2, embeddings #3
   Check: no dairy, peanut, tree nut terms in its 5 ingredient lines
   Ingredient lines (the evidence for the check):
     - 1 (16 ounce) package dry penne pasta
     - 1 head escarole, chopped
     - 1 (15.5 ounce) can cannellini beans, with liquid
     - 1 (14.5 ounce) can diced tomatoes with garlic and onion, drained
     - salt and ground black pepper to taste
3. Penne with Mushrooms and Caramelized Garlic Topped with Parsley  [fn:lbdoJWX6HAMrTwmYjkFPyxu/lqR/lLO]
   5 steps | 5 ingredients | BM25 #3, embeddings #8
   Check: no dairy, peanut, tree nut terms in its 5 ingredient lines
   Ingredient lines (the evidence for the check):
     - 3 cloves garlic, diced
     - Olive oil
     - 8 mushrooms, diced
     - 1 pound penne pasta
     - Sprig parsley, chopped
4. Penne with Eggplant  [ar:J0i796t1eGNrEYZx/buYDaILREObz.y]
   11 steps | 9 ingredients | BM25 #7, embeddings #4
   Check: no dairy, peanut, tree nut terms in its 9 ingredient lines
   Ingredient lines (the evidence for the check):
     - 1 (8 ounce) package penne pasta
     - 2 tablespoons olive oil
     - 1 eggplant, halved lengthwise and cut into small pieces
     - 3 cloves garlic, chopped
     - 2 tablespoons olive oil, or more if needed
     - salt and pepper to taste
     - 1/4 cup sun-dried tomato spread
     - 1 cup tomato sauce, or more if needed
     - 4 leaves chopped fresh basil
5. Pat's Simple Penne  [ar:9mPiUMSt4KndASd0tYPD7iKvkRhsO2i]
   7 steps | 5 ingredients | BM25 #4, embeddings #7
   Check: no dairy, peanut, tree nut terms in its 5 ingredient lines
   Ingredient lines (the evidence for the check):
     - 6 cups penne pasta
     - 1 pound bacon, cut into 1 inch pieces
     - 1 onion, thinly sliced
     - 3 1/2 (10.75 ounce) cans chicken broth
     - 1 pinch crushed red pepper flakes

Ask for 'the second one' to see its ingredients and steps.
Allergen checks read the ingredient text only; hidden sources (for example milk inside chocolate chips) cannot be detected. This is not medical advice: always check the real labels.
Quality filter: 9 recipes whose title looks like a test record are never ranked here (config JUNK_TITLE_*); statistics counts include them.
```

