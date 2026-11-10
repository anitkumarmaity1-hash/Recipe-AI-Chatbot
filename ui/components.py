"""Reusable UI pieces. Dynamic text (recipe titles, ingredient lines, what the user typed) is
always passed through `esc()` before it goes into HTML."""

from __future__ import annotations

import html
from typing import Any, Iterable, Sequence

import streamlit as st

from recipebot.agent.composer import ALLERGEN_DISCLAIMER, constraints_text, fmt_int
from recipebot.agent.substitution_composer import SAFETY_NOTE
from recipebot.tools.matching import QUANTITY_NOTE
from ui import navigation
from ui.styles import STRETCH
from ui.services import RecipeDetail

LEVEL_LABEL = {
    "direct": ("DIRECT dataset evidence", "ok"),
    "indirect": ("INDIRECT dataset evidence", "warn"),
    "none": ("NO dataset evidence", "muted"),
}
SOURCE_LABEL = {
    "data": "Dataset evidence",
    "both": "Dataset evidence + cooking knowledge",
    "knowledge": "General cooking knowledge (not dataset evidence)",
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def label(name: str) -> str:
    return str(name).replace("_", " ")


def chip(text: str, kind: str = "muted") -> str:
    return f'<span class="nosh-chip {kind}">{esc(label(text))}</span>'


def chips(values: Iterable[str], kind: str = "muted", empty: str = "none") -> str:
    items = [chip(v, kind) for v in values]
    return "".join(items) if items else f'<span class="nosh-note">{esc(empty)}</span>'


def html_block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def page_header(title: str, subtitle: str) -> None:
    html_block(
        f'<div class="nosh-pagehead"><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>')


def section_label(text: str) -> None:
    html_block(f'<div class="nosh-label">{esc(text)}</div>')


def allergen_notice(constraints: dict[str, Any] | None) -> None:
    """The allergen limitation, shown whenever an allergen restriction is active (same text as the backend)."""
    if constraints and constraints.get("exclude_allergens"):
        st.info(ALLERGEN_DISCLAIMER, icon=":material/info:")


def restriction_chips(constraints: dict[str, Any], unenforced: Sequence[str] = ()) -> None:
    """Show the hard filters that were applied to a result."""
    parts = [chip(f"no {label(a)} (allergen)", "bad")
             for a in constraints.get("exclude_allergens", [])]
    parts += [chip(f"no {x}", "bad") for x in constraints.get("exclude", [])]
    parts += [chip(f"must contain {x}", "info")
              for x in constraints.get("include", [])]
    if constraints.get("max_steps") is not None:
        parts.append(chip(f"max {constraints['max_steps']} steps", "info"))
    html_block('<div class="nosh-label">Hard filters applied</div>'
               + ("".join(parts) or '<span class="nosh-note">none</span>'))
    if unenforced:
        st.warning("Not enforced (ingredient lists cannot prove it): " + ", ".join(label(u) for u in unenforced),
                   icon=":material/rule:")


# ----------------------------------------------------------------------
# Recipe cards
# ----------------------------------------------------------------------
def recipe_header(title: str, recipe_id: str, meta: str = "") -> None:
    html_block(f'<div class="nosh-recipe-title">{esc(title)}</div>'
               f'<div class="nosh-meta"><span class="nosh-id">{esc(recipe_id)}</span>'
               f'{" &nbsp;·&nbsp; " + esc(meta) if meta else ""}</div>')


def open_buttons(recipe_id: str, key: str, substitution: bool = True) -> None:
    c1, c2, _ = st.columns([1, 1.3, 2])
    if c1.button("View recipe", key=f"open_{key}", icon=":material/menu_book:"):
        navigation.goto("recipe", recipe_id=recipe_id)
    if substitution and c2.button("Replace an ingredient", key=f"sub_{key}", icon=":material/swap_horiz:"):
        navigation.goto("substitution", sub_recipe_id=recipe_id)


def search_hits(hits: Sequence[dict[str, Any]], info: dict[str, dict[str, Any]], key: str) -> None:
    for pos, hit in enumerate(hits, 1):
        meta = info.get(hit["id"], {})
        bits = []
        if meta:
            bits += [meta["source"], f'{meta["n_steps"]} steps',
                     f'{meta["n_ingredients"]} ingredients']
        with st.container(border=True):
            recipe_header(f'{pos}. {hit["title"]}',
                          hit["id"], " · ".join(bits))
            rank = []
            rank.append(chip(f'BM25 #{hit["bm25_rank"]}' if hit.get(
                "bm25_rank") else "BM25 -", "muted"))
            rank.append(chip(f'embeddings #{hit["semantic_rank"]}' if hit.get(
                "semantic_rank") else "embeddings -", "muted"))
            html_block("".join(rank))
            open_buttons(hit["id"], f"{key}_{pos}")


def match_hits(hits: Sequence[dict[str, Any]], terms: Sequence[str], settings: dict[str, Any], key: str) -> None:
    for pos, h in enumerate(hits, 1):
        with st.container(border=True):
            top, score = st.columns([4, 1])
            with top:
                recipe_header(f'{pos}. {h["title"]}',
                              h["id"], f'{h["n_steps"]} steps')
            score.metric("Score", f'{h["score"]:.2f}')
            c1, c2 = st.columns(2)
            with c1:
                section_label(f'Matched ({h["n_matched"]} of {len(terms)})')
                html_block(chips(h["matched"], "ok"))
                section_label(
                    f'Missing: you have it, the recipe does not use it ({len(h["unused"])})')
                html_block(chips(h["unused"], "warn"))
            with c2:
                section_label(
                    f'Additional ingredients required ({h["n_extra"]})')
                html_block(chips(h["extra"], "bad"))
                section_label("Pantry staples assumed (not scored)")
                html_block(chips(h["staples"], "muted"))
            cap = min(h["n_steps"], settings["step_cap"])
            html_block(
                '<div class="nosh-formula">score = '
                f'{settings["w_coverage"]:g} × coverage {h["coverage"]:.2f} − '
                f'{settings["w_extra"]:g} × extra ratio {h["extra_ratio"]:.2f} − '
                f'{settings["w_steps"]:g} × steps {cap} = {h["score"]:.2f}</div>')
            open_buttons(h["id"], f"{key}_{pos}")


def match_explanation(settings: dict[str, Any]) -> None:
    with st.expander("How the score works"):
        st.markdown(
            f"**score = {settings['w_coverage']:g} × coverage − {settings['w_extra']:g} × extra ratio "
            f"− {settings['w_steps']:g} × steps** (steps counted up to {settings['step_cap']}).\n\n"
            "- **coverage** = matched ingredients ÷ ingredients you listed\n"
            "- **extra ratio** = additional ingredients needed ÷ ingredients the recipe needs "
            "(pantry staples are not counted)\n"
            "- Ties are broken by fewer steps, then by build order.\n\n"
            "The weights are design choices (`src/recipebot/config.py`), not measured values. "
            + QUANTITY_NOTE)


# ----------------------------------------------------------------------
# Recipe detail
# ----------------------------------------------------------------------
def recipe_detail(detail: RecipeDetail, restrictions_active: bool = False) -> None:
    html_block(f'<div class="nosh-recipe-title" style="font-size:1.6rem">{esc(detail.title)}</div>'
               f'<div class="nosh-meta"><span class="nosh-id">{esc(detail.id)}</span> &nbsp;·&nbsp; '
               f'Source: {esc(detail.source_label)} &nbsp;·&nbsp; {detail.n_steps} steps &nbsp;·&nbsp; '
               f'{len(detail.lines)} ingredient lines</div>')
    for warning in detail.warnings:
        st.warning(
            f"This recipe conflicts with your restrictions: {warning}", icon=":material/warning:")
    if restrictions_active and not detail.warnings:
        st.success("No conflict with your active restrictions was found in the ingredient text. "
                   "This is a text check only, not a safety guarantee.", icon=":material/check_circle:")
    left, right = st.columns([1, 1.5], gap="large")
    with left:
        st.subheader("Ingredients")
        html_block("".join(f'<div class="nosh-line">{esc(x)}</div>' for x in detail.lines)
                   or '<span class="nosh-note">No ingredient lines.</span>')
    with right:
        st.subheader("Instructions")
        if detail.steps:
            html_block("".join(
                f'<div class="nosh-step"><div class="n">{i}</div><div class="t">{esc(s)}</div></div>'
                for i, s in enumerate(detail.steps, 1)))
        else:
            st.info("This recipe has no instructions in the dataset.")
    st.caption("Cleaned text: ADVERTISEMENT markers and section-header lines are removed, and one sentence "
               "is counted as one step. The dataset has no cooking times, nutrition values or images, so none are shown.")


# ----------------------------------------------------------------------
# Substitution
# ----------------------------------------------------------------------
def level_chip(level: str) -> str:
    text, kind = LEVEL_LABEL.get(level, (level, "muted"))
    return f'<span class="nosh-chip {kind}">{esc(text)}</span>'


def substitution_result(payload: dict[str, Any], text: str, unenforced: Sequence[str], key: str) -> None:
    ev, adapted = payload["evidence"], payload.get("adapted")
    orig, target, pools, role = ev["original"], ev["target"], ev["pools"], ev["role"]
    cons = ev["constraints"]
    cands = ev["candidates"]

    recipe_header(f'{orig["title"]}', orig["id"],
                  f'replace "{label(target["base"])}"')
    section_label("Lines in the original that contain it")
    html_block("".join(f'<div class="nosh-line">line {x["position"] + 1}: {esc(x["line"])}</div>'
                       for x in target["lines"]))
    restriction_chips(cons, unenforced)
    allergen_notice(cons)

    weak = [c for c in cands if c["level"] != "none"]
    if adapted:
        st.success("A substitute with enough dataset evidence was found, so an adapted copy was built "
                   "(shown below). It is a plain word swap and still needs your judgement.",
                   icon=":material/check_circle:")
    elif ev["status"] == "ok" and weak:
        st.warning("WEAK EVIDENCE. The dataset supports "
                   + ", ".join(c["name"] for c in weak)
                   + " only weakly, so no adapted recipe was built. The cited recipes are listed so you can "
                     "judge them yourself.", icon=":material/warning:")
    else:
        st.info("INSUFFICIENT EVIDENCE. " + (ev.get("note") or "No substitute has dataset evidence, "
                                             "so no adapted recipe was built."), icon=":material/info:")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Related recipes with it", fmt_int(pools["n_related_with"]))
    m2.metric("Related recipes without it",
              fmt_int(pools["n_related_without"]))
    m3.metric("…that obey your filters", fmt_int(pools["n_without_allowed"]))
    m4.metric("Same dish family", fmt_int(pools["n_direct"]))
    st.caption("Similarity = overlap of ingredient names between recipes (not method or amounts). "
               "Only recipes that obey your hard filters can be cited as evidence.")

    st.subheader("Suggested substitutes")
    if not cands:
        st.write("No candidates were found.")
    for n, c in enumerate(cands, 1):
        with st.container(border=True):
            html_block(f'<div class="nosh-recipe-title">{n}. {esc(label(c["name"]))}</div>'
                       + level_chip(c["level"]) + chip(SOURCE_LABEL.get(c["source"], c["source"]), "info")
                       + ("" if c["in_vocabulary"] else chip("not an ingredient in the dataset", "bad")))
            a, b, d = st.columns(3)
            a.metric("Supporting recipes", c["n_support"])
            b.metric("…same dish family", c["n_direct"])
            if c["rate_without"] is not None:
                rate_with = "n/a" if c["rate_with"] is None else f'{c["rate_with"]:.0%}'
                d.metric("Used without / with it",
                         f'{c["rate_without"]:.0%} / {rate_with}')
            if c["level"] == "none":
                st.caption(("Too few recipes in the dataset use it here to count as evidence. " if c["n_support"]
                            else "No recipe in the dataset backs this up. ")
                           + "It is listed from general cooking knowledge (data/taxonomy/ingredient_roles.yaml) "
                             "and is unverified.")
            if c["shared_roles"]:
                section_label(
                    "Cooking roles shared with the original (cooking knowledge)")
                html_block(chips(c["shared_roles"], "info"))
            if c["evidence"]:
                with st.expander(f'Supporting recipe ids ({len(c["evidence"])})'):
                    for e in c["evidence"]:
                        html_block(f'<span class="nosh-id">{esc(e["id"])}</span> <b>{esc(e["title"])}</b> '
                                   f'{chip(e["tier"], "ok" if e["tier"] == "direct" else "warn")}'
                                   f'<span class="nosh-note"> similarity {e["similarity"]:.2f} · {e["n_steps"]} steps</span>'
                                   + "".join(f'<div class="nosh-line">{esc(x)}</div>' for x in e["lines"]))

    with st.expander("What the dataset says vs. general cooking knowledge", expanded=False):
        st.markdown(f'**Role of {label(target["base"])}** (cooking knowledge, not dataset evidence): '
                    + (", ".join(role["roles"]) if role["known"] else "not in the roles file"))
        if role.get("removal_effect"):
            st.markdown(
                f'**If it is removed** (cooking knowledge): {role["removal_effect"]}')
        st.caption(role.get("source", ""))

    if ev["rejected"]:
        st.subheader("Rejected alternatives")
        st.dataframe([{"Alternative": label(r["name"]), "Reason": r["reason"]} for r in ev["rejected"]],
                     hide_index=True, **STRETCH)

    for r in ev["residual_conflicts"]:
        st.error(f'STILL CONFLICTS with your restrictions: line {r["position"] + 1} "{r["line"]}" '
                 f'({r["constraint"]}). Only {label(target["base"])} was replaced, so this recipe does NOT '
                 "yet satisfy them.", icon=":material/dangerous:")

    if adapted:
        st.subheader("Adapted recipe")
        st.caption(f'A separate copy of "{adapted["original_title"]}" with {label(adapted["ingredient"])} → '
                   f'{label(adapted["substitute"])} ({adapted["level"]} evidence). The original is unchanged.')
        t_ing, t_steps, t_changes = st.tabs(
            ["Ingredients", "Instructions", "Changes made"])
        changed = {c["position"]: c for c in adapted["changed_lines"]}
        with t_ing:
            rows = []
            for i, line in enumerate(adapted["ingredient_lines"]):
                extra = ""
                if i in changed and changed[i].get("reference_id"):
                    extra = (f'<div class="nosh-note">for scale: [{esc(changed[i]["reference_id"])}] uses '
                             f'"{esc(changed[i]["reference_line"])}" (another recipe\'s amount, not verified for this one)</div>')
                rows.append(f'<div class="nosh-line{" changed" if i in changed else ""}">{esc(line)}'
                            + (" " + chip("changed", "warn") if i in changed else "") + extra + "</div>")
            html_block("".join(rows))
        with t_steps:
            revised = {c["position"] for c in adapted["step_changes"]}
            if adapted["steps"]:
                html_block("".join(
                    f'<div class="nosh-step{" changed" if i in revised else ""}"><div class="n">{i + 1}</div>'
                    f'<div class="t">{esc(s)}</div></div>' for i, s in enumerate(adapted["steps"])))
            else:
                st.info("The original recipe has no instructions.")
        with t_changes:
            for c in adapted["changed_lines"]:
                st.markdown(
                    f'- ingredient line {c["position"] + 1}: "{c["original"]}" → "{c["adapted"]}"')
            for c in adapted["step_changes"]:
                st.markdown(
                    f'- step {c["position"] + 1} (word swap), was: "{c["original"]}"')
            if not adapted["step_changes"]:
                st.markdown(
                    "- no instruction step names the ingredient, so the steps are unchanged.")
        for w in adapted["warnings"]:
            st.warning(w)
        uncertainty(text)

    st.info(SAFETY_NOTE, icon=":material/health_and_safety:")
    with st.expander("Full grounded answer (audit text)"):
        st.code(text, language="text")


def uncertainty(text: str) -> None:
    """The four-label uncertainty block, exactly as the backend composed it."""
    lines = text.splitlines()
    if "Uncertainty:" not in lines:
        return
    start = lines.index("Uncertainty:") + 1
    block = []
    for line in lines[start:start + 4]:
        if not line.startswith("  "):
            break
        block.append(line.strip())
    if not block:
        return
    st.subheader("How sure are we?")
    for line in block:
        head, _, body = line.partition(": ")
        st.markdown(f"**{head}**  \n{body}")


# ----------------------------------------------------------------------
# Statistics
# ----------------------------------------------------------------------
def stats_caption(payload: dict[str, Any]) -> None:
    from recipebot.agent.composer import filters_text
    st.caption(
        f'Recipes analyzed: {fmt_int(payload["n_analyzed"])} · Filters: {filters_text(payload["filters"])}')
    with st.expander("How this was computed"):
        st.markdown('**Definition of "contains":** ' +
                    payload["definition_of_contains"])
        st.code(payload["sql"], language="sql")
