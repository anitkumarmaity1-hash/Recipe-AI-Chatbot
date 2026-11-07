# Normalization report (Step 4, hybrid)

Recipes processed: 121,896

## Steps (rule: one sentence = one step, pysbd on instructions_clean)

| Metric | Value |
|---|---:|
| n_steps min / median / mean / max | 0 / 11.0 / 14.18 / 286 |
| recipes with 0 steps | 48 |
| n_lines median / mean / max | 4.0 / 3.98 / 71 |
| recipes with 1 or fewer non-empty lines | 20,367 |
| n_ingredients min / median / mean / max | 1 / 9.0 / 10.36 / 82 |

## Parser stage (table ingredient_parse)

| Metric | Value |
|---|---:|
| unique cleaned lines in cache | 416,699 |
| parser failures (exception) | 2 |
| parsed but no name found | 360 |

Failure examples: `6 pieces nan bread (or other Mediterranean flat bread)`, `Nan, 1 piece per person`

No-name examples: `8 cups loosely packed, torn, washed, and spun dry romaine lettuce`, `or 1 cup Smucker's® Orchard's Finest® Northwoods Blueberry Preserves`, `1/2 cup or store-bought`, `1/4 cup, or 12 fresh Thai basil leaves (or regular basil leaves), rinsed and dried`, `deveined`, `2 bunches arugula or 1 bunch trimmed watercress`, `2 liters (8 cups) of mussels cooked as above [see note from Gourmet's food editors, below]`, `26 to 40 quart large pot`, `1 1/2 pounds each`, `1 1/4 cups`

## Ingredient rows (table recipe_ingredient)

| Metric | Value |
|---|---:|
| ingredient line occurrences resolved by parser | 1,262,223 |
| resolved by regex fallback | 289 |
| no canonical name (skipped) | 194 |
| rows in recipe_ingredient | 1,302,125 |
| extra rows from multi-name lines ("salt and pepper") | 39,613 |
| rows with alternatives ("butter or margarine") | 30,872 |
| distinct canonical names | 62,761 |
| recipes with no canonical ingredient at all | 4 |
| first-name rows with parser confidence < 0.9 | 59,996 |
| first-name rows with a quantity | 1,150,060 of 1,262,512 |

### Skipped line examples

- `GARNISH`
- `GARNISH`
- `1 1/2 cups frozen, cut okra`
- `GARNISH`
- `350`
- `GARNISH`
- `5 pint jars`
- `Optional Garnish`
- `(Essential oil complement: orange)`
- `A 1-qt. jar`
- `(You will have leftovers)`
- `8 ounces C60`
- `1 5-pound, two 2 1/2-pound, or three 1 1/2-pound head-on fish, such as gray or pink snapper, black sea bass, or branzino, scaled, gutted`
- `peeled`
- `(from 1 or 2 oranges)`

### Parser vs regex: 73,804 of 416,528 distinct lines get a different canonical name

