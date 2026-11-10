"""AI Recipe Chat: the backend agent with Gemini understanding, session memory and follow-ups."""

from __future__ import annotations

import json
import time

import streamlit as st

from recipebot.agent.agent import AgentReply
from recipebot.agent.composer import filters_text
from ui import components as C
from ui import navigation, queries, services
from ui.engine import Engine
from ui.styles import STRETCH
from ui.errors import classify_llm_error, friendly_message, guarded, show_exception, show_llm_problem
from ui.session import ChatSession, ChatTurn, get_chat

EXAMPLES = [
    "Find me five pasta recipes.",
    "Find banana bread recipes without eggs.",
    "I have eggs, onions, tomatoes and rice. Suggest five recipes, no peanuts.",
    "Among recipes containing tomato, which five have the fewest steps?",
    "Take a banana bread recipe and replace the eggs.",
]
FOLLOW_UPS = ["Exclude dairy too.", "Show me the second recipe.",
              "Remove the dairy restriction."]
PREAMBLE_ANCHORS = {
    "search": ('Search: "',),
    "match": ("Ingredient match for:", "Not recognized, ignored", "Not counted:", "Hard filters applied:"),
    "substitute": ("Substitution: replace",),
}


def _preamble(reply: AgentReply) -> list[str]:
    """Lines the backend printed BEFORE the structured answer (restriction changes, notes)."""
    anchors = PREAMBLE_ANCHORS.get(reply.tool or "")
    if not anchors:
        return []
    lines = []
    for line in reply.text.splitlines():
        if line.startswith(anchors):
            break
        lines.append(line)
    else:
        return []
    return [x for x in lines if x.strip()]


def _render_reply(engine: Engine, turn: ChatTurn, session: ChatSession, index: int) -> None:
    reply = turn.reply
    problem = classify_llm_error(turn.llm_error)
    if problem:
        show_llm_problem(problem, turn.llm_error)
        if problem.retryable and index == len(session.turns) - 1:
            if st.button("Try again", key=f"retry_{index}", icon=":material/refresh:"):
                st.session_state["chat_retry"] = True
                st.rerun()
        return
    if reply is None or services.is_withheld(reply):
        st.error(turn.text, icon=":material/gpp_maybe:")
        return

    for line in _preamble(reply):
        st.caption(line)

    payload, tool = reply.payload, reply.tool
    if tool == "search" and payload and payload["hits"]:
        info = queries.summaries(engine, [h["id"] for h in payload["hits"]])
        C.restriction_chips(
            payload["constraints"], session.agent.state.unenforced if session.agent else ())
        st.caption(
            f'{payload["n_allowed"]:,} of {payload["n_total"]:,} recipes pass these filters; nothing was relaxed.')
        C.search_hits(payload["hits"], info, f"chat{index}")
        C.allergen_notice(payload["constraints"])
    elif tool == "match" and payload and payload["hits"]:
        C.restriction_chips(
            payload["constraints"], session.agent.state.unenforced if session.agent else ())
        st.caption(f'{payload["n_candidates"]:,} of {payload["n_total"]:,} recipes use at least one of your '
                   f'ingredients; {payload["n_eligible"]:,} pass the hard filters.')
        C.match_hits(payload["hits"], payload["terms"],
                     payload["settings"], f"chat{index}")
        C.match_explanation(payload["settings"])
        C.allergen_notice(payload["constraints"])
    elif tool == "stats" and payload:
        _render_stats(payload)
    elif tool == "details" and payload:
        detail = services.recipe_detail(
            engine, payload["id"], **_restrictions(session))
        if isinstance(detail, str):
            st.write(detail)
        else:
            C.recipe_detail(detail, restrictions_active=bool(_restrictions(session)["allergens"]
                                                             or _restrictions(session)["exclude_ingredients"]))
    elif tool == "substitute" and payload:
        C.substitution_result(payload, reply.text, session.agent.state.unenforced if session.agent else (),
                              f"chat{index}")
    else:
        # clarifying questions, refusals, saved restrictions, "no results": the backend's own words
        if "\n" in reply.text:
            st.code(reply.text, language="text", wrap_lines=True)
        else:
            st.write(reply.text)
        return

    with st.expander("Full grounded answer (filters, evidence, disclaimers)"):
        st.code(reply.text, language="text")
    _understanding_expander(reply)


def _restrictions(session: ChatSession) -> dict:
    s = session.agent.state if session.agent else None
    return {"allergens": list(s.exclude_allergens) if s else [],
            "exclude_ingredients": list(s.exclude_ingredients) if s else []}


