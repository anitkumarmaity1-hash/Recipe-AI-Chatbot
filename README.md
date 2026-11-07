# NOSH Recipe AI Chatbot

A grounded conversational recipe assistant over the Recipe Box dataset (~125k recipes).
The LLM only interprets questions and words answers; all facts, counts, filtering,
ranking and validation are computed deterministically from the data.

> Work in progress. Full setup, usage, evaluation and design notes will be added as the project is built.

## Quick start (Windows PowerShell)

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    pip install -e .
    pytest

## Data

    python scripts/download_data.py     # downloads the 3 raw JSON files into data/raw/
    python -m recipebot.eda             # prints and saves docs/EDA_REPORT.md