| Cleaned line | Parser+rules (used) | Regex only |
|---|---|---|
| Fresh lime wedges and cucumber slices | lime wedge | lime wedges and cucumber slice |
| Special equipment: 9-inch-diameter cake pan with 2-inch-high sides | special equipment | special equipment inch-diameter cake pan with inch-high side |
| 1 cup medium- or long-grain rice | medium-grain rice |  |
| 3 tablespoons freshly squeezed lime juice (2 limes) | lime juice | squeezed lime juice |
| 1 small tube white decorating icing | white decorating icing | tube white decorating icing |
| 1/4 cup finely ground amaretti crumbs* (from about 5 crisp Italian macaroons) | amaretti crumb | ground amaretti crumb |
| 2 tablespoons Frangelico (hazelnut liqueur; optional) | frangelico hazelnut liqueur | frangelico |
| 2 to 4 small thin fresh red or green Asian chilies (1 to 2 inches long) or serrano chilies, seeded and sliced very thin (wear rubber gloves) | red asian chili | thin red |
| 2 boxes packaged lemon pudding mix (not instant) | packaged lemon pudding mix not instant | packaged lemon pudding mix |
| 7 ounces tiny macaroni, cooked al denta and tossed with olive oil | macaroni | tiny macaroni |
| Juice of 1 lemon, plus wedges for serving | lemon | juice of lemon |
| 20 leaves fresh basil, shredded or torn, plus a few leaves to garnish | basil | leaves basil |
| Thinly sliced avocado and salmon roe, for garnish, optional | avocado | avocado and salmon roe |
| 8 hot or sweet pickled cherry peppers | hot pickled cherry pepper | hot |
| Butter and flour for preparing baking sheet and foil | butter | butter and flour preparing baking sheet and foil |
| 1/4 cup homemade or store-bought reduced-sodium chicken stock | homemade reduced-sodium chicken stock | homemade |
| Twist of orange zest | orange zest | twist of orange zest |
| 3/4 cup crumbled feta cheese | feta cheese | crumbled feta cheese |
| 2 medium red or yellow bell peppers, sliced thin | red bell pepper | red |
| Serving Suggestion: Tartar sauce | suggestion | suggestion tartar sauce |
| 1/2 cup manteca (lard), melted | manteca lard | manteca |
| 1 tablespoon freshly ground or coarsely ground black pepper | black pepper | ground |
| Freshly picked flat-leaf parsley, for garnish | flat-leaf parsley | picked flat-leaf parsley |
| 1 pound thinly sliced fully cooked pork | pork | fully cooked pork |
| 4 6 x 3 x 1/2-inch slices country-style white bread, toasted, each slice cut in half crosswise | country-style white bread | x x inch slices country-style white bread |
| 2 pounds skinless, boneless chicken breasts, cut into 1 1/2-inch pieces | chicken breast |  |
| 1/4 pound Cabrales or other blue cheese, crumbled | cabrales cheese | cabrale |
| pinch of very finely chopped fresh garlic | garlic | very garlic |
| Special equipment: an electric pizzelle maker; a 5 1/2-inch cone-shaped pizzelle mold | special equipment | special equipment electric pizzelle maker inch cone-shaped pizzelle mold |
| 2 thin salmon fillets | salmon fillet | thin salmon fillet |

### Lowest-confidence parser names

| Cleaned line | Canonical | Confidence |
|---|---|---:|
| 1 (6-ounce) container fresh raspberries or 1 cup frozen (thawed) | raspberry | 0.000 |
| 4 (4 ounce) tilapia fillets, fresh or frozen (thawed) | tilapia fillet | 0.000 |
| 1 1/2 cups corn, fresh or frozen (thawed) | corn | 0.000 |
| 1 1/2 cups cranberries, fresh or frozen (thawed) | cranberry | 0.000 |
| 1 cup corn kernels, fresh or frozen (thawed) | corn kernel | 0.000 |
| 1 cup peas, fresh or frozen (thawed) | pea | 0.000 |
| 24 pesticide free rose petals, pink, red, yellow or a combination | pesticide free rose petal | 0.000 |
| Specialty savory sprouts such as daikon, corn, lentil or fenugreek and nasturtium or other edible flower petals, as garnish | specialty savory sprout | 0.000 |
| Or 1 large round or oval loaf, pain de ménage or miche; pain boulot | loaf | 0.000 |
| 4 cups small-diced zucchini (green/yellow) (5 small zucchini) | yellow | 0.000 |
| 4 cups small-diced zucchini (green/yellow) (5 small zucchini) | small-diced zucchini | 0.000 |
| Food coloring, your choices on tan, flesh, red, blue, green, yellow, purple, pink, orange, red, etc. | food coloring | 0.000 |
| Food coloring, your choices on tan, flesh, red, blue, green, yellow, purple, pink, orange, red, etc. | blue | 0.000 |
| 4 apples, Red or Golden Delicious or, 2 of each | apple | 0.000 |
| 4 dozen small hard-shelled (littleneck) clams, well scrubbed | littleneck | 0.001 |
| 4 dozen small hard-shelled (littleneck) clams, well scrubbed | clam | 0.001 |
| 1 head soft lettuce (Boston, Bibb or mixed baby greens) | soft lettuce | 0.001 |
| Special equipment: a 1/2-ounce cookie or ice cream scoop | special equipment | 0.001 |
| 3 tablespoons chopped fresh or 1 tablespoon dried oregano, divided | oregano | 0.001 |
| 2 large onions, white, yellow, or red, thinly sliced | onion | 0.001 |

