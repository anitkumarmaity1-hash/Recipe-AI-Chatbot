"""Answer composer (Step 9): turns tool output into text. No LLM, no database.

Every number and recipe id printed here comes straight from a tool result, and
every answer states the filters, the number of recipes analyzed and the method.
Plain ASCII punctuation is used on purpose (Windows consoles, saved transcripts).
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from recipebot.retrieval.common import BM25_WEIGHT, RRF_K, SEMANTIC_WEIGHT
from recipebot.retrieval.hybrid import HybridResult

ALLERGEN_DISCLAIMER = (
    "Allergen checks read the ingredient text only; hidden sources (for example milk "
    "inside chocolate chips) cannot be detected. This is not medical advice: always "
    "check the real labels."
)


def fmt_int(n: int) -> str:
    return f"{n:,}"


def plural(n: int, word: str) -> str:
    """'1 step', '4 steps' (all counted words here add a plain 's')."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def fmt_pct(x: float) -> str:
    return f"{x:.1f}%"


def _names(values: Iterable[str]) -> str:
    return ", ".join(v.replace("_", " ") for v in values)


# ----------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------
def constraints_text(c: dict[str, Any], unenforced: Sequence[str] = ()) -> str:
    """One line describing hard constraints (a Constraints.describe() dict)."""
    parts = []
    if c.get("exclude_allergens"):
        parts.append(f"no {_names(c['exclude_allergens'])} (allergen check)")
    if c.get("exclude"):
        parts.append(f"no {_names(c['exclude'])} (ingredient)")
    if c.get("include"):
        parts.append(f"must contain {_names(c['include'])}")
    if c.get("max_steps") is not None:
        parts.append(f"at most {plural(c['max_steps'], 'step')}")
    text = "; ".join(parts) or "none"
    if unenforced:
        text += f". NOT enforced (cannot be checked reliably): {_names(unenforced)}"
    return text


def filters_text(f: dict[str, Any]) -> str:
    """One line describing a statistics Filter.describe() dict."""
    if "of" in f and "among" in f:
        return f"of: {filters_text(f['of'])} | among: {filters_text(f['among'])}"
    parts = []
    if f.get("all_of"):
        parts.append(f"contains all of {_names(f['all_of'])}")
    if f.get("any_of"):
        parts.append(f"contains at least one of {_names(f['any_of'])}")
    if f.get("none_of"):
        parts.append(f"contains none of {_names(f['none_of'])}")
    if f.get("exclude_allergens"):
        parts.append(f"no {_names(f['exclude_allergens'])} (allergen check)")
    if f.get("max_steps") is not None:
        parts.append(f"at most {plural(f['max_steps'], 'step')}")
    if f.get("min_steps"):
        parts.append(f"at least {f['min_steps']} step(s)")
    return "; ".join(parts) or "none (all usable recipes)"


# ----------------------------------------------------------------------
# Search
# ----------------------------------------------------------------------
def _check_text(c: dict[str, Any], n_ingredients: int, n_steps: int) -> str:
    parts = []
    if c.get("exclude_allergens"):
        parts.append(
            f"no {_names(c['exclude_allergens'])} terms in its {n_ingredients} ingredient lines")
    if c.get("exclude"):
        parts.append(f"none of {_names(c['exclude'])} among its ingredients")
    if c.get("include"):
        parts.append(f"contains {_names(c['include'])}")
    if c.get("max_steps") is not None:
        parts.append(f"{plural(n_steps, 'step')} (limit {c['max_steps']})")
    return "; ".join(parts) or "no hard filters active"


def compose_search(
    res: HybridResult,
    unenforced: Sequence[str],
    info: dict[int, tuple[int, int]],
    changes: Sequence[str] = (),
) -> str:
    """info maps row_idx -> (n_steps, n_ingredients)."""
    c = res.constraints
    lines = list(changes)
    lines.append(f'Search: "{res.query}"')
    lines.append("Hard filters applied: " + constraints_text(c, unenforced))
    lines.append(f"Eligible recipes: {fmt_int(res.n_allowed)} of {fmt_int(res.n_total)} "
                 "pass these filters; nothing was relaxed.")
    if not res.hits:
        lines.append(res.note or "No recipes found.")
        lines.append("You can remove a restriction (for example 'dairy is fine now') "
                     "or ask for something else.")
    else:
        lines.append(f"Ranking: BM25 + embeddings fused with RRF (k={RRF_K}, "
                     f"weights {BM25_WEIGHT}/{SEMANTIC_WEIGHT}).")
        lines.append("")
        for pos, h in enumerate(res.hits, 1):
            n_steps, n_ing = info.get(h.row_idx, (0, 0))
            bm = f"#{h.bm25_rank}" if h.bm25_rank else "-"
            se = f"#{h.semantic_rank}" if h.semantic_rank else "-"
            lines.append(f"{pos}. {h.title}  [{h.id}]")
            lines.append(
                f"   {plural(n_steps, 'step')} | {n_ing} ingredients | BM25 {bm}, embeddings {se}")
            lines.append(f"   Check: {_check_text(c, n_ing, n_steps)}")
        lines.append("")
        lines.append(
            "Ask for 'the second one' to see its ingredients and steps.")
    if c.get("exclude_allergens"):
        lines.append(ALLERGEN_DISCLAIMER)
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Statistics
# ----------------------------------------------------------------------
def expected_numbers(res) -> list[str]:
    """Strings the guard requires in a statistics answer (taken from the tool result)."""
    v, n = res.value, res.n_analyzed
    if res.name == "count":
        return [fmt_int(v), fmt_int(n)]
    if res.name == "percentage":
        d = res.details
        return [] if v is None else [fmt_pct(v), fmt_int(d["numerator"]), fmt_int(d["denominator"])]
    if res.name == "ingredient_count_stats":
        return [] if v is None else [f"{v['mean']:.2f}", f"{v['median']:g}"]
    if res.name == "top_common_ingredients":
        return [fmt_int(row["n_recipes"]) for row in v]
    return [str(row["n_steps"]) for row in v] if res.name == "fewest_steps" else []


