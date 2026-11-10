"""Ingredient substitution assistant (backend: SubstitutionMiner + adaptation through the agent)."""

from __future__ import annotations

import streamlit as st

from ui import components as C
from ui import queries, services
from ui.engine import Engine
from ui.styles import STRETCH
from ui.errors import guarded
from ui.session import chat_restrictions

KEY_ID = "sub_recipe_id"


def _import_chat() -> None:
    r = chat_restrictions()
    st.session_state["sub_allergens"] = r["allergens"]
    st.session_state["sub_exclude"] = ", ".join(r["exclude"])
    st.session_state["sub_limit"] = r["max_steps"] is not None
    if r["max_steps"] is not None:
        st.session_state["sub_steps"] = r["max_steps"]


def _picker(engine: Engine) -> str | None:
    """Choose the recipe: by a search, or by pasting a recipe id."""
    chosen = st.session_state.get(KEY_ID)
    t_search, t_id = st.tabs(["Search by name", "Use a recipe id"])
    with t_search:
        with st.form("sub_search", border=False):
            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            query = c1.text_input("Dish or ingredient",
                                  placeholder="e.g. banana bread, penne pasta")
            submitted = c2.form_submit_button("Search", **STRETCH)
        if submitted:
            try:
                with st.spinner("Searching…"):
                    run = services.search_recipes(engine, query, k=8)
                hits = (run.payload or {}).get(
                    "hits", []) if not run.withheld else []
                st.session_state["sub_hits"] = [
                    {"id": h["id"], "title": h["title"]} for h in hits]
                if not hits:
                    st.info("No recipe found for that search.")
            except services.RequestError as exc:
                st.error(str(exc))
        hits = st.session_state.get("sub_hits", [])
        if hits:
            options = [h["id"] for h in hits]
            titles = {h["id"]: h["title"] for h in hits}
            pick = st.selectbox("Pick a recipe", options, format_func=lambda i: f"{titles[i]}  [{i}]",
                                key="sub_pick")
            if st.button("Use this recipe", key="sub_use_pick", icon=":material/check:"):
                st.session_state[KEY_ID] = pick
                st.rerun()
    with t_id:
        with st.form("sub_by_id", border=False):
            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            rid = c1.text_input("Recipe id", placeholder="e.g. ar:abc123")
            go = c2.form_submit_button("Use", **STRETCH)
        if go and rid.strip():
            st.session_state[KEY_ID] = rid.strip()
            st.rerun()
    return chosen


def render(engine: Engine) -> None:
    C.page_header("Ingredient Substitution",
                  "Replace an ingredient using evidence from other recipes in the dataset, "
                  "clearly separated from general cooking knowledge.")
    recipe_id = _picker(engine)
    if not recipe_id:
        st.info("Choose a recipe to begin.", icon=":material/menu_book:")
        return

    record = queries.recipe_record(engine, recipe_id)
    if record is None:
        st.error(f"I have no recipe with the id “{recipe_id}”.")
        if st.button("Choose another recipe"):
            st.session_state.pop(KEY_ID, None)
            st.rerun()
        return

    st.divider()
    with st.container(border=True):
        C.recipe_header(record["title"], record["id"],
                        f'{record["source_label"]} · {record["n_steps"]} steps')
        with st.expander("Ingredients of this recipe"):
            C.html_block(
                "".join(f'<div class="nosh-line">{C.esc(x)}</div>' for x in record["lines"]))
        if st.button("Choose a different recipe", key="sub_change"):
            st.session_state.pop(KEY_ID, None)
            st.session_state.pop("sub_result", None)
            st.rerun()

    bases = queries.ingredient_bases(engine, recipe_id)
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Ingredient to replace")
        ingredient = st.selectbox("Ingredient", bases, key=f"sub_ing_{recipe_id}",
                                  help="Names the substitution tool understands for this recipe.")
    with right:
        st.subheader("Restrictions")
        st.multiselect("Exclude allergens", engine.allergens, key="sub_allergens", format_func=C.label,
                       help="Substitutes and cited recipes must obey these.")
        st.text_input("Exclude ingredients (comma separated)",
                      key="sub_exclude", placeholder="e.g. mushrooms")
        limit = st.checkbox(
            "Limit the number of steps of cited recipes", key="sub_limit")
        steps = st.slider("Maximum steps", 1, 50, 10,
                          key="sub_steps", disabled=not limit)
        st.button("Import restrictions from my chat", key="sub_import", on_click=_import_chat,
                  icon=":material/sync:")

    if st.button("Find substitutes", type="primary", icon=":material/swap_horiz:", disabled=not bases):
        restrictions = services.Restrictions(
            allergens=tuple(st.session_state.get("sub_allergens", [])),
            exclude=tuple(services.split_terms(
                st.session_state.get("sub_exclude", ""))),
            max_steps=steps if limit else None)
        with guarded("looking for substitutes"):
            try:
                with st.spinner("Mining the dataset for evidence…"):
                    run = services.substitute(
                        engine, recipe_id, ingredient, restrictions)
            except services.RequestError as exc:
                st.error(str(exc))
                return
            st.session_state["sub_result"] = {
                "recipe_id": recipe_id, "ingredient": ingredient, "tool": run.reply.tool,
                "payload": run.payload, "text": run.reply.text, "withheld": run.withheld,
                "unenforced": run.unenforced}

    result = st.session_state.get("sub_result")
    if result and result["recipe_id"] == recipe_id:
        st.divider()
        if result["withheld"]:
            st.error(result["text"], icon=":material/gpp_maybe:")
        elif result["tool"] != "substitute" or result["payload"] is None:
            # for example: the ingredient is not in the recipe, or a restriction is unknown
            st.warning(result["text"], icon=":material/info:")
        else:
            C.substitution_result(
                result["payload"], result["text"], result["unenforced"], "sub")