def _render_stats(payload: dict) -> None:
    name, value = payload["name"], payload["value"]
    if name == "count":
        c1, c2 = st.columns(2)
        c1.metric("Recipes", f"{value:,}")
        c2.metric("Share of usable recipes",
                  f'{100 * value / payload["n_analyzed"]:.1f}%' if payload["n_analyzed"] else "n/a")
    elif name == "percentage":
        st.metric("Percentage",
                  "undefined" if value is None else f"{value:.1f}%")
    elif name == "ingredient_count_stats":
        if value:
            cols = st.columns(4)
            for col, key in zip(cols, ("mean", "median", "min", "max")):
                col.metric(f"{key.capitalize()} ingredients",
                           f"{value[key]:.2f}" if key == "mean" else f"{value[key]:g}")
        else:
            st.write("No recipe matches the filter.")
    elif name == "top_common_ingredients":
        st.dataframe([{"Ingredient": r["ingredient"], "Recipes": r["n_recipes"]} for r in value],
                     hide_index=True, **STRETCH)
    elif name == "fewest_steps":
        if value:
            for r in value:
                C.recipe_header(r["title"], r["id"], f'{r["n_steps"]} steps')
        else:
            st.write("No recipe matches these filters.")
    st.caption(
        f'Recipes analyzed: {payload["n_analyzed"]:,} · Filters: {filters_text(payload["filters"])}')


def _understanding_expander(reply: AgentReply) -> None:
    with st.expander("How I understood this"):
        st.caption(f"intent: {reply.intent} · tool: {reply.tool} · "
                   + ", ".join(f"{k}: {v:.0f} ms" for k, v in reply.timings_ms.items()))
        st.code(json.dumps(reply.understanding, indent=2,
                ensure_ascii=False), language="json")


def _sidebar_memory(session: ChatSession) -> None:
    """What the assistant currently remembers (the backend SessionState, shown read-only)."""
    s = session.agent.state
    with st.container(border=True):
        st.markdown("**Chat memory**")
        if not (s.has_restrictions() or s.unenforced or s.available or s.last_query):
            st.caption("Nothing yet. Say things like “I can't have dairy”.")
        parts = [C.chip(f"no {C.label(a)}", "bad")
                 for a in s.exclude_allergens]
        parts += [C.chip(f"no {x}", "bad") for x in s.exclude_ingredients]
        parts += [C.chip(f"must have {x}", "info") for x in s.include]
        if s.max_steps is not None:
            parts.append(C.chip(f"≤ {s.max_steps} steps", "info"))
        parts += [C.chip(f"{x} (not enforced)", "warn") for x in s.unenforced]
        if parts:
            C.html_block("".join(parts))
        if s.available:
            st.caption("Ingredients you have: " + ", ".join(s.available))
        if s.last_query:
            st.caption(f"Last search: {s.last_query} · mode: {s.mode}")
        c1, c2 = st.columns(2)
        if c1.button("Clear filters", key="mem_clear", help="Forget all restrictions, keep the conversation",
                     disabled=not (s.has_restrictions() or s.unenforced)):
            s.clear_filters()
            st.rerun()
        if c2.button("New chat", key="mem_reset", help="Forget everything"):
            session.agent.reset()
            session.turns.clear()
            st.rerun()


def render(engine: Engine) -> None:
    C.page_header("AI Recipe Chat",
                  "Search in plain language, refine with follow-ups, and set restrictions as you go.")
    session = get_chat(engine)
    if session.agent is None:
        st.warning("The chat needs a Gemini API key, which is not configured. Add `GEMINI_API_KEY` and "
                   "`GEMINI_MODEL` to your `.env` file and restart the app. "
                   "All other pages work without it.", icon=":material/key:")
        if session.config_error:
            with st.expander("Details"):
                st.code(session.config_error, language="text")
        return

    with st.sidebar:
        _sidebar_memory(session)

    message = st.chat_input(
        "Ask about recipes, ingredients, restrictions or substitutions…")
    if st.session_state.pop("chat_retry", False) and len(session.turns) >= 2:
        # re-send the message whose model step failed
        message = session.turns[-2].text
        del session.turns[-2:]
    message = message or st.session_state.pop("chat_pending", None)

    if not session.turns and not message:
        st.markdown("**Try one of these**")
        cols = st.columns(2)
        for i, example in enumerate(EXAMPLES):
            if cols[i % 2].button(example, key=f"ex_{i}", **STRETCH):
                st.session_state["chat_pending"] = example
                st.rerun()
    for i, turn in enumerate(session.turns):
        with st.chat_message(turn.role, avatar=":material/person:" if turn.role == "user" else ":material/restaurant:"):
            if turn.role == "user":
                st.markdown(turn.text)
            else:
                with guarded("showing the answer"):
                    _render_reply(engine, turn, session, i)
    if session.turns and not message:
        st.caption("Follow-ups to try: " +
                   " · ".join(f"“{x}”" for x in FOLLOW_UPS))
    if message:
        _handle(engine, session, message)


def _handle(engine: Engine, session: ChatSession, message: str) -> None:
    session.turns.append(ChatTurn("user", message))
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(message)
    with st.chat_message("assistant", avatar=":material/restaurant:"):
        try:
            with st.spinner("Thinking…"):
                started = time.perf_counter()
                reply = engine.handle(session.agent, message)
                elapsed = time.perf_counter() - started
        except Exception as exc:                                    # noqa: BLE001 - shown and logged
            show_exception(exc, "answering a chat message")
            title, advice = friendly_message(exc)
            session.turns.append(
                ChatTurn("assistant", f"{title}. {advice}", None, None))
            return
        turn = ChatTurn("assistant", reply.text, reply,
                        session.adapter.last_error if session.adapter else None)
        session.turns.append(turn)
    st.rerun()
