"""Cached, USER-INDEPENDENT lookups. Safe to cache because the database is read-only and shared,
and the cache key contains everything the answer depends on (including the database fingerprint).
Nothing that depends on a visitor's conversation or restrictions is ever cached here."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import queries, services
from ui.engine import Engine


@st.cache_data(show_spinner=False, max_entries=256)
def stats(_engine: Engine, fingerprint: str, stat_type: str, include: tuple[str, ...] = (),
          k: int | None = None, max_steps: int | None = None,
          allergens: tuple[str, ...] = ()) -> dict[str, Any]:
    """One statistics answer through the agent pipeline. Returns plain data (cache-friendly)."""
    try:
        run = services.statistics(_engine, stat_type, include=include, k=k, max_steps=max_steps,
                                  allergens=allergens)
    except services.RequestError as exc:
        return {"ok": False, "message": str(exc), "payload": None, "text": ""}
    reply = run.reply
    ok = run.payload is not None and reply.tool == "stats"
    return {"ok": ok, "message": "" if ok else reply.text, "payload": run.payload if ok else None,
            "text": reply.text}


@st.cache_data(show_spinner=False)
def overview(_engine: Engine, fingerprint: str) -> dict[str, Any]:
    return queries.dataset_overview(_engine)