def compose_stats(res, notes: Sequence[str] = ()) -> str:
    """res is a tools.stats.StatsResult."""
    v, n, d = res.value, res.n_analyzed, res.details
    lines: list[str] = []
    if res.name == "count":
        lines.append(f"Answer: {fmt_int(v)} recipes ({fmt_pct(100 * v / n) if n else 'n/a'} of "
                     f"{fmt_int(n)} usable recipes).")
    elif res.name == "percentage":
        if v is None:
            lines.append(
                "Answer: undefined, because no recipe matches the 'among' filter.")
        else:
            lines.append(
                f"Answer: {fmt_pct(v)} ({fmt_int(d['numerator'])} of {fmt_int(d['denominator'])} recipes).")
    elif res.name == "ingredient_count_stats":
        if v is None:
            lines.append(
                "Answer: no recipe matches the filter, so there is nothing to average.")
        else:
            lines.append(f"Answer: mean {v['mean']:.2f}, median {v['median']:g}, "
                         f"min {v['min']}, max {v['max']} ingredients per recipe.")
    elif res.name == "top_common_ingredients":
        lines.append(
            "Most common ingredients (number of recipes containing each):")
        for pos, row in enumerate(v, 1):
            share = fmt_pct(100 * row["n_recipes"] / n) if n else "n/a"
            lines.append(
                f"{pos}. {row['ingredient']}: {fmt_int(row['n_recipes'])} recipes ({share})")
    elif res.name == "fewest_steps":
        if not v:
            lines.append(
                "No recipe matches these filters (recipes with 0 steps are not ranked).")
        else:
            lines.append("Recipes with the fewest steps:")
            for pos, row in enumerate(v, 1):
                lines.append(
                    f"{pos}. {row['title']}  [{row['id']}]  - {plural(row['n_steps'], 'step')}")
    lines.append(f"Recipes analyzed: {fmt_int(n)}")
    lines.append(f"Filters applied: {filters_text(res.filters)}")
    if res.name == "percentage":
        lines.append(f"Calculation: {d['calculation']} = {fmt_pct(v)}" if v is not None
                     else f"Calculation: {d['calculation']}")
    elif res.name == "count":
        lines.append(
            "Calculation: number of recipes that satisfy every filter (each recipe counted once).")
    elif res.name == "ingredient_count_stats":
        lines.append("Calculation: " + d["metric"])
    elif res.name == "top_common_ingredients":
        lines.append("Calculation: for each canonical ingredient, the number of distinct recipes "
                     "containing it among the analyzed recipes.")
    elif res.name == "fewest_steps":
        lines.append("Calculation: " + d["step_rule"])
    lines.append('Definition of "contains": ' + res.definition)
    lines.extend(f"Note: {note}" for note in notes)
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Recipe details
# ----------------------------------------------------------------------
def compose_details(
    recipe_id: str, title: str, source_label: str,
    ingredient_lines: Sequence[str], steps: Sequence[str],
    warnings: Sequence[str] = (),
) -> str:
    lines = [
        f"{title}  [{recipe_id}]  (source: {source_label})", "", "Ingredients:"]
    lines += [f"  - {line}" for line in ingredient_lines]
    lines += ["",
              f"Instructions ({plural(len(steps), 'step')}, one sentence = one step):"]
    lines += [f"  {i}. {step}" for i,
              step in enumerate(steps, 1)] or ["  (this recipe has no instructions)"]
    lines += ["", "Note: this is the cleaned text (ADVERTISEMENT markers and section-header lines "
                  "removed); the original text is stored unchanged in the database."]
    lines.extend(f"WARNING: {w}" for w in warnings)
    return "\n".join(lines)
