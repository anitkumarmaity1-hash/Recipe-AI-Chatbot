# Evaluation results

11 of 11 cases passed.

| Case | Task | What it checks | Result |
|---|---|---|---|
| T1-search-penne | 1 | dish search returns titles and stable ids | PASS |
| T1-followup-no-dairy | 1 | a new restriction refines the active search (pinned: 51,174 eligible) | PASS |
| T1-count-garlic-onion | 1 | aggregate: count and percentage with denominator (pinned: 10,062 of 121,896) | PASS |
| T1-fewest-steps-tomato | 1 | ranking by instruction steps over the full filtered set (pinned: 6,014 analyzed) | PASS |
| T1-refuse-cooking-time | 1 | refuses an attribute the dataset does not have | PASS |
| T1-refuse-calories | 1 | refuses nutrition values instead of guessing | PASS |
| T1-no-match | 1 | contradictory hard constraints: says nothing matches and relaxes nothing | PASS |
| T2-match-constraints | 2 | ingredient match with a peanut exclusion and a step limit | PASS |
| T2-followup-exclude-eggs | 2 | 'Exclude eggs too' updates the results and keeps the step limit | PASS |
| T3-sub-cream-pasta | 3 | the assignment's own example: replace cream in a pasta recipe without dairy (the recipe used must contain cream) | PASS |
| T3-sub-banana-eggs | 3 | egg-free banana bread: adapted recipe only with real evidence, otherwise an honest weak-evidence answer | PASS |