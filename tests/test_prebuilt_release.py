"""The prebuilt download URL and its one-time GitHub release publication path."""

import sys
import urllib.error
from pathlib import Path

from scripts import fetch_prebuilt


def test_default_url_matches_the_release_asset_published_by_the_workflow():
    assert fetch_prebuilt.DEFAULT_URL == (
        "https://github.com/anitkumarmaity1-hash/Recipe-AI-Chatbot/"
        "releases/download/data-v1/nosh_data.zip"
    )
    workflow = Path(".github/workflows/publish-prebuilt.yml").read_text(encoding="utf-8")
    assert 'default: data-v1' in workflow
    assert 'gh release upload "$RELEASE_TAG" dist/nosh_data.zip --clobber' in workflow


def test_missing_default_asset_points_to_the_workflow(monkeypatch, capsys):
    def raise_404(*args, **kwargs):
        raise urllib.error.HTTPError(
            fetch_prebuilt.DEFAULT_URL, 404, "Not Found", hdrs=None, fp=None
        )

    monkeypatch.setattr(fetch_prebuilt.urllib.request, "urlopen", raise_404)
    monkeypatch.setattr(sys, "argv", ["fetch_prebuilt.py"])

    assert fetch_prebuilt.main() == 2
    output = capsys.readouterr().out
    assert "Actions > Publish prebuilt recipe data > Run workflow" in output
    assert "data-v1" in output
