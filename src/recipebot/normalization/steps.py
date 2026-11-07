"""Step counting. Rule (approved): one step = one sentence of the CLEANED instructions,
split with pysbd. An empty instruction has 0 steps. n_lines is kept as evidence only.
"""
from __future__ import annotations

import re

import pysbd

_segmenter: pysbd.Segmenter | None = None


def _get_segmenter() -> pysbd.Segmenter:
    global _segmenter
    if _segmenter is None:
        _segmenter = pysbd.Segmenter(language="en", clean=False)
    return _segmenter


def split_steps(text: str | None) -> list[str]:
    """Split instructions into sentences (steps), ignoring fragments with no letters or digits."""
    if not text or not text.strip():
        return []
    sentences = _get_segmenter().segment(text)
    return [s.strip() for s in sentences if re.search(r"[A-Za-z0-9]", s)]


def count_steps(text: str | None) -> int:
    return len(split_steps(text))


def count_lines(text: str | None) -> int:
    """Number of non-empty lines (evidence for the step-rule decision, not used for ranking)."""
    if not text:
        return 0
    return sum(1 for line in text.splitlines() if line.strip())
