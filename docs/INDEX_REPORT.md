# Index report

Generated: 2026-11-08T02:23:32

## BM25 (rank_bm25.BM25Okapi)
- documents: 121896
- vocabulary: 19821 tokens
- average tokens per document: 23.4
- build time: 4 s
- pickle size: 18 MB
- load time (startup cost): 0.4 s
- ID fingerprint: 4c97fdedf2412d77

## Sample queries (top 5)

### `penne pasta`
BM25: Penne Pasta with Spinach and Bacon (15.2); Bacon and Parmesan Penne Pasta (15.0); Tuna Alfredo with Penne Pasta (14.7); Creamy Penne Pasta (14.3); Penne Pasta with Cannellini Beans and Escarole (13.9)
Semantic: Creamy Penne Pasta (0.76); Penne with Pancetta and Mushrooms (0.73); Fast Creamy Tomato Penne (0.72); Penne Pasta with Peas and Prosciutto (0.71); Penne with Broiled Vegetables and Feta Cheese  (0.70)

### `chicken tomato garlic`
BM25: Tomato-and-Garlic-Stuffed Chicken Cutlets  (6.7); Tomato Chicken (6.5); Grilled Chicken Breast with Tomato-Tarragon Sauce  (6.5); Stuffed Tomato Basil Chicken (6.4); Tomato Chicken Rice Soup (6.4)
Semantic: Chicken with 20 Cloves of Garlic  (0.69); Chicken with 40 Cloves of Garlic (0.68); Light Tomato Sauce  (0.68); Garlic and Herb Tomatoes (0.68); Chicken with Garlic Sauce  (0.68)

### `banana bread without eggs`
BM25: Chocolate, Peanut Butter and Banana Cupcakes (12.2); Country Banana Bread (11.4); Banana Bread French Toast (11.4); Almond Butter and Finger Bananas on Fruit Bread  (11.3); Peruvian Aji Sauce (11.3)
Semantic: The Best Banana Bread (0.72); Country Banana Bread (0.71); Banana Banana Bread (0.71); Healthier Banana Banana Bread (0.70); Simple Banana Bread (0.70)

### `vegetarian chili`
BM25: Unbelievably Easy and Delicious Vegetarian Chili (12.6); Chili Omelet (11.7); Grandma's Slow Cooker Vegetarian Chili (11.3); Vegetarian Tortilla Stew (11.1); Vegetarian Refried Beans (10.9)
Semantic: The Best Vegetarian Chili in the World (0.79); Vegetarian Chili (0.78); Vegetarian Chili (0.78); Unbelievably Easy and Delicious Vegetarian Chili (0.78); Meatiest Vegetarian Chili From Your Slow Cooker (0.78)

BM25 average query time over 4 queries: 75 ms

Note: neither index understands negation, so 'without eggs' is NOT enforced here. Hard constraints are applied later by SQL (Step 7).
