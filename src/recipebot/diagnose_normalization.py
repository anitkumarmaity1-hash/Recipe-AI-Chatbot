"""Read-only diagnostics for Step 4b. Writes docs/NORMALIZATION_DIAGNOSTICS.md.

Run from the project root:
    python -m recipebot.diagnose_normalization
It never modifies the database.
"""

from __future__ import annotations

from datetime import datetime

from recipebot import config
from recipebot.db import connect

REPORT_PATH = config.PROJECT_ROOT / "docs" / "NORMALIZATION_DIAGNOSTICS.md"

# (base, more specific form) pairs whose relationship we must decide.
VARIANT_PAIRS = [
    ("butter", "unsalted butter"),
    ("olive oil", "extra-virgin olive oil"),
    ("sugar", "white sugar"),
    ("salt", "kosher salt"),
    ("pepper", "black pepper"),
    ("cinnamon", "ground cinnamon"),
    ("flour", "all-purpose flour"),
    ("milk", "whole milk"),
    ("onion", "red onion"),
]

# Words that may be noise inside canonical names.
DESCRIPTOR_CANDIDATES = [
    "homemade", "store-bought", "reduced-sodium", "low-sodium", "small-diced",
    "unsalted", "fresh", "dried", "frozen", "organic", "plain", "light",
    "extra-virgin", "freshly", "good-quality", "high-quality",
]


def clip(text: str | None, n: int = 160) -> str:
    text = (text or "").replace("\n", " ")
    return text if len(text) <= n else text[:n] + "..."


def table(headers: list[str], rows: list[tuple]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("|", "/")
                   for c in row) + " |")
    return out + [""]