### Most common units (normalized)

| Unit | Rows |
|---|---:|
| cup | 345,627 |
| tablespoon | 187,783 |
| teaspoon | 180,626 |
| pound | 42,990 |
| ounce | 36,757 |
| clove | 24,453 |
| can | 21,388 |
| package | 14,344 |
| pinch | 11,127 |
| slice | 8,808 |
| sprig | 6,267 |
| bunch | 5,691 |
| stick | 4,789 |
| stalk | 3,479 |
| quart | 3,434 |

### Top 40 canonical names (number of recipes)

| Canonical | Recipes |
|---|---:|
| salt | 47,624 |
| garlic | 32,092 |
| black pepper | 31,106 |
| egg | 25,737 |
| all-purpose flour | 20,804 |
| olive oil | 20,414 |
| butter | 20,278 |
| onion | 19,256 |
| kosher salt | 18,753 |
| sugar | 17,560 |
| unsalted butter | 16,062 |
| water | 15,925 |
| pepper | 12,468 |
| vegetable oil | 11,924 |
| lemon juice | 11,136 |
| extra-virgin olive oil | 10,633 |
| white sugar | 9,987 |
| vanilla extract | 9,722 |
| milk | 9,408 |
| green onion | 8,724 |
| heavy cream | 8,580 |
| baking powder | 7,789 |
| carrot | 7,604 |
| ground cinnamon | 7,591 |
| lemon | 7,307 |
| brown sugar | 6,399 |
| baking soda | 6,236 |
| powdered sugar | 6,232 |
| celery | 6,197 |
| red onion | 6,100 |
| tomato | 6,010 |
| honey | 5,913 |
| parsley | 5,849 |
| shallot | 5,718 |
| cilantro | 5,339 |
| sour cream | 5,012 |
| ginger | 4,732 |
| lime juice | 4,599 |
| egg yolk | 4,598 |
| thyme | 4,590 |

### Deterministic sample: cleaned line -> canonical

| Cleaned line | Canonical |
|---|---|
| 1 large egg | egg |
| 1 tablespoon fresh lemon juice | lemon juice |
| salt and pepper to taste | salt |
| 1/4 cup grated Parmesan | parmesan |
| Salt and pepper | salt |
| 1 onion, finely chopped | onion |
| 1 teaspoon fine sea salt | fine sea salt |
| 3 scallions (white and light green parts only), thinly sliced | green onion |
| Extra-virgin olive oil | extra-virgin olive oil |
| 1 pint heavy cream | heavy cream |
| Kosher salt | kosher salt |
| 2 tablespoons kirsch (clear cherry brandy) | kirsch |
| 1/2 cup light corn syrup | light corn syrup |
| 1/2 cup sugar | sugar |
| 1 pinch cayenne pepper | cayenne pepper |
| 3 tablespoons butter | butter |
| Pinch of kosher salt | kosher salt |
| 1 pint cherry tomatoes, halved | cherry tomato |
| 2 garlic cloves, minced | garlic |
| 1 1/2 teaspoons salt | salt |
| 1 pound boneless, skinless chicken breast halves, cubed | chicken breast half |
| 1/2 cup heavy cream | heavy cream |
| 1/2 cup margarine | margarine |
| Salt and pepper | pepper |
| 1 tablespoon Dijon mustard | dijon mustard |
| 3 ounces of butter | butter |
| 8 shallots, peeled and halved | shallot |
| Simple syrup, poured on a plate to dip glass in | simple syrup |
| 2 cups all-purpose flour | all-purpose flour |
| 1 teaspoon granulated garlic | granulated garlic |
