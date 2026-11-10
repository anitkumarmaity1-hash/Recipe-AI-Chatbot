"""Per-browser-session state. Everything here lives in `st.session_state`, which Streamlit keeps
separately for every visitor, so conversations and restrictions of different users never mix."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import streamlit as st

from recipebot.agent.agent import AgentReply, RecipeAgent
from ui.engine import Engine, LLMAdapter, create_backend

CHAT_KEY = "nosh_chat"


@dataclass
class ChatTurn:
    role: str                              # "user" | "assistant"
    text: str
    reply: AgentReply | None = None
    # backend error text when the model step failed
    llm_error: str | None = None


@dataclass
class ChatSession:
    agent: RecipeAgent | None
    adapter: LLMAdapter | None
    config_error: str | None
    turns: list[ChatTurn] = field(default_factory=list)


def get_chat(engine: Engine) -> ChatSession:
    """This visitor's conversation (created on first use). The agent holds the backend SessionState."""
    session = st.session_state.get(CHAT_KEY)
    if session is None:
        backend, error = create_backend()
        adapter = LLMAdapter(backend) if backend is not None else None
        agent = engine.new_agent(adapter) if adapter is not None else None
        session = ChatSession(agent=agent, adapter=adapter, config_error=error)
        st.session_state[CHAT_KEY] = session
    return session


def chat_restrictions() -> dict[str, Any]:
    """The restrictions currently active in this visitor's chat (empty when there is no chat yet)."""
    session = st.session_state.get(CHAT_KEY)
    if session is None or session.agent is None:
        return {"allergens": [], "exclude": [], "unenforced": [], "include": [], "max_steps": None}
    s = session.agent.state
    return {"allergens": list(s.exclude_allergens), "exclude": list(s.exclude_ingredients),
            "unenforced": list(s.unenforced), "include": list(s.include), "max_steps": s.max_steps}
