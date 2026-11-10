"""Shared backend objects for the Streamlit app.

What is shared between users (built once, read-only): the DuckDB connection, the BM25 and FAISS
indexes with the embedding model, the allergen flags, the matcher and the substitution miner.
What is NEVER shared: conversation state. Every browser session owns its own `RecipeAgent`
(and therefore its own `SessionState`); see `ui/session.py`.

DuckDB connections are not safe for concurrent use from several threads, and Streamlit runs each
session in its own thread. All access to the shared objects therefore goes through `Engine.lock`.
The lock is released while the chat waits for Gemini, so one slow API call never blocks others.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import streamlit as st

from recipebot import config
from recipebot.agent.agent import AgentReply, RecipeAgent, Understander
from recipebot.db import connect
from recipebot.normalization.allergens import load_allergens
from recipebot.retrieval.hybrid import HybridRetriever
from recipebot.schemas import Understanding
from recipebot.tools.matching import RecipeMatcher
from recipebot.tools.substitution import SubstitutionMiner
from recipebot.understanding.backend import get_backend
from recipebot.understanding.gemini_backend import ConfigError
from recipebot.understanding.restrictions import RestrictionMapper

logger = logging.getLogger(__name__)


@dataclass
class Engine:
    con: Any
    retriever: HybridRetriever
    mapper: RestrictionMapper
    matcher: RecipeMatcher
    miner: SubstitutionMiner
    allergens: tuple[str, ...]
    # changes when the database file changes; part of every cache key
    fingerprint: str
    lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def default_k(self) -> int:
        return config.DEFAULT_RESULT_K

    @property
    def max_k(self) -> int:
        return config.MAX_RESULT_K

    @contextmanager
    def locked(self) -> Iterator[None]:
        with self.lock:
            yield

    def new_agent(self, understander: Understander) -> RecipeAgent:
        """A fresh agent (fresh SessionState) that reuses the shared, expensive objects."""
        return RecipeAgent(self.retriever, understander, self.mapper,
                           matcher=self.matcher, miner=self.miner)

    def handle(self, agent: RecipeAgent, message: str) -> AgentReply:
        """Run one message through an agent while holding the engine lock."""
        adapter = agent.understander
        with self.lock:
            if isinstance(adapter, LLMAdapter):
                # lets the adapter release it during the API call
                adapter.held_lock = self.lock
            try:
                return agent.handle(message)
            finally:
                if isinstance(adapter, LLMAdapter):
                    adapter.held_lock = None


# ----------------------------------------------------------------------
# Understanders
# ----------------------------------------------------------------------
class FixedUnderstander:
    """Returns a prepared Understanding without calling any model.

    The form pages (ingredient finder, substitution, analytics) already know exactly what the
    user wants, so no language model is needed. The request still goes through the full agent
    pipeline: session merge, hard-constraint mask, independent verification and output guard.
    """

    def __init__(self, understanding: Understanding):
        self._understanding = understanding

    def understand(self, message: str, state: dict[str, Any] | None = None) -> Understanding:
        import copy
        return copy.deepcopy(self._understanding)


class LLMAdapter:
    """Chat understander: wraps the configured backend (Gemini) and remembers the last failure.

    Errors are re-raised unchanged, so the agent still answers with its own "could not understand"
    message and leaves the session untouched; the UI only reads `last_error` to explain it.
    """

    def __init__(self, backend: Any):
        self.backend = backend
        self.last_error: str | None = None
        self.held_lock: threading.RLock | None = None

    def understand(self, message: str, state: dict[str, Any] | None = None) -> Understanding:
        self.last_error = None
        lock = self.held_lock
        if lock is not None:
            lock.release()
        try:
            return self.backend.understand(message, state)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if lock is not None:
                lock.acquire()


# ----------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------
def _db_fingerprint() -> str:
    path = Path(config.DB_PATH)
    try:
        stat = path.stat()
        return f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        return str(path)


def _build_engine() -> Engine:
    """Open the database and load the indexes (slow: seconds to a minute on first start)."""
    con = connect(read_only=True)
    try:
        retriever = HybridRetriever.from_disk(con)
        # loads the embedding model once
        retriever.semantic.search("warm up", k=1)
        # allergen flags (one-time scan, then cached)
        retriever.flags
        mapper = RestrictionMapper.from_files(
            known_allergens=load_allergens().keys())
        # same construction as RecipeAgent builds lazily, but shared by every session
        matcher = RecipeMatcher(con, retriever.stats)
        miner = SubstitutionMiner(con, retriever.stats, staples=matcher.staples,
                                  allergen_matcher=retriever.matcher)
        return Engine(con=con, retriever=retriever, mapper=mapper, matcher=matcher, miner=miner,
                      allergens=tuple(load_allergens().keys()), fingerprint=_db_fingerprint())
    except BaseException:
        con.close()
        raise


@st.cache_resource(show_spinner="Loading recipe database, indexes and embedding model "
                                "(first start only, this can take a minute)...")
def get_engine() -> Engine:
    """One engine per server process. A failure is not cached, so a rerun retries."""
    return _build_engine()


def create_backend() -> tuple[Any | None, str | None]:
    """The language-model backend, or (None, reason) when it is not configured.

    Only the chat needs it; every other page works without an API key.
    """
    try:
        return get_backend(), None
    except (ConfigError, NotImplementedError, ValueError) as exc:
        return None, str(exc)
