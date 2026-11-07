"""Tests for Step 2: raw-file loading, download/extract logic and EDA statistics.

All fixtures here are SYNTHETIC records invented for testing; they are not
real dataset content and say nothing about the real data's statistics.
"""
from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from recipebot import config
from recipebot.data_loading import SOURCES, load_raw_file, raw_file_path
from recipebot.eda import analyze_cross_file, analyze_source, content_fingerprint, render_report


def _load_download_module():
    """Import scripts/download_data.py by path (scripts/ is not a package)."""
    path = config.PROJECT_ROOT / "scripts" / "download_data.py"
    spec = importlib.util.spec_from_file_location("download_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNTHETIC = {
    "k1": {"title": "Test Pasta", "ingredients": ["1 cup pasta", "2 tbsp butter"], "instructions": "Boil pasta. Add butter."},
    "k2": {"title": "Test Pasta", "ingredients": ["1 cup pasta", "2 tbsp butter"], "instructions": "Boil pasta. Add butter."},
    "k3": {"title": "Salad", "ingredients": ["ADVERTISEMENT", "For the dressing:", "", "1 lettuce"], "instructions": "Line one.\nLine two."},
    "k4": {"title": "", "ingredients": [], "instructions": None},
    "k5": None,
}


def test_analyze_source_counts():
    stats = analyze_source(SYNTHETIC)
    assert stats["n_records"] == 5
    assert stats["non_dict"] == 1
    assert stats["empty_counts"] == {
        "title": 1, "ingredients": 1, "instructions": 1}
    assert stats["records_with_0_ingredients"] == 1
    assert stats["ingredient_lines_total"] == 8
    assert stats["ingredient_lines_advert"] == 1
    assert stats["ingredient_lines_header_like"] == 1
    assert stats["ingredient_lines_empty"] == 1
    assert stats["instr_with_newline"] == 1
    assert stats["duplicate_title_extra_copies"] == 1
    assert stats["duplicate_content_extra_copies"] == 1


def test_cross_file_key_and_content_overlap():
    first = analyze_source({"same": SYNTHETIC["k1"], "a": SYNTHETIC["k3"]})
    second = analyze_source({"same": SYNTHETIC["k2"], "b": SYNTHETIC["k4"]})
    cross = analyze_cross_file({"ar": first, "epi": second})
    assert cross["total_records"] == 4
    assert cross["unique_keys_overall"] == 3
    assert cross["key_overlaps"] == {"ar & epi": 1}
    assert cross["content_overlaps"] == {"ar & epi": 1}


def test_fingerprint_ignores_key_but_not_content():
    assert content_fingerprint(
        SYNTHETIC["k1"]) == content_fingerprint(SYNTHETIC["k2"])
    assert content_fingerprint(
        SYNTHETIC["k1"]) != content_fingerprint(SYNTHETIC["k3"])


def test_render_report_contains_key_sections():
    results = {"ar": analyze_source(SYNTHETIC)}
    report = render_report(results, analyze_cross_file(results))
    assert "# EDA Report" in report
    assert "Per-file statistics" in report


def test_load_raw_file_reads_object_and_rejects_array(tmp_path: Path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"k": {"title": "x"}}), encoding="utf-8")
    assert load_raw_file(good) == {"k": {"title": "x"}}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_raw_file(bad)
    with pytest.raises(FileNotFoundError):
        load_raw_file(tmp_path / "missing.json")


def test_raw_file_path_rejects_unknown_source(tmp_path: Path):
    assert raw_file_path("ar", tmp_path).name == SOURCES["ar"]
    with pytest.raises(KeyError):
        raw_file_path("nope", tmp_path)


def test_extract_expected_files_is_zip_slip_safe(tmp_path: Path):
    module = _load_download_module()
    zip_path = tmp_path / "recipes_raw.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name in SOURCES.values():
            archive.writestr(f"nested/{name}", "{}")  # nested folder is fine
        archive.writestr("../evil.json", "{}")        # must never be written
    raw_dir = tmp_path / "raw"
    written = module.extract_expected_files(zip_path, raw_dir)
    assert sorted(p.name for p in written) == sorted(SOURCES.values())
    assert not (tmp_path / "evil.json").exists()
    assert sorted(p.name for p in raw_dir.iterdir() if p.suffix ==
                  ".json") == sorted(SOURCES.values())


def test_extract_raises_when_a_file_is_missing(tmp_path: Path):
    module = _load_download_module()
    zip_path = tmp_path / "partial.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(SOURCES["ar"], "{}")
    with pytest.raises(ValueError):
        module.extract_expected_files(zip_path, tmp_path / "raw")
