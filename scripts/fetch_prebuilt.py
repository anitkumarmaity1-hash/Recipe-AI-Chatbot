"""Download the prebuilt database and indexes (skips the ~50 minute build).

    python scripts/fetch_prebuilt.py
    python scripts/fetch_prebuilt.py --url https://example.com/nosh_data.zip

Extracts only data/db/* and data/index/* into the project. Anything else in the zip is refused.
The BM25 index is a Python pickle: only use a zip you trust (this repository's own release).
"""

from __future__ import annotations

import argparse
import urllib.error
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
            request = urllib.request.Request(
                args.url, headers={"User-Agent": "nosh-recipe-chatbot/0.1"})
            with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and args.url == DEFAULT_URL:
                print(
                    "The prebuilt release asset is not published yet.\n"
                    "In GitHub, open Actions > Publish prebuilt recipe data > Run workflow.\n"
                    "Keep the release tag as 'data-v1'. The workflow builds and uploads the exact\n"
                    "asset this command expects. After it succeeds, run this command again.\n"
                    "Alternatively, follow the full local build in README.md.")
            else:
                print(f"Download failed (HTTP {exc.code}): {exc.reason}")
            return 2
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
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
