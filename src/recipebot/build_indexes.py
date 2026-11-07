"""Build the search indexes and write docs/INDEX_REPORT.md.

Usage (project root, venv active):
    python -m recipebot.build_indexes bm25                # fast
    python -m recipebot.build_indexes embeddings --benchmark 500   # speed test only
    python -m recipebot.build_indexes embeddings          # slow, resumable
    python -m recipebot.build_indexes all
Add --force to discard cached embedding shards.
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime

from recipebot import config
from recipebot.db import connect
from recipebot.retrieval.bm25 import Bm25Index, build_bm25
from recipebot.retrieval.common import (
    BM25_PATH,
    EMBEDDING_MODEL,
    FAISS_PATH,
    embedding_text,
    load_corpus,
)
from recipebot.retrieval.embeddings import SemanticIndex, build_embeddings, default_encoder

logger = logging.getLogger(__name__)

REPORT_PATH = config.PROJECT_ROOT / "docs" / "INDEX_REPORT.md"
SAMPLE_QUERIES = [
    "penne pasta",
    "chicken tomato garlic",
    "banana bread without eggs",
    "vegetarian chili",
]


def run_benchmark(n: int) -> None:
    """Measure encoding speed on n evenly spaced recipes; write nothing."""
    corpus = load_corpus()
    all_texts = [embedding_text(t, i) for t, i in zip(
        corpus.titles, corpus.ingredients)]
    step = max(1, len(all_texts) // n)
    texts = all_texts[::step][:n]
    t0 = time.perf_counter()
    enc = default_encoder()
    print(f"Model load: {time.perf_counter() - t0:.1f} s")
    enc(texts[:32])  # warm-up
    t1 = time.perf_counter()
    enc(texts)
    dt = time.perf_counter() - t1
    rate = len(texts) / dt
    print(f"Encoded {len(texts)} texts in {dt:.1f} s = {rate:.0f} texts/s")
    print(
        f"ESTIMATE for all {len(all_texts)} recipes: about "
        f"{len(all_texts) / rate / 60:.0f} minutes (extrapolated, not measured)"
    )


def _titles(row_idxs: list[int]) -> list[str]:
    con = connect(read_only=True)
    try:
        return [
            con.execute("SELECT title FROM recipes WHERE row_idx = ?", [
                        i]).fetchone()[0]
            for i in row_idxs
        ]
    finally:
        con.close()


def _sample_section() -> list[str]:
    lines = ["## Sample queries (top 5)", ""]
    bm25 = Bm25Index.load() if BM25_PATH.exists() else None
    sem = SemanticIndex.load() if FAISS_PATH.exists() else None
    bm25_times: list[float] = []
    for query in SAMPLE_QUERIES:
        lines.append(f"### `{query}`")
        if bm25:
            t0 = time.perf_counter()
            hits = bm25.top_k(query, k=5)
            bm25_times.append(time.perf_counter() - t0)
            lines.append("BM25: " + "; ".join(
                f"{t} ({s:.1f})" for t, (_, s) in zip(_titles([h[0] for h in hits]), hits)
            ))
        if sem:
            hits = sem.search(query, k=5)
            lines.append("Semantic: " + "; ".join(
                f"{t} ({s:.2f})" for t, (_, s) in zip(_titles([h[0] for h in hits]), hits)
            ))
        lines.append("")
    if bm25_times:
        lines.append(
            f"BM25 average query time over {len(bm25_times)} queries: "
            f"{1000 * sum(bm25_times) / len(bm25_times):.0f} ms"
        )
        lines.append("")
    lines.append(
        "Note: neither index understands negation, so 'without eggs' is NOT "
        "enforced here. Hard constraints are applied later by SQL (Step 7)."
    )
    return lines


def write_report(stats: dict) -> None:
    lines = [
        "# Index report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    if "bm25" in stats:
        s = stats["bm25"]
        t0 = time.perf_counter()
        Bm25Index.load()
        load_s = time.perf_counter() - t0
        lines += [
            "## BM25 (rank_bm25.BM25Okapi)",
            f"- documents: {s['n_docs']}",
            f"- vocabulary: {s['vocab_size']} tokens",
            f"- average tokens per document: {s['avg_doc_tokens']:.1f}",
            f"- build time: {s['seconds']:.0f} s",
            f"- pickle size: {s['size_mb']:.0f} MB",
            f"- load time (startup cost): {load_s:.1f} s",
            f"- ID fingerprint: {s['fingerprint']}",
            "",
        ]
    if "embeddings" in stats:
        s = stats["embeddings"]
        lines += [
            "## FAISS IndexFlatIP",
            f"- model: {s['model']}",
            f"- vectors: {s['n_vectors']} x {s['dim']}",
            f"- encoded in this run: {s['encoded_this_run']} "
            f"({s['seconds_this_run']:.0f} s); shards reused: "
            f"{s['shards_skipped']}/{s['shards_total']}",
            f"- index size: {s['size_mb']:.0f} MB",
            f"- ID fingerprint: {s['fingerprint']}",
            "",
        ]
    if "bm25" in stats and "embeddings" in stats:
        same = stats["bm25"]["fingerprint"] == stats["embeddings"]["fingerprint"]
        lines += [f"Fingerprints equal (same recipes, same order): {same}", ""]
    lines += _sample_section()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written: {REPORT_PATH}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Build BM25 and FAISS indexes.")
    parser.add_argument("target", choices=["bm25", "embeddings", "all"])
    parser.add_argument("--benchmark", type=int, default=0,
                        help="only measure encoding speed on N texts")
    parser.add_argument("--force", action="store_true",
                        help="discard cached embedding shards")
    args = parser.parse_args(argv)

    if args.benchmark:
        run_benchmark(args.benchmark)
        return 0

    stats: dict = {}
    if args.target in ("bm25", "all"):
        stats["bm25"] = build_bm25()
        print(f"BM25 done: {stats['bm25']}")
    if args.target in ("embeddings", "all"):
        stats["embeddings"] = build_embeddings(force=args.force)
        print(f"Embeddings done: {stats['embeddings']}")
    write_report(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
