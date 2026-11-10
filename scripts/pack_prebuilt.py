"""Pack the built database and indexes into one zip, to upload as a GitHub Release asset.

    python scripts/pack_prebuilt.py        (project root, after the full build)

Creates dist/nosh_data.zip containing data/db/recipes.duckdb and everything in data/index/.
Upload it at: GitHub repository > Releases > Draft a new release, tag data-v1, attach the zip.
The raw dataset files are NOT included (anyone can re-download them with scripts/download_data.py).
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    files = [ROOT / "data" / "db" / "recipes.duckdb",
             *sorted(p for p in (ROOT / "data" / "index").glob("*") if p.is_file() and p.name != ".gitkeep")]
    missing = [f for f in files if not f.exists()]
    if missing or len(files) < 2:
        print("Build the data first (see README). Missing:",
              missing or "data/index/*")
        return 2
    out = ROOT / "dist" / "nosh_data.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for f in files:
            archive.write(f, f.relative_to(ROOT).as_posix())
            print("added", f.relative_to(ROOT))
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
