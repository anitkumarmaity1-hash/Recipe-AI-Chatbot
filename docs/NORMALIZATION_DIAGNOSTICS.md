# Normalization diagnostics (Step 4b-1)

Generated: 2026-11-08T00:49:03

## 1. Recipes with 0 steps

| instructions_empty | recipes |
|---|---|
| False | 15 |
| True | 33 |

Zero steps although instructions are NOT empty (first 15):

| id | title | chars | start of instructions_clean |
|---|---|---|---|
| fn:/9gzhAs85eTplAn8/SvcjgirsO/W7fu | Gateau Saint-Honore | 1 | ; |
| fn:6AdCFCZR4cr1NzOtloWzWuOmDewvFGG | Title | 1 | ; |
| fn:76zDLGsfc5S.M60Zgn9PqbONi4Ky2yO | New England Stuffing | 2 | .; |
| fn:8cXsulZSeQb3w.W70RwTlbZ./rDbpF6 | Queen Mother's Cake | 1 | ; |
| fn:CIpbN9qEZeLIg0YNW8aC6zwfR8CRYte | Real Time Cooking -- Out of the Fridge and Pantry | 1 | . |
| fn:DxsP.opjapGRa4zq4XMrI5M2Zz6EGue | Title | 1 | ; |
| fn:GTI7DQPe/IIaXmQbITOlrtAiykcHiie | Dark Chocolate as a Snack | 1 | ; |
| fn:GsAQK3AG..YxEw7lKIy3PcZ31MY1FEG | Gas Station Cue | 1 | ; |
| fn:MTfg2ThnICiCRaQPkUZuXzHf8GEgKUC | Midwest Stuffing | 2 | .; |
| fn:iVw3EPn4NzLlzY.FuhGphhBs6VcTpTi | Lamb Chops | 1 | ; |
| fn:nR3sz.W1PSU74zn8m3NDDYC96iEI.lW | Title | 1 | ; |
| fn:pKBZl5/whnhq65P6/TbUjEfQ0jM85Se | Southwest Stuffing | 2 | .; |
| fn:uvcjJ07lrvDkPRXKUcA8CrKLgJbD4hq | Southern Stuffing | 2 | .; |
| fn:yJcaFDZcwAdeOxs2pIhWRz72Xnz/ysC | Title | 1 | ; |
| fn:z/doINysh818E6fDIAXUnLyLn7gGqLy | EXPIRE ME | 1 | ; |

## 2. Highest step counts

| id | title | n_steps | chars | newlines |
|---|---|---|---|---|
| epi:ooB4g9Ui2SkHVhnUrUjK3vfCT5UNSIe | Basic Brioche  | 286 | 28058 | 70 |
| epi:GHxfIaJYfIkIDpGgUrs/0jX0rJ0TAKe | Basic Sourdough Bread  | 265 | 25965 | 52 |
| epi:wUeErXrKq2JQ.UEgMEEobDhubqOGhmi | Fondant-Covered Wedding Cake with Raspberries and Chocolate  | 260 | 18569 | 23 |
| epi:FU.E9mpjw8EfI6lBD4OI1fY/mkFRkjC | Plain French Bread (Pain Français)  | 228 | 28039 | 59 |
| epi:1Sv8KemKulQpkexkry7wY6nR8ulUrd6 | Lemon-Berry Wedding Cake  | 220 | 14699 | 23 |
| epi:O6AnubtFTHRCpRXUcqjoJ8AC.N2L3Ym | Maine Lobster Bake  | 198 | 16494 | 16 |
| epi:MK94XksyZda2rfmXwsqcKgnOXmNHye2 | Classic Roast Turkey With Herbed Stuffing and Old-Fashioned Gravy  | 167 | 16344 | 19 |
| epi:HdesmXxKS5AZpPwviPnlLvCQE0/aE1S | Boysenberry-Grand Marnier Ice Cream Bonbons  | 164 | 8652 | 11 |

## 3. Possible under-splitting (1 step but long text)

- recipes with exactly 1 step: 1304
- of those, with more than 400 characters of instructions: 1

