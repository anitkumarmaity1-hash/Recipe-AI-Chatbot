# Normalization diagnostics (Step 4b-1)

Generated: 2026-11-08T01:23:08

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
| epi:KJ.dr1VHkKIiGvHArDT0hfqbjjEe.ha | To Roast Fresh Chestnuts  | Special equipment: a chestnut knife and protective gloves |
| fn:9qlI6nIVRMeuWfQSX4EZX3eyHNr8oZq | Almond and Sugar Powder | 6 ounces, or 1 cup plus 2 tablespoons, blanched or raw almonds // 6 ounces, or 1 1/4 cups plus 3 tablespoons, confectioners' sugar |
| fn:6AdCFCZR4cr1NzOtloWzWuOmDewvFGG | Title | 1 cup |
| fn:6RFXdT0/33sy7kMqbXAQTT2k4ElYQfG | prodtest | 1 |
| fn:dfWHO68vsCnbQPkcs0AWZv3jBapkvXO | CALIFORNIA AVOCADO TOAST THREE WAYS (Sponsored) | - |

## 5. Lines with a 'prefix:' (candidates for non-ingredient lines)

| prefix | lines | example canonical | example line |
|---|---|---|---|
| garnish | 728 | almond | Garnish: 1 (1 1/2-inch-long) lemon twist |
| optional | 34 | almond | Optional: 1 jalapeno, chopped |
| garnishes | 23 | arugula | Garnishes: Pickled cauliflower on a skewer, avocado slice on a skewer or a long strip of b... |
| suggested toppings | 19 | almond | Suggested toppings: 1 cup lightly whipped and chilled creme fraiche, sliced jalapenos, fre... |
| toppings | 17 | apple | Toppings: 1/2 chopped apple, chopped walnuts, pure maple syrup |
| 1 teaspoon hot sauce (recommended | 17 | hot sauce | 1 teaspoon hot sauce (recommended: Frank's Red Hot) |
| 2 tablespoons hot sauce (recommended | 15 | hot sauce | 2 tablespoons hot sauce (recommended: Frank's Hot Sauce) |
| 1/2 teaspoon hot sauce (recommended | 13 | hot sauce | 1/2 teaspoon hot sauce (recommended: Frank's Red Hot) |
| optional garnishes | 13 | caramel sauce | Optional garnishes: Fresh lime slices |
| for serving | 13 | any combination of bread stick | For serving: Corn tortillas, black bread, or cucumber slices, as desired. |
| hot sauce (recommended | 12 | hot sauce | Hot sauce (recommended: Crystal's) |
| 1/4 cup orange liqueur (recommended | 12 | orange liqueur | 1/4 cup orange liqueur (recommended: Cointreau or Grand Marnier) |
| optional garnish | 12 | blackberry | Optional garnish: 1/2 cup (2 1/2 ounces) pomegranate seeds |
| 1 tablespoon hot sauce (recommended | 11 | hot sauce | 1 tablespoon hot sauce (recommended: Frank's Red Hot) |
| 1/2 cup sugar substitute (recommended | 10 | sugar substitute | 1/2 cup sugar substitute (recommended: Splenda) |
| 1/4 cup sugar substitute (recommended | 10 | sugar substitute | 1/4 cup sugar substitute (recommended: Splenda) |
| 2 teaspoons hot sauce (recommended | 10 | hot sauce | 2 teaspoons hot sauce (recommended: Frank's Red Hot) |
| bouquet garni | 8 | bouquet garni | Bouquet garni: 1 peeled clove garlic, 4 sprigs parsley, 1 bay leaf and 1 teaspoon dried ro... |
| 1 teaspoon crushed garlic (recommended | 8 | garlic | 1 teaspoon crushed garlic (recommended: Christopher Ranch) |
| 1/3 cup sugar substitute (recommended | 7 | sugar substitute | 1/3 cup sugar substitute (recommended: Splenda) |
| 1 bouquet garni | 7 | bouquet garni | 1 bouquet garni: 1 sprig fresh thyme or 1/4 teaspoon dried, 2 chives, 1 sprig parsley |
| dash hot sauce (recommended | 7 | hot sauce | Dash hot sauce (recommended: Tabasco) |
| 3/4 cup sugar substitute (recommended | 7 | sugar substitute | 3/4 cup sugar substitute (recommended: Splenda) |
| 3 tablespoons hot sauce (recommended | 6 | hot sauce | 3 tablespoons hot sauce (recommended: Crystal) |
| 1/2 cup hot sauce (recommended | 6 | hot sauce | 1/2 cup hot sauce (recommended: Crystal) |
| egg wash | 6 | egg wash | Egg Wash: 1 egg well beaten with a pinch of salt |
| 1 cup sugar substitute (recommended | 6 | sugar substitute | 1 cup sugar substitute (recommended: Splenda) |
| crab boil seasoning (recommended | 5 | crab boil seasoning | Crab boil seasoning (recommended: Old Bay) |
| 1 tablespoon orange liqueur (recommended | 5 | orange liqueur | 1 tablespoon orange liqueur (recommended: Grand Marnier) |
| 1 (28-ounce) can tomatoes (recommended | 5 | tomato | 1 (28-ounce) can tomatoes (recommended: San Marzano) |
| even easier | 5 | even easier purchased chocolate cookie crust | Even easier: High-quality purchased lemon curd can be used in place of homemade. |
| grill seasoning (recommended | 5 | grill seasoning | Grill seasoning (recommended: Grill Mates Montreal Steak Seasoning by McCormick) or coarse... |
| 1/4 cup hot sauce (recommended | 5 | hot sauce | 1/4 cup hot sauce (recommended: Crystal) |
| for garnish | 5 | cilantro | For garnish: 2 tablespoons toasted sesame seeds and a few pineapple rings (use good qualit... |
| pan preparation | 5 | pan preparation | Pan Preparation: Butter the pan(s) or spray with butter-flavor nonstick vegetable spray an... |
| suggested garnishes | 5 | suggested garnish | Suggested garnishes: Fresh whipped cream or marshmallow frosting, dark cocoa powder |
| salt | 4 | salt | Salt: 1/2 teaspoon |
| 2 teaspoons grill seasoning (recommended | 4 | grill seasoning | 2 teaspoons grill seasoning (recommended: Montreal Seasoning by McCormick), half a palm fu... |
| 1 (14-ounce) can beef broth (recommended | 4 | beef broth | 1 (14-ounce) can beef broth (recommended: Swanson's) |
| 1 bottle beer (recommended | 4 | beer | 1 bottle beer (recommended: Abita) |

## 6. Candidate descriptor words inside canonical names

| word | distinct names | recipes | top examples |
|---|---|---|---|
| homemade | 13 | 49 | homemade-type white bread (22), homemade-style white bread (14), homemade-type whole-wheat bread (3) |
| store-bought | 0 | 0 |  |
| reduced-sodium | 0 | 0 |  |
| low-sodium | 0 | 0 |  |
| small-diced | 0 | 0 |  |
| unsalted | 246 | 17489 | unsalted butter (16802), unsalted pistachio (62), unsalted peanut (58) |
| fresh | 19 | 22 | fresh-flat leaf parsley (3), fresh-cut green bean (2), fluid-ounces fresh-squeezed lemon juice (1) |
| dried | 1481 | 14050 | dried oregano (2992), dried thyme (1592), dried basil (1182) |
| frozen | 3 | 3 | half-frozen watermelon (1), individually quick-frozen raspberry (1), semi-frozen peach (1) |
| organic | 0 | 0 |  |
| plain | 324 | 2549 | plain yogurt (878), plain greek yogurt (184), plain bread crumb (103) |
| light | 345 | 5668 | light brown sugar (2763), light corn syrup (1065), light soy sauce (274) |
| extra-virgin | 86 | 12012 | extra-virgin olive oil (11796), drizzle extra-virgin olive oil (29), extra-virgin coconut oil (17) |
| freshly | 7 | 8 | freshly-grated nutmeg (2), freshly-grated ginger (1), freshly-brewed strong coffee (1) |
| good-quality | 0 | 0 |  |
| high-quality | 0 | 0 |  |

## 7. Variant pairs: how often each form appears, and together

| base | recipes | specific form | recipes | recipes with both |
|---|---|---|---|---|
| butter | 20279 | unsalted butter | 16802 | 566 |
| olive oil | 20422 | extra-virgin olive oil | 11796 | 827 |
| sugar | 17567 | white sugar | 9987 | 55 |
| salt | 47624 | kosher salt | 18753 | 1019 |
| pepper | 12474 | black pepper | 31106 | 756 |
| cinnamon | 1511 | ground cinnamon | 7592 | 63 |
| flour | 2693 | all-purpose flour | 20809 | 111 |
| milk | 9410 | whole milk | 3397 | 47 |
| onion | 19264 | red onion | 6118 | 238 |

## 8. Lines containing ' and ' that produced only one ingredient row

- line occurrences: 59664 (many are fine, e.g. 'macaroni and cheese' as one product)

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

