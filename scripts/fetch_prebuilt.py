"""Download the prebuilt database and indexes (skips the ~50 minute build).

    python scripts/fetch_prebuilt.py
    python scripts/fetch_prebuilt.py --url https://example.com/nosh_data.zip

Extracts only data/db/* and data/index/* into the project. Anything else in the zip is refused.
The BM25 index is a Python pickle: only use a zip you trust (this repository's own release).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = ("https://github.com/anitkumarmaity1-hash/Recipe-AI-Chatbot/"
               "releases/download/data-v1/nosh_data.zip")
ALLOWED_PREFIXES = ("data/db/", "data/index/")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download the prebuilt NOSH data.")
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "nosh_data.zip"
        print(f"Downloading {args.url} ...")
        try:
            urllib.request.urlretrieve(args.url, target)
        except OSError as exc:
            print(
                f"Download failed: {exc}\nUse the full build instead (see README).")
            return 2
        with zipfile.ZipFile(target) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
            bad = [n for n in names if not n.startswith(
                ALLOWED_PREFIXES) or ".." in n]
            if bad:
                print("Refusing to extract unexpected paths:", bad)
                return 2
            archive.extractall(ROOT, members=names)
    print("Done. Start the chat with: python -m recipebot.cli")
    return 0


if __name__ == "__main__":
    sys.exit(main())