def main() -> int:
    con = connect(read_only=True)
    def q(sql, p=None): return con.execute(sql, p or []).fetchall()
    L: list[str] = [
        "# Normalization diagnostics (Step 4b-1)", "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}", "",
    ]

    # 1. zero-step recipes
    L += ["## 1. Recipes with 0 steps", ""]
    split = q(
        "SELECT r.instructions_empty, COUNT(*) FROM recipe_stats rs "
        "JOIN recipes r ON r.row_idx = rs.row_idx WHERE rs.n_steps = 0 "
        "GROUP BY 1 ORDER BY 1"
    )
    L += table(["instructions_empty", "recipes"], split)
    rows = q(
        "SELECT rs.id, r.title, length(r.instructions_clean), "
        "left(r.instructions_clean, 120) FROM recipe_stats rs "
        "JOIN recipes r ON r.row_idx = rs.row_idx "
        "WHERE rs.n_steps = 0 AND NOT r.instructions_empty ORDER BY rs.id LIMIT 15"
    )
    L += ["Zero steps although instructions are NOT empty (first 15):", ""]
    L += table(["id", "title", "chars", "start of instructions_clean"], rows)

    # 2. highest step counts
    L += ["## 2. Highest step counts", ""]
    rows = q(
        "SELECT rs.id, r.title, rs.n_steps, length(r.instructions_clean), "
        "length(r.instructions_clean) - length(replace(r.instructions_clean, chr(10), '')) "
        "FROM recipe_stats rs JOIN recipes r ON r.row_idx = rs.row_idx "
        "ORDER BY rs.n_steps DESC, rs.id LIMIT 8"
    )
    L += table(["id", "title", "n_steps", "chars", "newlines"], rows)

    # 3. possible under-splitting
    L += ["## 3. Possible under-splitting (1 step but long text)", ""]
    n_sus = q(
        "SELECT COUNT(*) FROM recipe_stats rs JOIN recipes r ON r.row_idx = rs.row_idx "
        "WHERE rs.n_steps = 1 AND length(r.instructions_clean) > 400"
    )[0][0]
    n_one = q("SELECT COUNT(*) FROM recipe_stats WHERE n_steps = 1")[0][0]
    L += [f"- recipes with exactly 1 step: {n_one}",
          f"- of those, with more than 400 characters of instructions: {n_sus}", ""]
    rows = q(
        "SELECT rs.id, r.title, length(r.instructions_clean), "
        "left(r.instructions_clean, 220) FROM recipe_stats rs "
        "JOIN recipes r ON r.row_idx = rs.row_idx "
        "WHERE rs.n_steps = 1 AND length(r.instructions_clean) > 400 "
        "ORDER BY rs.id LIMIT 8"
    )
    L += table(["id", "title", "chars", "start of instructions_clean"], rows)
    rows = q(
        "SELECT rs.id, r.title, rs.n_steps, r.instructions_clean FROM recipe_stats rs "
        "JOIN recipes r ON r.row_idx = rs.row_idx WHERE r.title ILIKE '%Brunswick Stew%' "
        "ORDER BY rs.n_steps LIMIT 3"
    )
    L += ["Brunswick Stew recipes (full cleaned instructions):", ""]
    for rid, title, n, text in rows:
        L += [f"- `{rid}` {title}, n_steps={n}", f"  > {clip(text, 700)}"]
    L.append("")

    # 4. recipes without canonical ingredients
    L += ["## 4. Recipes with no canonical ingredient", ""]
    rows = q(
        "SELECT rs.id, r.title, array_to_string(r.ingredients_clean, ' || ') "
        "FROM recipe_stats rs JOIN recipes r ON r.row_idx = rs.row_idx "
        "WHERE NOT EXISTS (SELECT 1 FROM recipe_ingredient ri WHERE ri.row_idx = rs.row_idx)"
    )
    L += table(["id", "title", "ingredient lines"],
               [(a, b, clip(c, 200)) for a, b, c in rows])

    # 5. non-ingredient prefixes
    L += ["## 5. Lines with a 'prefix:' (candidates for non-ingredient lines)", ""]
    rows = q(
        "SELECT regexp_extract(lower(raw_line), '^([^:]{2,40}):', 1) AS prefix, "
        "COUNT(*) AS lines, min(canonical) AS example_canonical, "
        "min(raw_line) AS example_line FROM recipe_ingredient "
        "WHERE name_index = 0 AND regexp_matches(raw_line, '^[^:]{2,40}:') "
        "GROUP BY 1 ORDER BY lines DESC LIMIT 40"
    )
    L += table(["prefix", "lines", "example canonical", "example line"],
               [(a, b, c, clip(d, 90)) for a, b, c, d in rows])

    # 6. descriptor candidates
    L += ["## 6. Candidate descriptor words inside canonical names", ""]
    rows = []
    for word in DESCRIPTOR_CANDIDATES:
        res = q(
            "SELECT COUNT(DISTINCT canonical), COUNT(DISTINCT row_idx) FROM recipe_ingredient "
            "WHERE regexp_matches(canonical, ?)", [
                r"(^|[ -])" + word + r"($|[ -])"],
        )[0]
        ex = q(
            "SELECT canonical, COUNT(DISTINCT row_idx) n FROM recipe_ingredient "
            "WHERE regexp_matches(canonical, ?) GROUP BY 1 ORDER BY n DESC LIMIT 3",
            [r"(^|[ -])" + word + r"($|[ -])"],
        )
        rows.append((word, res[0], res[1], ", ".join(
            f"{c} ({n})" for c, n in ex)))
    L += table(["word", "distinct names", "recipes", "top examples"], rows)

    # 7. variant pairs
    L += ["## 7. Variant pairs: how often each form appears, and together", ""]
    rows = []
    for base, spec in VARIANT_PAIRS:
        nb = q("SELECT COUNT(DISTINCT row_idx) FROM recipe_ingredient WHERE canonical = ?", [
               base])[0][0]
        ns = q("SELECT COUNT(DISTINCT row_idx) FROM recipe_ingredient WHERE canonical = ?", [
               spec])[0][0]
        both = q(
            "SELECT COUNT(*) FROM (SELECT row_idx FROM recipe_ingredient WHERE canonical IN (?, ?) "
            "GROUP BY row_idx HAVING COUNT(DISTINCT canonical) = 2)", [
                base, spec],
        )[0][0]
        rows.append((base, nb, spec, ns, both))
    L += table(["base", "recipes", "specific form",
               "recipes", "recipes with both"], rows)

    # 8. 'A and B' lines that produced a single name
    L += ["## 8. Lines containing ' and ' that produced only one ingredient row", ""]
    sub = (
        "SELECT recipe_id, position, count(*) c, any_value(raw_line) l, any_value(canonical) k "
        "FROM recipe_ingredient GROUP BY recipe_id, position"
    )
    n_and = q(
        f"SELECT COUNT(*) FROM ({sub}) WHERE c = 1 AND l ILIKE '% and %'")[0][0]
    rows = q(f"SELECT l, k FROM ({sub}) WHERE c = 1 AND l ILIKE '% and %' "
             "ORDER BY hash(l) LIMIT 20")
    L += [f"- line occurrences: {n_and} (many are fine, e.g. 'macaroni and cheese' as one product)", ""]
    L += table(["line", "canonical"], [(clip(a, 100), b) for a, b in rows])

    con.close()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Report written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
