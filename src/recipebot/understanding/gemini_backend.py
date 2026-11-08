"""Gemini backend for query understanding (Step 8).

One call per user message: structured JSON output, temperature 0, then strict
validation (schemas.Understanding.from_dict). Failure handling:
  * 429 / 5xx / network errors: retry with exponential backoff (config).
  * invalid JSON or invalid slots: ONE repair attempt that shows the model its
    own error, then UnderstandingError. We never guess.
  * other API errors (bad key, wrong model name...): fail at once with a clear
    message. The API key is scrubbed from every message.
The model never produces recipe facts; it only fills an Understanding.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from recipebot import config
from recipebot.schemas import Understanding, UnderstandingError, understanding_json_schema
from recipebot.understanding.prompt import build_payload, build_system_prompt

logger = logging.getLogger(__name__)

TRANSIENT_CODES = frozenset({429, 500, 502, 503, 504})
MAX_OUTPUT_TOKENS = 600


class ConfigError(RuntimeError):
    """Missing API key or model name."""


class GeminiBackend:
    name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        *,
        client: Any = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.api_key = api_key if api_key is not None else config.GEMINI_API_KEY
        self.model = model if model is not None else config.GEMINI_MODEL
        self.timeout_s = timeout_s if timeout_s is not None else config.GEMINI_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else config.GEMINI_MAX_RETRIES
        self._sleep = sleep
        self._client = client
        # model, attempts, latency_ms, raw (for evaluation logs)
        self.last_call: dict[str, Any] = {}

        if not self.model:
            raise ConfigError(
                "GEMINI_MODEL is empty. Set it in .env (see .env.example).")
        if client is None and not self.api_key:
            raise ConfigError(
                "GEMINI_API_KEY is empty. Set it in .env (never commit .env).")

    # ------------------------------------------------------------------
    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
                from google.genai import types
            except ImportError as exc:                       # pragma: no cover
                raise ConfigError(
                    "Install the SDK: pip install google-genai") from exc
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=int(self.timeout_s * 1000)),
            )
        return self._client

    def _scrub(self, text: str) -> str:
        """Remove the API key from any message that may be shown or logged."""
        return text.replace(self.api_key, "***") if self.api_key else text

    def _generate(self, contents: str) -> str:
        """One model call with retries on transient failures. Returns the raw text."""
        from google.genai import errors, types

        cfg = types.GenerateContentConfig(
            system_instruction=build_system_prompt(),
            temperature=0,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_json_schema=understanding_json_schema(),
        )
        client = self._get_client()
        for attempt in range(self.max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=self.model, contents=contents, config=cfg)
            except errors.APIError as exc:
                if exc.code in TRANSIENT_CODES and attempt < self.max_retries:
                    self._backoff(attempt, f"API error {exc.code}")
                    continue
                message = self._scrub(
                    f"{getattr(exc, 'message', '') or exc}")[:300]
                raise UnderstandingError(
                    f"Gemini API error {exc.code}: {message}") from None
            except Exception as exc:  # network / timeout errors differ between SDK versions
                if attempt < self.max_retries:
                    self._backoff(attempt, type(exc).__name__)
                    continue
                raise UnderstandingError(
                    f"Could not reach Gemini ({type(exc).__name__}). Check the network "
                    f"and GEMINI_TIMEOUT_SECONDS.") from None
            self.last_call["attempts"] = self.last_call.get(
                "attempts", 0) + attempt + 1
            text = response.text
            if not text:
                raise UnderstandingError(
                    "Gemini returned an empty answer (possibly blocked).")
            return text
        raise UnderstandingError(
            "Gemini call failed")      # pragma: no cover (loop always returns/raises)

    def _backoff(self, attempt: int, why: str) -> None:
        delay = 2.0 ** attempt
        logger.warning("Gemini %s; retrying in %.0f s", why, delay)
        self._sleep(delay)

    # ------------------------------------------------------------------
    def understand(self, message: str, state: dict[str, Any] | None = None) -> Understanding:
        """Message (+ session state) -> validated Understanding. Raises UnderstandingError."""
        if not message or not message.strip():
            raise UnderstandingError("Empty message.")
        start = time.perf_counter()
        self.last_call = {"model": self.model, "attempts": 0}
        payload = build_payload(message, state)
        contents = payload
        last_problem = ""
        # first try + one repair
        for repair in range(2):
            raw = self._generate(contents)
            self.last_call["raw"] = raw
            try:
                understanding = Understanding.from_dict(json.loads(raw))
            except (json.JSONDecodeError, UnderstandingError) as exc:
                last_problem = str(exc)
                logger.warning("Invalid model output (%s)", last_problem)
                contents = (f"{payload}\n\nYour previous output was invalid: {last_problem}\n"
                            f"Return the corrected JSON object only.")
                continue
            self._guard_target(understanding, state)
            self.last_call["latency_ms"] = 1000 * (time.perf_counter() - start)
            return understanding
        raise UnderstandingError(
            f"Model output stayed invalid after one repair: {last_problem}")

    @staticmethod
    def _guard_target(understanding: Understanding, state: dict[str, Any] | None) -> None:
        """A recipe id must come from the session state; otherwise drop it (never trust a made-up id)."""
        if not understanding.target_recipe_id:
            return
        known: set[str] = set()
        for item in (state or {}).get("last_results") or []:
            if isinstance(item, dict) and item.get("id"):
                known.add(str(item["id"]))
        active = (state or {}).get("active_recipe")
        if isinstance(active, dict) and active.get("id"):
            known.add(str(active["id"]))
        if understanding.target_recipe_id not in known:
            logger.warning("Dropping unknown target_recipe_id %r",
                           understanding.target_recipe_id)
            understanding.target_recipe_id = None
