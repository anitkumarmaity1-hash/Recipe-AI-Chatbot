"""Find recipes by the ingredients you have (backend: RecipeMatcher through the agent pipeline)."""

from __future__ import annotations

import streamlit as st

from ui import components as C
from ui import services
from ui.engine import Engine
from ui.styles import STRETCH
from ui.errors import guarded
from ui.session import chat_restrictions

KEY_LIST = "finder_ingredients"
EXAMPLE = ["eggs", "onion", "tomato", "rice"]


def _add_from_input() -> None:
    items = st.session_state.get(KEY_LIST, [])
    for term in services.split_terms(st.session_state.get("finder_new", "")):
        if term not in items:
            items.append(term)
    st.session_state[KEY_LIST] = items
    st.session_state["finder_new"] = ""


def _use_example() -> None:
    st.session_state[KEY_LIST] = list(EXAMPLE)


def _import_chat() -> None:
    r = chat_restrictions()
    st.session_state["finder_allergens"] = r["allergens"]
    st.session_state["finder_exclude"] = ", ".join(r["exclude"])
    st.session_state["finder_limit"] = r["max_steps"] is not None
    if r["max_steps"] is not None:
        st.session_state["finder_steps"] = r["max_steps"]


def render(engine: Engine) -> None:
    C.page_header("Find Recipes by Ingredients",
                  "Tell us what is in your kitchen. Recipes are ranked by the project's matching score.")
    st.session_state.setdefault(KEY_LIST, [])
    items: list[str] = st.session_state[KEY_LIST]

    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.subheader("Your ingredients")
        with st.form("finder_add", clear_on_submit=False, border=False):
            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            c1.text_input("Add ingredients (separate several with commas)", key="finder_new",
                          placeholder="e.g. eggs, flour, milk")
            c2.form_submit_button("Add", on_click=_add_from_input, **STRETCH)
        if items:
            cols = st.columns(4)
            for i, name in enumerate(items):
                if cols[i % 4].button(f"✕  {name}", key=f"rm_{i}", help="Remove", **STRETCH):
                    items.remove(name)
                    st.rerun()
            st.button("Clear all", key="finder_clear",
                      on_click=lambda: st.session_state.update({KEY_LIST: []}))
        else:
            st.caption("Nothing added yet.")
            st.button("Use an example (eggs, onion, tomato, rice)",
                      on_click=_use_example)

    with right:
        st.subheader("Restrictions")
        st.multiselect("Exclude allergens", engine.allergens, key="finder_allergens",
                       format_func=C.label, placeholder="e.g. dairy, egg, peanut",
                       help="Checked on every ingredient line of every recipe shown.")
        st.text_input("Exclude ingredients (comma separated)", key="finder_exclude", placeholder="e.g. mushrooms, cilantro",
                      help="Phrases such as “dairy” or “nuts” are treated as allergen categories, like in the chat.")
        limit = st.checkbox(
            "Limit the number of cooking steps", key="finder_limit")
        steps = st.slider("Maximum steps", 1, 50, 8,
                          key="finder_steps", disabled=not limit)
        k = st.slider("Number of recipes", 1, engine.max_k,
                      engine.default_k, key="finder_k")
        st.button("Import restrictions from my chat", on_click=_import_chat, icon=":material/sync:",
                  help="Copies the allergens, excluded ingredients and step limit remembered by the chat.")

    go = st.button("Find recipes", type="primary",
                   icon=":material/search:", disabled=not items)
    if go:
        restrictions = services.Restrictions(
            allergens=tuple(st.session_state.get("finder_allergens", [])),
            exclude=tuple(services.split_terms(
                st.session_state.get("finder_exclude", ""))),
            max_steps=steps if limit else None)
        with guarded("matching recipes"):
            try:
                with st.spinner("Matching recipes…"):
                    run = services.find_by_ingredients(
                        engine, items, restrictions, k)
            except services.RequestError as exc:
                st.error(str(exc))
                return
            st.session_state["finder_result"] = {"payload": run.payload, "text": run.reply.text,
                                                 "withheld": run.withheld, "unenforced": run.unenforced,
                                                 "tool": run.reply.tool}
    result = st.session_state.get("finder_result")
    if result:
        st.divider()
        _show(result)
    elif not items:
        st.info("Add a few ingredients above and press **Find recipes**.",
                icon=":material/kitchen:")


def _show(result: dict) -> None:
    payload, text = result["payload"], result["text"]
    if result["withheld"]:
        st.error(text, icon=":material/gpp_maybe:")
        return
    if payload is None or result["tool"] != "match":
        # e.g. an excluded ingredient that is not in the dataset: the backend explains and nothing changed
        st.warning(text, icon=":material/info:")
        return

    cons = payload["constraints"]
    C.restriction_chips(cons, result["unenforced"])
    for item in payload["unknown"]:
        hint = f" Did you mean: {', '.join(item['suggestions'])}?" if item["suggestions"] else ""
        st.warning(
            f"Not recognized, ignored: “{item['term']}”.{hint}", icon=":material/help:")
    for name in payload["dropped"]:
        st.warning(
            f"Not counted: “{name}” is in your list but you also excluded it.", icon=":material/block:")

    if not payload["terms"] or not payload["hits"]:
        st.info(payload["note"] or "No recipe matched.",
                icon=":material/search_off:")
        C.allergen_notice(cons)
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Ingredients used", len(payload["terms"]))
    m2.metric("Recipes using at least one", f'{payload["n_candidates"]:,}')
    m3.metric("Pass your filters", f'{payload["n_eligible"]:,}')
    st.caption("Nothing was relaxed: every recipe below passed the hard filters and was re-verified "
               "from the database. Recipes without instructions are not ranked.")
    C.match_hits(payload["hits"], payload["terms"],
                 payload["settings"], "finder")
    C.match_explanation(payload["settings"])
    C.allergen_notice(cons)
    with st.expander("Full grounded answer (audit text)"):
        st.code(text, language="text")
