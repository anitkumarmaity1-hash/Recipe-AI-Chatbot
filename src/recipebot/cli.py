"""Command-line chat (Step 9).

Run from the project root with the venv active (.env filled, indexes built):
    python -m recipebot.cli
    python -m recipebot.cli --debug --save docs/conversations/01_pasta_dairy.md

Commands inside the chat:  /help  /state  /reset  /debug  /quit
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from recipebot import config
from recipebot.agent.agent import AgentReply, RecipeAgent
from recipebot.db import connect
from recipebot.normalization.allergens import load_allergens
from recipebot.retrieval.hybrid import HybridRetriever
from recipebot.understanding.backend import get_backend
from recipebot.understanding.gemini_backend import ConfigError
from recipebot.understanding.restrictions import RestrictionMapper

HELP = ("Ask about recipes, e.g. 'Find me a penne pasta recipe', 'I cannot have dairy', "
        "'How many recipes contain both garlic and onion?', 'Show the second one'.\n"
        "Commands: /state (what I remember)  /reset (forget everything)  "
        "/debug (show the model's reading and timings)  /quit")


def build_agent(con) -> RecipeAgent:
    """Load indexes and the model backend. Warms up the slow parts so the first answer is fast."""
    retriever = HybridRetriever.from_disk(con)
    t0 = time.perf_counter()
    # loads the embedding model once
    retriever.semantic.search("warm up", k=1)
    # allergen flags (one-time scan, then cached)
    retriever.flags
    print(f"Ready (warm-up {time.perf_counter() - t0:.1f} s).")
    mapper = RestrictionMapper.from_files(
        known_allergens=load_allergens().keys())
    return RecipeAgent(retriever, get_backend(), mapper)


def state_text(agent: RecipeAgent) -> str:
    return json.dumps(agent.state.to_prompt_state() | {
        "unenforced": agent.state.unenforced, "last_query": agent.state.last_query,
        "exclude_allergens": agent.state.exclude_allergens,
        "exclude_ingredients": agent.state.exclude_ingredients},
        indent=2, ensure_ascii=False)


def debug_text(reply: AgentReply) -> str:
    timings = ", ".join(f"{k}={v:.0f} ms" for k, v in reply.timings_ms.items())
    return (f"[debug] intent={reply.intent} tool={reply.tool} {timings}\n"
            f"[debug] understanding={json.dumps(reply.understanding, ensure_ascii=False)}"
            + (f"\n[debug] GUARD: {reply.guard_problems}" if reply.guard_problems else ""))


def save_turn(path: Path | None, turn: int, message: str, reply: AgentReply) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"### Turn {turn}\n\n**User:** {message}\n\n"
                     f"Understanding: `{json.dumps(reply.understanding, ensure_ascii=False)}`\n\n"
                     f"**Chatbot:**\n\n```text\n{reply.text}\n```\n\n")


def main(argv: list[str] | None = None) -> int:
    config.setup_logging(logging.WARNING)
    logging.getLogger("recipebot").setLevel(
        logging.INFO)   # shows the one-time allergen scan
    parser = argparse.ArgumentParser(
        description="NOSH recipe chatbot (command line).")
    parser.add_argument("--debug", action="store_true",
                        help="show intent, slots and timings")
    parser.add_argument("--save", type=Path, default=None,
                        help="append the transcript to this Markdown file")
    args = parser.parse_args(argv)

    try:
        con = connect(read_only=True)
        agent = build_agent(con)
    except (FileNotFoundError, RuntimeError, ConfigError, ValueError, NotImplementedError) as exc:
        print(f"Cannot start: {exc}")
        return 2

    print(HELP)
    debug, turn = args.debug, 0
    try:
        while True:
            try:
                message = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not message:
                continue
            if message in ("/quit", "/exit"):
                break
            if message == "/help":
                print(HELP)
            elif message == "/state":
                print(state_text(agent))
            elif message == "/reset":
                agent.reset()
                print("Session cleared.")
            elif message == "/debug":
                debug = not debug
                print(f"debug {'on' if debug else 'off'}")
            else:
                turn += 1
                reply = agent.handle(message)
                print("\n" + reply.text)
                if debug:
                    print("\n" + debug_text(reply))
                save_turn(args.save, turn, message, reply)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
