# NOSH Recipe AI Chatbot

A grounded conversational recipe assistant over the Recipe Box dataset (~125k recipes).
The LLM only interprets questions and words answers; all facts, counts, filtering,
ranking and validation are computed deterministically from the data.

> Work in progress. The agent loop, matching, substitution and UI are not built yet.

## Quick start (Windows PowerShell)

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    pip install -e .
    pytest

## Build the data (run once, from the project root, venv active)

    python scripts/download_data.py            # 3 raw JSON files into data/raw/
    python -m recipebot.build_db               # DuckDB: recipes + recipes_excluded (about 15 s)
    python -m recipebot.build_normalized       # parser cache + recipe_ingredient + recipe_stats (first run about 25 min)
    python -m recipebot.build_indexes bm25     # BM25 index (seconds)
    python -m recipebot.build_indexes embeddings   # MiniLM vectors + FAISS (about 25 min, resumable)

## Try it

    python -m recipebot.tools.stats count --all-of garlic onion
    python -m recipebot.retrieval.hybrid "penne pasta" --exclude-allergen dairy -k 5
    python -m recipebot.retrieval.hybrid "banana bread" --exclude egg --max-steps 8

Set up the language model once: copy `.env.example` to `.env`, put your key in `GEMINI_API_KEY` (never commit it), then:

    python -m recipebot.understanding.backend "I cannot have dairy"

The first query with `--exclude-allergen` scans all ingredient lines once and caches the result in `data/index/allergen_flags.npz`.
Details of every design decision: `docs/DESIGN.md`. AI tools used: `AI_USAGE.md`.