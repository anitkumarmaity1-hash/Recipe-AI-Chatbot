"""Page registry and jumping between pages (e.g. from a recipe card to the recipe view)."""

from __future__ import annotations

from typing import Any

import streamlit as st

PAGES: dict[str, Any] = {}


def register(pages: dict[str, Any]) -> None:
    PAGES.clear()
    PAGES.update(pages)


def goto(key: str, **session_values: Any) -> None:
    """Set some session values, then open the page registered under `key`."""
    for name, value in session_values.items():
        st.session_state[name] = value
    st.switch_page(PAGES[key])
