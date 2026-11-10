"""Run the evaluation set against the real chatbot (real database, indexes and Gemini key).

    python eval/run_eval.py                 (project root, venv active, data built, .env filled)
    python eval/run_eval.py --only T3       (only case ids that start with T3)
    python eval/run_eval.py --sleep 6       (seconds between turns; protects the free API quota)

Writes eval/results/eval_results.json and eval/results/eval_report.md.
A case passes only if every check of every checked turn passes (see eval/checks.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checks import run_checks  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


class DbFacts:
    """Facts read straight from DuckDB, never from the chatbot's answer."""

    def __init__(self, con, matcher):
        self.con, self.matcher = con, matcher

    def _rows(self, sql: str, ids):
        return self.con.execute(sql, [list(ids)]).fetchall() if ids else []

    def existing_ids(self, ids):
        return {r[0] for r in self._rows(
            "SELECT id FROM recipes WHERE id IN (SELECT unnest(?::VARCHAR[]))", ids)}

    def n_steps(self, ids):
        return dict(self._rows(
            "SELECT r.id, s.n_steps FROM recipes r JOIN recipe_stats s ON s.row_idx = r.row_idx "
            "WHERE r.id IN (SELECT unnest(?::VARCHAR[]))", ids))

    def allergen_hits(self, ids, allergen):
        hits = []
        for rid, lines in self._rows(
                "SELECT id, ingredients_clean FROM recipes WHERE id IN (SELECT unnest(?::VARCHAR[]))", ids):
            for line in lines or []:
                if self.matcher.matches(line, allergen):
                    hits.append(f"{rid}: {line}")
        return hits


def run_case(agent, case: dict, facts, sleep: float = 0.0) -> dict:
    """Play one case turn by turn. Only turns with "checks" are judged."""
    agent.reset()
    failures: list[str] = []
    last_text = ""
    for number, turn in enumerate(case["turns"], 1):
        reply = agent.handle(turn["say"])
        last_text = reply.text
        if "checks" in turn:
            failures += [f"turn {number}: {f}" for f in run_checks(
                reply.text, reply.intent, reply.guard_problems, turn["checks"], facts)]
        if sleep:
            time.sleep(sleep)
    return {"id": case["id"], "task": case["task"], "what": case["what"],
            "passed": not failures, "failures": failures, "last_reply": last_text}


def write_report(results: list[dict]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "eval_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    passed = sum(r["passed"] for r in results)
    lines = [f"# Evaluation results\n\n{passed} of {len(results)} cases passed.\n",
             "| Case | Task | What it checks | Result |", "|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| {r['id']} | {r['task']} | {r['what']} | {'PASS' if r['passed'] else 'FAIL'} |")
    failed = [r for r in results if not r["passed"]]
    if failed:
        lines.append("\n## Failures\n")
        for r in failed:
            lines.append(f"### {r['id']}\n")
            lines += [f"- {f}" for f in r["failures"]]
            lines.append("\nLast reply:\n\n```text\n" +
                         r["last_reply"][:1500] + "\n```\n")
    (RESULTS_DIR / "eval_report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the NOSH evaluation set.")
    parser.add_argument("--only", default="",
                        help="run only case ids that start with this text")
    parser.add_argument("--sleep", type=float, default=4.0,
                        help="seconds between turns")
    args = parser.parse_args(argv)

    from recipebot.cli import build_agent
    from recipebot.db import connect

    cases = [c for c in json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
             if c["id"].startswith(args.only)]
    con = connect(read_only=True)
    agent = build_agent(con)
    facts = DbFacts(con, agent.retriever.matcher)
    results = []
    for case in cases:
        result = run_case(agent, case, facts, args.sleep)
        print(f"{'PASS' if result['passed'] else 'FAIL'}  {result['id']}")
        for failure in result["failures"]:
            print(f"      {failure}")
        results.append(result)
    write_report(results)
    print(f"\n{sum(r['passed'] for r in results)} of {len(results)} passed. "
          f"Report: {RESULTS_DIR / 'eval_report.md'}")
    con.close()
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
