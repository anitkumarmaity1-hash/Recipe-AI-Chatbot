"""Backend interface, factory and a command-line smoke test (Step 8).

UNDERSTANDING_BACKEND (in .env) chooses the implementation:
  gemini : Gemini API (this step)
  lora   : fine-tuned local model (optional, Step 13; not built yet)

Smoke test with the real model (project root, venv active, .env filled):
    python -m recipebot.understanding.backend "I cannot have dairy"
    python -m recipebot.understanding.backend "Replace the butter in the second one" --state-file state.json
(state.json holds the session state as JSON; a file avoids shell quoting problems)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Protocol

from recipebot import config
from recipebot.normalization.allergens import load_allergens
from recipebot.schemas import Understanding, UnderstandingError
from recipebot.understanding.gemini_backend import ConfigError, GeminiBackend
from recipebot.understanding.restrictions import RestrictionMapper, to_constraints


class UnderstandingBackend(Protocol):
    name: str

    def understand(self, message: str, state: dict[str, Any] | None = None) -> Understanding:
        ...


def get_backend(name: str | None = None, **kwargs: Any) -> UnderstandingBackend:
    """Create the backend selected by `name` (default: config.UNDERSTANDING_BACKEND)."""
    name = (name or config.UNDERSTANDING_BACKEND).strip().lower()
    if name == "gemini":
        return GeminiBackend(**kwargs)
    if name == "lora":
        raise NotImplementedError(
            "The LoRA backend is optional and is built in Step 13. "
            "Set UNDERSTANDING_BACKEND=gemini in .env.")
    raise ValueError(
        f"Unknown understanding backend {name!r}; use one of {config.VALID_BACKENDS}")


def main(argv: list[str] | None = None) -> int:
    config.setup_logging(logging.WARNING)
    parser = argparse.ArgumentParser(
        description="Understand one message with the configured backend.")
    parser.add_argument("message")
    parser.add_argument("--state-file", default=None,
                        help="JSON file with the session state")
    args = parser.parse_args(argv)

    try:
        state = {}
        if args.state_file:
            with open(args.state_file, encoding="utf-8-sig") as handle:  # tolerates a BOM
                state = json.load(handle)
        backend = get_backend()
        understanding = backend.understand(args.message, state)
        mapper = RestrictionMapper.from_files(
            known_allergens=load_allergens().keys())
        constraints, unsupported = to_constraints(understanding, mapper)
    except (json.JSONDecodeError, ConfigError, UnderstandingError,
            NotImplementedError, ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}")
        return 2

    print("backend       :", backend.name, "|", getattr(backend, "model", ""))
    print("understanding :", json.dumps(
        understanding.to_dict(), ensure_ascii=False))
    print("constraints   :", constraints.describe())
    print("unsupported   :", unsupported or "-")
    call = getattr(backend, "last_call", {})
    print(
        f"latency       : {call.get('latency_ms', 0):.0f} ms, attempts={call.get('attempts')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
