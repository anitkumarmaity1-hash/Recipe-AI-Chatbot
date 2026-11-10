"""Sidebar status under the page navigation."""

from __future__ import annotations

import streamlit as st

from recipebot import config
from ui import cached
from ui.engine import Engine


def render(engine: Engine) -> None:
    with st.sidebar:
        st.markdown("### 🍽️ NOSH")
        st.caption("Your Intelligent Recipe Assistant")
        st.divider()
        try:
            usable = cached.overview(engine, engine.fingerprint)["usable"]
            st.caption(f":material/database: {usable:,} usable recipes")
        except Exception:                        # noqa: BLE001 - the status line is optional
            import logging
            logging.getLogger(__name__).exception("Sidebar status failed")
        llm = bool(config.GEMINI_API_KEY and config.GEMINI_MODEL)
        st.caption(f":material/{'check_circle' if llm else 'error'}: Gemini "
                   + ("configured" if llm else "not configured (chat disabled)"))
