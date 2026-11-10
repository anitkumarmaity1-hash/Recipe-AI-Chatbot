"""Turn failures into clear messages. Nothing is swallowed: every error is logged, and the
technical detail stays available in an expander (no raw tracebacks on the page)."""

from __future__ import annotations

import logging
import os
import re
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

import streamlit as st

logger = logging.getLogger(__name__)

DEBUG = os.getenv("NOSH_UI_DEBUG", "").strip() == "1"


@dataclass(frozen=True)
class LLMProblem:
    kind: str          # rate_limit | server | network | auth | blocked | invalid | other
    title: str
    advice: str
    retryable: bool


def classify_llm_error(text: str | None) -> LLMProblem | None:
    """Read the backend's error text (it never contains the API key) and explain it."""
    if not text:
        return None
    t = text.lower()
    code = re.search(r"gemini api error (\d{3})", t)
    status = int(code.group(1)) if code else None
    if status == 429 or "rate limit" in t or "resource_exhausted" in t or "quota" in t:
        return LLMProblem("rate_limit", "Gemini is rate limiting requests (429)",
                          "The free tier allows only a few requests per minute. Wait about a minute "
                          "and try again. Your conversation and restrictions were not changed.", True)
    if status is not None and status >= 500:
        return LLMProblem("server", f"Gemini had a server problem ({status})",
                          "This is usually temporary. Try again in a moment. Nothing was changed.", True)
    if "could not reach gemini" in t:
        return LLMProblem("network", "Could not reach Gemini",
                          "Check your internet connection (and GEMINI_TIMEOUT_SECONDS in .env), "
                          "then try again. Nothing was changed.", True)
    if status in (400, 401, 403) or "api key" in t or "gemini_api_key" in t or "gemini_model" in t:
        return LLMProblem("auth", "Gemini rejected the request or is not configured",
                          "Check GEMINI_API_KEY and GEMINI_MODEL in your .env file, then restart "
                          "the app.", False)
    if "empty answer" in t or "blocked" in t:
        return LLMProblem("blocked", "Gemini returned no answer",
                          "The request may have been blocked. Try rephrasing your message.", True)
    if "invalid" in t or "stayed invalid" in t:
        return LLMProblem("invalid", "I could not read that message reliably",
                          "Try rephrasing it more simply. Nothing was changed.", False)
    return LLMProblem("other", "The language model step failed",
                      "Try again or rephrase your message. Nothing was changed.", True)


def show_llm_problem(problem: LLMProblem, technical: str | None = None) -> None:
    st.warning(f"**{problem.title}.** {problem.advice}",
               icon=":material/cloud_off:")
    if technical:
        with st.expander("Technical details"):
            st.code(technical, language="text")


def friendly_message(exc: BaseException) -> tuple[str, str]:
    """(title, advice) for an unexpected exception."""
    name = type(exc).__name__
    text = str(exc)
    if isinstance(exc, FileNotFoundError):
        return ("The recipe database or an index file is missing",
                "Build or download the data first (see the setup steps on this page).")
    if name in ("IOException", "CatalogException", "BinderException", "InvalidInputException",
                "ConversionException", "ParserException") or "duckdb" in type(exc).__module__:
        return ("The recipe database returned an error",
                "The database may be missing a table or be locked by another program. "
                "Close other programs that use it and rebuild it if the problem stays.")
    if isinstance(exc, RuntimeError) and ("index" in text.lower() or "rebuild" in text.lower()):
        return ("The search indexes do not match the database",
                "Rebuild them as the message below says.")
    if isinstance(exc, KeyError) and "Unknown allergen" in text:
        return ("Unknown allergen category", "Pick an allergen from the list provided.")
    return ("Something went wrong while processing your request",
            "Your session is unchanged. Try again; if it keeps failing, check the technical details.")


def show_exception(exc: BaseException, context: str = "") -> None:
    logger.exception("UI error%s", f" while {context}" if context else "")
    title, advice = friendly_message(exc)
    st.error(f"**{title}.** {advice}", icon=":material/error:")
    with st.expander("Technical details"):
        st.code(f"{type(exc).__name__}: {exc}", language="text")
        if DEBUG:
            st.code("".join(traceback.format_exception(exc)), language="text")


@contextmanager
def guarded(context: str) -> Iterator[None]:
    """Show a friendly error (and log it) instead of crashing the page.

    Use as `with guarded("searching"):`. Streamlit control-flow exceptions pass through.
    """
    try:
        yield
    except Exception as exc:                       # noqa: BLE001 - shown and logged, not swallowed
        if type(exc).__module__.startswith("streamlit"):
            raise
        show_exception(exc, context)
