### Turn 1

**User:** Find me a recipe that contains tomato, but I cannot have tomato.

Understanding: `{"intent": "search", "dish_query": null, "include": ["tomato"], "include_any": [], "exclude": ["tomato"], "allow": [], "max_steps": null, "available": [], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": "allergy", "reason": null}`

**Chatbot:**

```text
Added restriction: no tomato (ingredient).
Search: "tomato"
Hard filters applied: no tomato (ingredient); must contain tomato
Eligible recipes: 0 of 121,896 pass these filters; nothing was relaxed.
No recipe satisfies the hard constraints; nothing was relaxed.
You can remove a restriction (for example 'dairy is fine now') or ask for something else.
```

### Turn 2

**User:** I have eggs and I cannot have eggs.

Understanding: `{"intent": "match", "dish_query": null, "include": [], "include_any": [], "exclude": ["eggs"], "allow": [], "max_steps": null, "available": ["eggs"], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": "allergy", "reason": null}`

**Chatbot:**

```text
Added restriction: no egg (allergen check on every ingredient line).
New search: the previous 'must contain' list and step limit were reset; allergen and ingredient exclusions stay.
Not counted: 'egg' is in your ingredient list but you also excluded it.
None of your ingredients could be used (unknown names or excluded ingredients).
Tell me which ingredients you have, for example 'I have eggs, flour and milk'.
```

### Turn 3

**User:** Clear all my restrictions.

Understanding: `{"intent": "clear_filters", "dish_query": null, "include": [], "include_any": [], "exclude": [], "allow": [], "max_steps": null, "available": [], "stat_type": null, "k": null, "target_recipe_id": null, "target_recipe_title": null, "ingredient_to_replace": null, "restriction_type": null, "reason": null}`

**Chatbot:**

```text
All restrictions cleared. Tell me what you would like to search for.
```

