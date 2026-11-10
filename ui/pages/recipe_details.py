"""Recipe details: cleaned ingredients, numbered steps and warnings for the active chat restrictions."""

from __future__ import annotations

import streamlit as st

from ui import components as C
from ui import navigation, services
from ui.engine import Engine
from ui.styles import STRETCH
from ui.errors import guarded
from ui.session import chat_restrictions

KEY = "recipe_id"


def render(engine: Engine) -> None:
    C.page_header("Recipe Details",
                  "The full cleaned recipe from the dataset, with warnings for your restrictions.")
    with st.form("recipe_lookup", border=False):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        rid = c1.text_input("Recipe id", value=st.session_state.get(
            KEY, ""), placeholder="e.g. ar:abc123")
        go = c2.form_submit_button("Show", **STRETCH)
    if go:
        st.session_state[KEY] = rid.strip()
    recipe_id = st.session_state.get(KEY, "")
    if not recipe_id:
        st.info("Open a recipe from a search result, the ingredient finder or the analytics page, "
                "or paste a recipe id above.", icon=":material/menu_book:")
        return

    r = chat_restrictions()
    with guarded("loading the recipe"):
        detail = services.recipe_detail(
            engine, recipe_id, r["allergens"], r["exclude"])
        if isinstance(detail, str):
            st.warning(detail, icon=":material/search_off:")
            return
        if r["allergens"] or r["exclude"]:
            C.html_block('<div class="nosh-label">Active restrictions from your chat</div>'
                         + C.chips([f"no {C.label(a)}" for a in r["allergens"]]
                                   + [f"no {x}" for x in r["exclude"]], "bad"))
        C.recipe_detail(detail, restrictions_active=bool(
            r["allergens"] or r["exclude"]))
        if r["allergens"]:
            C.allergen_notice({"exclude_allergens": r["allergens"]})
        if st.button("Replace an ingredient in this recipe", icon=":material/swap_horiz:"):
            navigation.goto("substitution", sub_recipe_id=detail.id)
