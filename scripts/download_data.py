"""Download the Recipe Box dataset and extract the three JSON files into data/raw/.

Usage (from the project root, venv active):

    python scripts/download_data.py                # download + extract
    python scripts/download_data.py --zip PATH     # use a zip you downloaded manually
    python scripts/download_data.py --force        # re-extract even if files exist

Only the standard library is used, so this works before any other install.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from recipebot import config
from recipebot.data_loading import SOURCES

logger = logging.getLogger("download_data")

# URL given on the dataset page (see handover section 6.1) is tried first.
# The second URL is UNVERIFIED (recalled from the recipe-box project README);
# it is only a fallback and the manual route below always works.
DATASET_URLS: tuple[str, ...] = (
    "https://eightportions.com/recipes_raw.zip",
    "https://storage.googleapis.com/recipe-box/recipes_raw.zip",
)
ZIP_NAME = "recipes_raw.zip"
CHUNK_SIZE = 1024 * 1024  # 1 MiB
TIMEOUT_SECONDS = 60

MANUAL_HELP = (
    "Automatic download failed. Manual route:\n"
    "  1. Open https://eightportions.com/datasets/Recipes/ in your browser.\n"
    "  2. Download the zip of raw recipes.\n"
    f"  3. Save it as data/raw/{ZIP_NAME}  (or anywhere) and run:\n"
    f"     python scripts/download_data.py --zip data/raw/{ZIP_NAME}"
)


def sha256_of(path: Path) -> str:
    """Return the SHA-256 hex digest of a file (for reproducibility notes)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_zip(urls: tuple[str, ...], destination: Path) -> bool:
    """Try each URL in turn; save the first success to ``destination``.

    The file is written to ``<destination>.part`` first and renamed only after
    the full download, so a cut-off transfer never leaves a corrupt zip behind.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    for url in urls:
        logger.info("Downloading %s", url)
        request = urllib.request.Request(
            url, headers={"User-Agent": "nosh-recipe-chatbot/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response, partial.open("wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                next_report = 10
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if total and done * 100 // total >= next_report:
                        logger.info("  %d%% (%.1f MB)", done *
                                    100 // total, done / 1e6)
                        next_report += 10
            partial.replace(destination)
            logger.info("Saved %s (%.1f MB)", destination,
                        destination.stat().st_size / 1e6)
            return True
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("Failed for %s: %s", url, exc)
            partial.unlink(missing_ok=True)
    return False


def extract_expected_files(zip_path: Path, raw_dir: Path) -> list[Path]:
    """Extract only the three expected JSON files into ``raw_dir``.

    Members are matched by base name and written to ``raw_dir / <expected name>``
    explicitly, so a malicious zip entry such as ``../x`` can never write
    outside ``raw_dir`` (zip-slip protection).

    Raises:
        FileNotFoundError: if the zip does not exist.
        ValueError: if one of the three expected files is not in the zip.
    """
    if not zip_path.is_file():
        raise FileNotFoundError(f"Zip not found: {zip_path}")
    raw_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        by_basename = {Path(
            info.filename).name: info for info in archive.infolist() if not info.is_dir()}
        missing = [name for name in SOURCES.values()
                   if name not in by_basename]
        if missing:
            raise ValueError(
                f"Zip is missing expected files: {missing}. Found: {sorted(by_basename)}")
        for expected_name in SOURCES.values():
            target = raw_dir / expected_name
            with archive.open(by_basename[expected_name]) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            written.append(target)
            logger.info("Extracted %s (%.1f MB)", target.name,
                        target.stat().st_size / 1e6)
    return written


def all_files_present(raw_dir: Path) -> bool:
    """True if all three expected JSON files already exist and are non-empty."""
    return all((raw_dir / name).is_file() and (raw_dir / name).stat().st_size > 0 for name in SOURCES.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download and extract the Recipe Box dataset.")
    parser.add_argument("--zip", type=Path,
                        help="Path to an already downloaded recipes_raw.zip")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract even if the JSON files exist")
    parser.add_argument("--raw-dir", type=Path, default=config.RAW_DIR,
                        help="Output folder (default: data/raw)")
    args = parser.parse_args(argv)

    config.setup_logging()
    raw_dir: Path = args.raw_dir

    if all_files_present(raw_dir) and not args.force:
        logger.info(
            "All three JSON files already exist in %s. Use --force to re-extract.", raw_dir)
    else:
        zip_path = args.zip or (raw_dir / ZIP_NAME)
        if args.zip is None and not zip_path.is_file():
            if not download_zip(DATASET_URLS, zip_path):
                logger.error(MANUAL_HELP)
                return 1
        try:
            extract_expected_files(zip_path, raw_dir)
        except (FileNotFoundError, ValueError, zipfile.BadZipFile) as exc:
            logger.error("Extraction failed: %s", exc)
            return 1

    for name in SOURCES.values():
        path = raw_dir / name
        logger.info("%s | %.1f MB | sha256=%s", name,
                    path.stat().st_size / 1e6, sha256_of(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
