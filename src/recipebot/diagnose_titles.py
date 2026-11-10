"""Show which recipe titles the junk-title filter hides, so you can check it before relying on it.

    python -m recipebot.diagnose_titles            (project root, venv active, database built)
    python -m recipebot.diagnose_titles --show 200
"""

from __future__ import annotations

import argparse
import sys

from recipebot import config
from recipebot.db import connect
from recipebot.normalization.titles import is_junk_title


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List titles hidden by the junk-title filter.")
    parser.add_argument("--show", type=int, default=60,
                        help="how many flagged titles to print")
    args = parser.parse_args(argv)
    con = connect(read_only=True)
    rows = con.execute(
        "SELECT id, title FROM recipes ORDER BY row_idx").fetchall()
    flagged = [(rid, title) for rid, title in rows if is_junk_title(title)]
    print(f"Filter on: {config.JUNK_TITLE_FILTER} | rules: min letters {config.JUNK_TITLE_MIN_LETTERS}, "
          f"max consonant run {config.JUNK_TITLE_MAX_CONSONANT_RUN}, allowed {config.JUNK_TITLE_ALLOW}")
    print(f"{len(flagged):,} of {len(rows):,} recipes look like test records.\n")
    for rid, title in flagged[: args.show]:
        print(f"  [{rid}] {title!r}")
    if len(flagged) > args.show:
        print(f"  ... and {len(flagged) - args.show:,} more (use --show N)")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
