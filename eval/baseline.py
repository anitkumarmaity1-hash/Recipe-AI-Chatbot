"""One-shot LLM baseline: the same questions, asked to Gemini WITHOUT tools or the dataset.

    python eval/baseline.py          (project root, venv active, .env filled)

For each case in eval/golden.json that has a "baseline" entry:
  kind "number"  : correct only if the expected number appears in the answer
  kind "recipes" : grounded only if the answer cites recipe ids and EVERY id exists in the database
Writes eval/results/baseline_results.json and eval/results/baseline_report.md (side by side with
the chatbot's answer from eval_results.json when that file exists).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
ID_LIKE = re.compile(r"\b(?:ar|epi|fn):[A-Za-z0-9./_-]+")


def judge_number(answer: str, expect: str) -> tuple[bool, str]:
    found = expect.replace(",", "") in answer.replace(",", "")
    return found, ("contains the exact value " + expect) if found else f"does not contain the real value {expect}"


def judge_recipes(answer: str, existing) -> tuple[bool, str]:
    """existing: function(list of ids) -> set of ids that exist in the database."""
    ids = [i.rstrip(".,;:)") for i in dict.fromkeys(ID_LIKE.findall(answer))]
    if not ids:
        return False, "no recipe ids given, so nothing can be checked against the dataset"
    real = existing(ids)
    fake = [i for i in ids if i not in real]
    if fake:
        return False, f"{len(fake)} of {len(ids)} cited ids do not exist in the dataset (e.g. {fake[0]})"
    return True, f"all {len(ids)} cited ids exist"


def ask_gemini(question: str) -> str:
    from google import genai
    from google.genai import types

    from recipebot import config
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=config.GEMINI_MODEL, contents=question,
        config=types.GenerateContentConfig(temperature=0, max_output_tokens=900))
    return response.text or ""


def main() -> int:
    from recipebot.db import connect
    cases = [c for c in json.loads((HERE / "golden.json").read_text(encoding="utf-8"))["cases"]
             if "baseline" in c]
    system = {}
    if (RESULTS_DIR / "eval_results.json").exists():
        system = {r["id"]: r for r in json.loads(
            (RESULTS_DIR / "eval_results.json").read_text(encoding="utf-8"))}
    con = connect(read_only=True)

    def existing(ids):
        return {r[0] for r in con.execute(
            "SELECT id FROM recipes WHERE id IN (SELECT unnest(?::VARCHAR[]))", [ids]).fetchall()}

    rows = []
    for case in cases:
        spec = case["baseline"]
        answer = ask_gemini(spec["question"])
        ok, why = (judge_number(answer, spec["expect"]) if spec["kind"] == "number"
                   else judge_recipes(answer, existing))
        rows.append({"id": case["id"], "question": spec["question"], "baseline_answer": answer,
                     "baseline_ok": ok, "why": why,
                     "system_passed": system.get(case["id"], {}).get("passed"),
                     "system_answer": system.get(case["id"], {}).get("last_reply", "")})
        print(f"{'OK  ' if ok else 'BAD '} {case['id']}: {why}")
        time.sleep(4)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "baseline_results.json").write_text(json.dumps(rows,
                                                                  indent=2, ensure_ascii=False), encoding="utf-8")
    out = ["# One-shot LLM baseline vs the chatbot\n",
           "The baseline is the same Gemini model asked once, with no database and no tools.\n",
           "| Case | One-shot LLM | Chatbot (eval set) |", "|---|---|---|"]
    for r in rows:
        sys_cell = {True: "PASS", False: "FAIL",
                    None: "not run"}[r["system_passed"]]
        out.append(
            f"| {r['id']} | {'grounded' if r['baseline_ok'] else 'WRONG/UNGROUNDED'}: {r['why']} | {sys_cell} |")
    for r in rows:
        out.append(f"\n## {r['id']}\n\n**Question:** {r['question']}\n\n**One-shot answer:**\n\n```text\n"
                   f"{r['baseline_answer'][:1500]}\n```\n\n**Chatbot answer:**\n\n```text\n{r['system_answer'][:1500]}\n```\n")
    (RESULTS_DIR / "baseline_report.md").write_text("\n".join(out), encoding="utf-8")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
