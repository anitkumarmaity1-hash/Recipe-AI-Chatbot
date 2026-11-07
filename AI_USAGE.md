# AI Tool Usage Disclosure

| Tool | Used for | Notes |
|---|---|---|
| Claude (Anthropic) | Architecture planning, code generation and review, explanations | All code is read, run and understood by the author before commit |
| Gemini (Google AI Studio) | Runtime: query understanding and answer wording inside the chatbot | Facts and statistics come from code, not the LLM |

## Log
- 2026-11-07: Project initialized with AI assistance (Claude).
- 2026-11-07: Day 1 Step 2 (dataset download script, raw-file loader, EDA script and tests) written with Claude; EDA numbers are computed by code from the real files, not written by the AI.
- 2026-11-07: Day 1 Steps 3 and 4 (cleaning rules, DuckDB build, hybrid ingredient normalization, allergen taxonomy) written with Claude. The parser library's API was checked by Claude in a Linux sandbox before use. All dataset numbers come from the author's own runs.
- 2026-11-07/08: Day 1 Steps 4b, 5 and 6 (normalization tuning, statistics tool, BM25 and FAISS indexes) written with Claude and run by the author.
- 2026-11-08: Day 2 Step 7 (hybrid retrieval: constraint masks, RRF, verification) written with Claude. Claude ran the tests in its own sandbox on a tiny database; the author runs them on the real data.