| id | title | chars | start of instructions_clean |
|---|---|---|---|
| epi:X/EbOfi47I5FcAVpv5TE.LMP4RdrKqu | Bean Salad with Lemon and Herbs  | 499 | Toss 2 cups fresh cooked shell beans (such as cannellini or cranberry) or one 14-ounce can cannellini beans or chickpeas, rinsed, 6 ounces green beans (trimmed, cut into 1" pieces), 1/4 cup fresh parsley leaves with tend |

Brunswick Stew recipes (full cleaned instructions):

- `ar:VaZnpzH6pGqrBgnqdWMWhjHMwgT.wL2` Easy Brunswick Stew, n_steps=1
  > Combine cream-style corn, diced tomatoes, chicken, pork, sweet corn, ketchup, tomato sauce, water, bacon drippings, barbeque sauce, Worcestershire sauce, hot sauce, and black pepper together in a Dutch oven or stockpot; simmer over low heat until heated through, 20 to 45 minutes.
- `ar:21EhITSmtx4JLpQs50auvWviSGIpyn.` Leftover Roast Brunswick Stew, n_steps=3
  > Place the shredded roast in a slow cooker. Mix in the vegetables with liquid, barbeque sauce, Worcestershire sauce, and beef broth. Cover, and cook at least 1 hour on High.
- `ar:Nuw.pdi5D1mRjYbVMRRLTS5wwYn/mHC` Harmon's Brunswick Stew , n_steps=4
  > Melt butter in a skillet over medium-high heat. Saute onion in melted butter until tender, 5 to 7 minutes. Stir sauteed onion, cream-style corn, crushed tomatoes, white chicken chunks, pork in barbeque sauce, beef in barbeque sauce, Worcestershire sauce, black pepper, salt, and hot sauce together in a slow cooker crock. Cook on High until hot, at least 30 minutes.

## 4. Recipes with no canonical ingredient

| id | title | ingredient lines |
|---|---|---|
| fn:9qlI6nIVRMeuWfQSX4EZX3eyHNr8oZq | Almond and Sugar Powder | 6 ounces, or 1 cup plus 2 tablespoons, blanched or raw almonds // 6 ounces, or 1 1/4 cups plus 3 tablespoons, confectioners' sugar |
| fn:6AdCFCZR4cr1NzOtloWzWuOmDewvFGG | Title | 1 cup |
| fn:6RFXdT0/33sy7kMqbXAQTT2k4ElYQfG | prodtest | 1 |
| fn:dfWHO68vsCnbQPkcs0AWZv3jBapkvXO | CALIFORNIA AVOCADO TOAST THREE WAYS (Sponsored) | - |

## 5. Lines with a 'prefix:' (candidates for non-ingredient lines)

| prefix | lines | example canonical | example line |
|---|---|---|---|
| special equipment | 1693 | food mill | SPECIAL EQUIPMENT: Eight 6-ounce aluminum tins |
| garnish | 728 | almond | Garnish: 1 (1 1/2-inch-long) lemon twist |
| accompaniment | 703 | accompaniment | Accompaniment: "epi:recipeLink id="238426">honeyed red-onion confit |
| equipment | 414 | deep skillet | Equipment: 1 (9- by 5- by 3-inch) loaf pan; stand mixer fitted with paddle attachment; 1 t... |
| ingredient info | 284 | ingredient info | Ingredient Info: All-butter puff pastry is available frozen at Whole Foods markets. One 14... |
| serving suggestion | 265 | pastry | Serving Suggestion: 1 1/2 cups reduced-fat vanilla ice cream or nonfat frozen vanilla yogu... |
| serving suggestions | 175 | piling the relish and the chicken in warm pita is fun way | Serving Suggestions: Asparagus with Prosciutto |
| accompaniments | 137 | accompaniment | Accompaniments: 1/2-inch cubes of California avocado; chopped fresh cilantro; tortilla chi... |
| optional | 34 | almond | Optional: 1 jalapeno, chopped |
| garnishes | 23 | arugula | Garnishes: Pickled cauliflower on a skewer, avocado slice on a skewer or a long strip of b... |
| suggested toppings | 19 | suggested topping | Suggested toppings: 1 cup lightly whipped and chilled creme fraiche, sliced jalapenos, fre... |
| 1 teaspoon hot sauce (recommended | 17 | hot sauce | 1 teaspoon hot sauce (recommended: Frank's Red Hot) |
| toppings | 17 | bibb lettuce | Toppings: 1/2 chopped apple, chopped walnuts, pure maple syrup |
| 2 tablespoons hot sauce (recommended | 15 | hot sauce | 2 tablespoons hot sauce (recommended: Frank's Hot Sauce) |
| for serving | 13 | assorted pita chip | For serving: Corn tortillas, black bread, or cucumber slices, as desired. |
| optional garnishes | 13 | caramel sauce | Optional garnishes: Fresh lime slices |
| 1/2 teaspoon hot sauce (recommended | 13 | hot sauce | 1/2 teaspoon hot sauce (recommended: Frank's Red Hot) |
| 1/4 cup orange liqueur (recommended | 12 | orange liqueur | 1/4 cup orange liqueur (recommended: Cointreau or Grand Marnier) |
| hot sauce (recommended | 12 | hot sauce | Hot sauce (recommended: Crystal's) |
| optional garnish | 12 | blackberry | Optional garnish: 1/2 cup (2 1/2 ounces) pomegranate seeds |
| 1 tablespoon hot sauce (recommended | 11 | hot sauce | 1 tablespoon hot sauce (recommended: Frank's Red Hot) |
| accompaniment if desired | 11 | accompaniment | Accompaniment if desired: Apple and Celery Salad |
| test-kitchen tip | 11 | test-kitchen tip | Test-Kitchen Tip: To release the most flavor from the lemongrass stalk, it's important to ... |
| special equipment  | 11 | special equipment | Special equipment : a 1- to 1 1/2-quart teapot |
| 1/4 cup sugar substitute (recommended | 10 | sugar substitute | 1/4 cup sugar substitute (recommended: Splenda) |
| 1/2 cup sugar substitute (recommended | 10 | sugar substitute | 1/2 cup sugar substitute (recommended: Splenda) |
| **ingredient info | 10 | agave syrup nectar | **Ingredient Info:**Semolina flour (pasta flour) is available at better supermarkets and a... |
| 2 teaspoons hot sauce (recommended | 10 | hot sauce | 2 teaspoons hot sauce (recommended: Frank's Red Hot) |
| **special equipment | 10 | special equipment | **Special Equipment:**10" springform cake pan or eight 2/3 or 3/4-cup ramekins or custard ... |
| bouquet garni | 8 | bouquet garni | Bouquet garni: 1 peeled clove garlic, 4 sprigs parsley, 1 bay leaf and 1 teaspoon dried ro... |
| 1 teaspoon crushed garlic (recommended | 8 | garlic | 1 teaspoon crushed garlic (recommended: Christopher Ranch) |
| note | 8 | note | NOTE: You¿ll also need 4 ovenproof bowls or ramekins, about 2 cups each. |
| 1/3 cup sugar substitute (recommended | 7 | sugar substitute | 1/3 cup sugar substitute (recommended: Splenda) |
| dash hot sauce (recommended | 7 | hot sauce | Dash hot sauce (recommended: Tabasco) |
| 1 bouquet garni | 7 | bouquet garni | 1 bouquet garni: 1 sprig fresh thyme or 1/4 teaspoon dried, 2 chives, 1 sprig parsley |
| 3/4 cup sugar substitute (recommended | 7 | sugar substitute | 3/4 cup sugar substitute (recommended: Splenda) |
| 3 tablespoons hot sauce (recommended | 6 | hot sauce | 3 tablespoons hot sauce (recommended: Crystal) |
| suggested dippers | 6 | suggested dipper | Suggested dippers: fruit, pretzels, cookies, etc. |
| 1/2 cup hot sauce (recommended | 6 | hot sauce | 1/2 cup hot sauce (recommended: Crystal) |
| 1 cup sugar substitute (recommended | 6 | sugar substitute | 1 cup sugar substitute (recommended: Splenda) |

## 6. Candidate descriptor words inside canonical names

| word | distinct names | recipes | top examples |
|---|---|---|---|
| homemade | 204 | 511 | homemade chicken stock (124), homemade-type white bread (22), homemade chicken broth (18) |
| store-bought | 326 | 560 | store-bought pizza dough (52), store-bought pesto (19), store-bought puff pastry (18) |
| reduced-sodium | 36 | 630 | reduced-sodium chicken broth (322), reduced-sodium soy sauce (201), reduced-sodium beef broth (39) |
| low-sodium | 113 | 1911 | low-sodium chicken broth (1031), low-sodium soy sauce (366), low-sodium chicken stock (167) |
| small-diced | 33 | 75 | small-diced red onion (21), small-diced celery (15), small-diced carrot (13) |
| unsalted | 252 | 17490 | unsalted butter (16062), cold unsalted butter (1010), unsalted pistachio (62) |
| fresh | 23 | 27 | fresh-flat leaf parsley (3), fresh-cut green bean (2), farm-fresh egg (2) |
| dried | 1489 | 14054 | dried oregano (2992), dried thyme (1592), dried basil (1182) |
| frozen | 3 | 3 | individually quick-frozen raspberry (1), half-frozen watermelon (1), semi-frozen peach (1) |
| organic | 318 | 428 | organic egg (29), organic spinach (20), organic lemon (15) |
| plain | 332 | 2558 | plain yogurt (880), plain greek yogurt (183), plain bread crumb (102) |
| light | 350 | 5669 | light brown sugar (2762), light corn syrup (1065), light soy sauce (270) |
| extra-virgin | 93 | 10872 | extra-virgin olive oil (10633), drizzle extra-virgin olive oil (29), high-quality extra-virgin olive oil (17) |
| freshly | 11 | 37 | freshly-squeezed lemon juice (11), freshly-squeezed orange juice (8), freshly-ground pepper (6) |
| good-quality | 217 | 441 | good-quality white chocolate (50), good-quality semisweet chocolate (15), good-quality milk chocolate (13) |
| high-quality | 78 | 178 | high-quality white chocolate (32), high-quality milk chocolate (19), high-quality extra-virgin olive oil (17) |

## 7. Variant pairs: how often each form appears, and together

| base | recipes | specific form | recipes | recipes with both |
|---|---|---|---|---|
| butter | 20278 | unsalted butter | 16062 | 537 |
| olive oil | 20414 | extra-virgin olive oil | 10633 | 690 |
| sugar | 17560 | white sugar | 9987 | 55 |
| salt | 47624 | kosher salt | 18753 | 1019 |
| pepper | 12468 | black pepper | 31106 | 756 |
| cinnamon | 1509 | ground cinnamon | 7591 | 63 |
| flour | 2690 | all-purpose flour | 20804 | 111 |
| milk | 9408 | whole milk | 3391 | 47 |
| onion | 19256 | red onion | 6100 | 239 |

## 8. Lines containing ' and ' that produced only one ingredient row

- line occurrences: 59953 (many are fine, e.g. 'macaroni and cheese' as one product)

| line | canonical |
|---|---|
| 1 (14-oz) can Italian plum tomatoes in juice, drained and chopped | italian plum tomatoes in juice |
| 1 pound ground beef, browned and drained of all fat, or use leftover, cooked, and minced meat | ground beef |
| 1 fresh jalapeno, seeded and chopped | jalapeno |
| 2 to 4 small thin fresh red or green Asian chilies (1 to 2 inches long) or serrano chilies, seeded a... | red asian chili |
| 7 ounces tiny macaroni, cooked al denta and tossed with olive oil | macaroni |
| A 3/4-pound piece salmon fillet, skin discarded and fish cut into 1/4-inch pieces | salmon fillet |
| 1/2 small cantaloupe, peeled and chopped (about 2 1/2 cups) | cantaloupe |
| 2 cloves garlic, unpeeled and smashed | garlic |
| 1 butternut squash peeled, seeded and chunked | butternut squash |
| 1 zucchini, halved and cut into 1/4-inch semi circles | zucchini |
| 2 large garlic cloves, crushed and minced to a paste | garlic |
| 1 red bell pepper, seeded and cored, sliced | red bell pepper |
| 4 large carrots, peeled and sliced lengthwise | carrot |
| 1 pound Brussels sprouts, bases trimmed, outer leaves removed and halved | brussels sprout |
| 3/8 stick/1 1/2 oz/40g butter, chilled and cubed | butter |
| 20 jumbo snails, poached in lightly salted water and removed from their shells | snail |
| 24 deveined shrimp, peeled, tails off, if your fish counter won't do this for you, ask for easy-peel... | shrimp |
| 1 small fennel bulb, halved, cored and diced | fennel |
| 1/2 pound assorted wild mushrooms (such as oyster, crimini, morel and stemmed shiitake), sliced | assorted wild mushroom |
| 4 whole bone-in, skin-on chicken breasts (for all white meat) or 3 whole 4-pound chickens (for a mix... | whole bone-in skin-on chicken breast |

