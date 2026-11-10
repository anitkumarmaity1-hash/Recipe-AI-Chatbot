"""Home: branding, feature overview, dataset statistics and quick actions."""

from __future__ import annotations

import streamlit as st

from ui import cached, navigation
from ui import components as C
from ui.engine import Engine
from ui.styles import STRETCH
from ui.errors import guarded

FEATURES = [
    ("chat", ":material/chat:", "AI Recipe Chat",
     "Ask in plain language, refine with follow-ups, and set allergen or ingredient restrictions as you talk."),
    ("finder", ":material/kitchen:", "Find by Ingredients",
     "List what you have. Recipes are ranked by what matches, what is missing and how many steps they take."),
    ("substitution", ":material/swap_horiz:", "Ingredient Substitution",
     "Swap an ingredient with evidence from similar recipes, and a clear line between data and cooking knowledge."),
    ("analytics", ":material/bar_chart:", "Recipe Analytics",
     "Explore sources, common ingredients and cooking steps across the whole dataset."),
    ("recipe", ":material/menu_book:", "Recipe Details",
     "Read any recipe with cleaned ingredients, numbered steps and warnings for your restrictions."),
    ("about", ":material/info:", "How it works",
     "Why answers come from the database, not from a language model's imagination."),
]
PROMPTS = ["Find me five pasta recipes.", "Find banana bread recipes without eggs.",
           "Among recipes containing tomato, which five have the fewest steps?"]


def render(engine: Engine) -> None:
    C.html_block(
        '<div class="nosh-hero"><div class="tag">NOSH</div>'
        '<h1>NOSH – Your Intelligent Recipe Assistant</h1>'
        '<p>Search recipes in plain language, cook from the ingredients you already have, and adapt a recipe '
        'when something is missing or off limits. Every recipe, number and substitution comes from the '
        'Recipe Box database and is checked again before you see it.</p></div>')

    with guarded("loading dataset statistics"):
        ov = cached.overview(engine, engine.fingerprint)
        ing = cached.stats(engine, engine.fingerprint,
                           "ingredient_count_summary")
        c = st.columns(4)
        c[0].metric("Usable recipes", f'{ov["usable"]:,}')
        c[1].metric("Sources", len(ov["by_source"]), help=", ".join(
            s["label"] for s in ov["by_source"]))
        if ing["ok"] and ing["payload"]["value"]:
            c[2].metric("Median ingredients",
                        f'{ing["payload"]["value"]["median"]:g}')
        if ov["steps"]:
            c[3].metric("Median steps", f'{ov["steps"]["median"]:g}')

    st.subheader("Start here")
    a, b, d = st.columns(3)
    if a.button("Discover recipes", type="primary", icon=":material/search:", **STRETCH):
        navigation.goto("chat")
    if b.button("Match my ingredients", icon=":material/kitchen:", **STRETCH):
        navigation.goto("finder")
    if d.button("Find a substitute", icon=":material/swap_horiz:", **STRETCH):
        navigation.goto("substitution")

    st.subheader("What you can do")
    for row in range(0, len(FEATURES), 3):
        cols = st.columns(3)
        for col, (key, icon, title, text) in zip(cols, FEATURES[row:row + 3]):
            with col:
                with st.container(border=True):
                    st.markdown(f"#### {icon} {title}")
                    st.caption(text)
                    if st.button("Open", key=f"feat_{key}", **STRETCH):
                        navigation.goto(key)

    st.subheader("Try asking")
    cols = st.columns(len(PROMPTS))
    for col, prompt in zip(cols, PROMPTS):
        if col.button(prompt, key=f"prompt_{prompt}", **STRETCH):
            navigation.goto("chat", chat_pending=prompt)
