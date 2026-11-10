"""Recipe analytics: statistics from the backend's statistics tool, plus plain counts it lacks."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from recipebot.tools.stats import STEP_RULE
from ui import cached, services
from ui import components as C
from ui.engine import Engine
from ui.styles import STRETCH
from ui.errors import guarded

GREEN, GREY = "#2F7D4F", "#B9B2A3"


def _bar(df: pd.DataFrame, y: str, x: str, x_title: str, height: int | None = None) -> alt.Chart:
    return (alt.Chart(df).mark_bar(color=GREEN, cornerRadiusEnd=4)
            .encode(x=alt.X(f"{x}:Q", title=x_title), y=alt.Y(f"{y}:N", sort="-x", title=None),
                    tooltip=[y, x])
            .properties(height=height or max(180, 26 * len(df))))


def _stat(engine: Engine, stat_type: str, **kw) -> dict:
    return cached.stats(engine, engine.fingerprint, stat_type, **kw)


def render(engine: Engine) -> None:
    C.page_header("Recipe Analytics",
                  "Dataset-level statistics computed live from the DuckDB database.")
    t_over, t_ing, t_steps = st.tabs(
        ["Overview", "Ingredients", "Cooking steps"])
    with t_over:
        with guarded("loading the overview"):
            _overview(engine)
    with t_ing:
        with guarded("computing ingredient statistics"):
            _ingredients(engine)
    with t_steps:
        with guarded("computing step statistics"):
            _steps(engine)


def _overview(engine: Engine) -> None:
    ov = cached.overview(engine, engine.fingerprint)
    total = _stat(engine, "count")
    ing = _stat(engine, "ingredient_count_summary")
    c = st.columns(4)
    c[0].metric("Usable recipes", f'{ov["usable"]:,}')
    c[1].metric("Sources", len(ov["by_source"]))
    if ing["ok"] and ing["payload"]["value"]:
        c[2].metric("Median ingredients / recipe",
                    f'{ing["payload"]["value"]["median"]:g}')
        c[3].metric("Mean ingredients / recipe",
                    f'{ing["payload"]["value"]["mean"]:.2f}')
    st.subheader("Recipes by source")
    df = pd.DataFrame(ov["by_source"]).rename(
        columns={"label": "Source", "recipes": "Recipes"})
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        st.altair_chart(_bar(df, "Source", "Recipes",
                        "Recipes", 150), **STRETCH)
    with right:
        shown = df[["Source", "Recipes"]].copy()
        shown["Share"] = (shown["Recipes"] /
                          shown["Recipes"].sum()).map("{:.1%}".format)
        st.dataframe(shown, hide_index=True, **STRETCH)
    if total["ok"] and total["payload"]["n_analyzed"] != ov["usable"]:
        st.warning(
            "The statistics tool and the source table disagree on the number of recipes.")
    if ov["excluded"]:
        with st.expander("Records excluded while cleaning"):
            st.dataframe(pd.DataFrame(ov["excluded"]).rename(columns={"reason": "Reason", "records": "Records"}),
                         hide_index=True, **STRETCH)
            st.caption(
                "These records are kept in the table `recipes_excluded` and are never searched.")
    if ing["ok"]:
        C.stats_caption(ing["payload"])


def _ingredients(engine: Engine) -> None:
    st.subheader("Most common ingredients")
    k = st.slider("How many", 5, engine.max_k, 10, key="an_top_k")
    top = _stat(engine, "top_ingredients", k=k)
    if top["ok"]:
        p = top["payload"]
        df = pd.DataFrame(p["value"]).rename(
            columns={"ingredient": "Ingredient", "n_recipes": "Recipes"})
        df["Share of recipes"] = (
            df["Recipes"] / p["n_analyzed"]).map("{:.1%}".format)
        a, b = st.columns([1.3, 1], gap="large")
        a.altair_chart(_bar(df, "Ingredient", "Recipes",
                       "Recipes containing it"), **STRETCH)
        b.dataframe(df, hide_index=True, **STRETCH)
        C.stats_caption(p)
    else:
        st.error(top["message"])
    st.caption("Counts are numbers of recipes, not ingredient lines. Different forms are listed separately "
               "(for example butter and unsalted butter).")

    st.divider()
    st.subheader("Ingredient explorer")
    st.caption(
        "Type an ingredient name to see how many recipes use it and what it is most often paired with.")
    with st.form("an_explore", border=False):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        name = c1.text_input(
            "Ingredient", placeholder="e.g. garlic", key="an_ing_name")
        c2.form_submit_button("Explore", **STRETCH)
    name = (name or "").strip().lower()
    if not name:
        return
    count = _stat(engine, "count", include=(name,))
    if not count["ok"]:
        st.warning(count["message"], icon=":material/help:")
        return
    p = count["payload"]
    m1, m2 = st.columns(2)
    m1.metric(f"Recipes containing {name}", f'{p["value"]:,}')
    m2.metric("Share of usable recipes",
              f'{100 * p["value"] / p["n_analyzed"]:.1f}%')
    C.stats_caption(p)
    co = _stat(engine, "top_ingredients", include=(name,), k=10)
    if co["ok"] and co["payload"]["value"]:
        df = pd.DataFrame(co["payload"]["value"]).rename(
            columns={"ingredient": "Ingredient", "n_recipes": "Recipes"})
        st.markdown(
            f"**Most common ingredients in recipes that contain {name}**")
        st.altair_chart(
            _bar(df, "Ingredient", "Recipes", "Recipes"), **STRETCH)
        C.stats_caption(co["payload"])


def _steps(engine: Engine) -> None:
    ov = cached.overview(engine, engine.fingerprint)
    s = ov["steps"]
    st.subheader("How many steps do recipes have?")
    if not s:
        st.info("No recipe has instructions.")
    else:
        c = st.columns(4)
        c[0].metric("Average steps", f'{s["mean"]:.2f}')
        c[1].metric("Median steps", f'{s["median"]:g}')
        c[2].metric("Fewest", s["min"])
        c[3].metric("Most", s["max"])
        hist = pd.DataFrame(ov["step_histogram"])
        cap = ov["hist_cap"]
        hist["label"] = hist["steps"].map(
            lambda n: f"{cap}+" if n == cap else str(n))
        chart = (alt.Chart(hist).mark_bar(color=GREEN, cornerRadiusEnd=3)
                 .encode(x=alt.X("label:N", sort=[h for h in hist["label"]], title="Steps"),
                         y=alt.Y("recipes:Q", title="Recipes"), tooltip=["label", "recipes"])
                 .properties(height=260))
        st.altair_chart(chart, **STRETCH)
        st.caption(f'Computed over {s["n"]:,} recipes with at least one step; {ov["n_zero_steps"]:,} recipes '
                   f'without instructions are not counted. {STEP_RULE.split(".")[0]}. '
                   "These figures come from a direct aggregate over the backend table `recipe_stats` "
                   "(the statistics tool itself has no step summary).")
        with st.expander("Average steps by source"):
            df = pd.DataFrame(ov["by_source"])[
                ["label", "mean_steps", "median_steps"]]
            df.columns = ["Source", "Average steps", "Median steps"]
            st.dataframe(df.round(2), hide_index=True, **STRETCH)

    st.divider()
    st.subheader("Recipes with the fewest steps")
    c1, c2 = st.columns(2)
    k = c1.slider("How many", 1, engine.max_k, 5, key="an_few_k")
    ing = c2.text_input("Must contain (optional)",
                        placeholder="e.g. tomato", key="an_few_ing").strip().lower()
    allergens = st.multiselect("Exclude allergens (applied by the backend like in search)", engine.allergens,
                               format_func=C.label, key="an_few_allergens")
    res = _stat(engine, "fewest_steps", include=(ing,)
                if ing else (), k=k, allergens=tuple(allergens))
    if not res["ok"]:
        st.warning(res["message"], icon=":material/help:")
        return
    p = res["payload"]
    if not p["value"]:
        st.info(
            "No recipe matches these filters (recipes with 0 steps are not ranked).")
    for row in p["value"]:
        with st.container(border=True):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            with c1:
                C.recipe_header(row["title"], row["id"],
                                f'{row["n_steps"]} steps')
            if c2.button("View", key=f'few_{row["id"]}', icon=":material/menu_book:"):
                from ui import navigation
                navigation.goto("recipe", recipe_id=row["id"])
    C.stats_caption(p)
    C.allergen_notice({"exclude_allergens": allergens})
