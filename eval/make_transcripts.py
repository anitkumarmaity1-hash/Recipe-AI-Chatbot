"""Regenerate the demo conversations in docs/conversations/ with the real chatbot.

    python eval/make_transcripts.py            (project root, venv active, data built, .env filled)

Each script below is replayed from a fresh session; the old file is deleted first, so the
transcripts always match the current code. Read the output before committing it.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

CONVERSATIONS = {
    "01_pasta_dairy.md": [
        "Find me a penne pasta recipe.", "I cannot have dairy.", "Show me the first one.",
        "Actually dairy is fine now."],
    "02_statistics_and_refusal.md": [
        "How many recipes contain both garlic and onion? What percentage of the dataset is that?",
        "Among recipes containing tomato, which five have the fewest instruction steps?",
        "What is the average and median number of ingredients per recipe?",
        "What are the 10 most common ingredients in recipes that contain tomato?",
        "How long does banana bread take to cook?"],
    "03_ingredient_match.md": [
        "I have eggs, onions, tomatoes and rice. Suggest five recipes using as many of these as possible, "
        "with no peanuts and at most six instruction steps. Prefer recipes that need the fewest additional ingredients.",
        "Exclude eggs too.", "I also have garlic.", "Show me the first one."],
    "04_no_match.md": [
        "Find me a recipe that contains tomato, but I cannot have tomato.",
        "I have eggs and I cannot have eggs.", "Clear all my restrictions."],
    "05_substitution_cream.md": [
        "Take a penne pasta recipe and replace the cream without dairy.", "No nuts either."],
    "06_substitution_weak_evidence.md": [
        "Take a banana bread recipe and remove the eggs. Use only ingredients that appear in the dataset.",
        "I cannot have dairy."],
}


def main() -> int:
    from recipebot.cli import build_agent, save_turn
    from recipebot.db import connect

    out_dir = Path(__file__).resolve().parents[1] / "docs" / "conversations"
    con = connect(read_only=True)
    agent = build_agent(con)
    for name, messages in CONVERSATIONS.items():
        path = out_dir / name
        path.unlink(missing_ok=True)
        agent.reset()
        for turn, message in enumerate(messages, 1):
            reply = agent.handle(message)
            save_turn(path, turn, message, reply)
            print(f"{name} turn {turn}: {reply.intent}")
            time.sleep(4)
    con.close()
    print(f"Written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
