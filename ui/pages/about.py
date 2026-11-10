"""About / project information: how NOSH works, its limits and the project documents."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from recipebot import config
from ui import components as C
from ui.engine import Engine

DOCS = [("Design decisions", "DESIGN.md"), ("Substitution evidence rules", "SUBSTITUTION.md"),
        ("Ingredient matching", "MATCHING.md"), ("Evaluation", "EVALUATION.md"),
        ("Dataset analysis", "EDA_REPORT.md")]


def render(engine: Engine) -> None:
    C.page_header(
        "About NOSH", "A grounded recipe assistant built on the Recipe Box dataset.")
    st.markdown(
        "NOSH answers questions about **121,896 usable recipes** from AllRecipes, Epicurious and Food Network. "
        "The language model (Gemini) only turns your message into a small structured request. "
        "**Every recipe, id, count, ranking and substitution comes from DuckDB and the search indexes**, "
        "and an output guard re-checks recipe ids and numbers before anything is shown.")
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("How a message is handled")
        st.markdown(
            "1. Requests for data the dataset lacks (cooking time, nutrition) are refused without calling the model.\n"
            "2. Gemini fills an *intent plus slots* request; invalid output is never guessed.\n"
            "3. The session memory merges your restrictions (they persist until you remove them).\n"
            "4. A deterministic tool runs: hybrid search (BM25 + FAISS + reciprocal rank fusion), ingredient "
            "matching, statistics, details or substitution mining.\n"
            "5. Hard constraints are applied *before* ranking, then re-verified independently.\n"
            "6. Answers are composed from templates and checked by the output guard.")
    with right:
        st.subheader("What it cannot do (on purpose)")
        st.markdown(
            "- No cooking times, calories or nutrition: the dataset has none.\n"
            "- Allergen checks read ingredient text only; hidden sources are not detected. "
            "It never claims a recipe is medically safe.\n"
            "- Diets such as “vegan” cannot be proven from ingredient lists and are reported as not enforced.\n"
            "- Substitutions rest on dataset evidence; weak evidence is shown but no adapted recipe is built.\n"
            "- Ingredient quantities are not compared; matches are by name.")
    st.subheader("Status")
    c = st.columns(3)
    c[0].metric("Recipe database", "Connected")
    c[1].metric("Gemini (chat)",
                "Configured" if config.GEMINI_API_KEY and config.GEMINI_MODEL else "Not configured")
    c[2].metric("Understanding backend", config.UNDERSTANDING_BACKEND)
    st.caption("API keys are never displayed.")

    st.subheader("Project documents")
    docs_dir = config.PROJECT_ROOT / "docs"
    tabs = st.tabs([title for title, _ in DOCS])
    for tab, (title, name) in zip(tabs, DOCS):
        with tab:
            path = Path(docs_dir) / name
            if path.exists():
                st.markdown(path.read_text(encoding="utf-8"))
            else:
                st.info(f"{name} was not found in the docs folder.")
