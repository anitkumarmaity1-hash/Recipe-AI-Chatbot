"""Diagnostic for substitution evidence (Step 11). Read-only; changes nothing.

Why it exists: for "replace egg in Country Banana Bread" the real run found only 10 related
recipes WITH egg and 14 WITHOUT, which is surprisingly few for such a common dish. This
script shows where the related-recipe groups come from, so we can tell whether the small
numbers are real (the similarity rule is too strict) or a bug.

    python -m recipebot.diagnose_substitution --recipe-id "ar:LCKl..." --replace egg --title-like "banana bread"

It prints: the original's ingredients and "core" set, how many recipes fall into each
similarity band, the most similar recipes with and without the ingredient, and (with
--title-like) how the recipes whose title contains the phrase score against the original.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import numpy as np

from recipebot import config
from recipebot.tools.substitution import SubstitutionMiner

BANDS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)


def _bands(sim: np.ndarray) -> str:
    return ", ".join(f">={b:g}: {int((sim >= b).sum())}" for b in BANDS)


def diagnose(con, miner: SubstitutionMiner, recipe_id: str, ingredient: str,
             title_like: str | None = None, top: int = 8) -> list[str]:
    t0 = time.perf_counter()
    res = miner.mine(recipe_id, ingredient)
    mine_s = time.perf_counter() - t0
    o, base, forms = res.original, res.target["base"], res.target["forms"]
    core = res.pools["original_core_ingredients"]
    cfg = miner.settings
    out = [f"Original: {o['title']}  [{o['id']}]  ({o['n_steps']} steps)",
           f"mine() took {mine_s:.2f} s",
           "Ingredient lines:"]
    out += [f"  {line}" for line in o["ingredient_lines"]]
    out.append(f"Replacing: {base} (forms {forms})")
    out.append(f"Core ingredients ({len(core)}): {', '.join(core)}")
    out.append(f"Thresholds: related >= {cfg.related_min_sim}, same dish >= {cfg.neighbor_min_sim} "
               f"+ {cfg.min_title_overlap} shared title word(s), min support {cfg.min_support}")
    if not core:
        return out + ["No core ingredients: nothing to compare."]

    row_idx, has_target, sim, _steps = miner._similar_recipes(
        o["row_idx"], base, forms, core)
    out.append(f"Recipes sharing at least one core ingredient: {len(row_idx)}")
    for flag, name in ((True, "WITH"), (False, "WITHOUT")):
        sel = has_target == flag
        out.append(
            f"  {name} {base}: {int(sel.sum())} recipes; by similarity: {_bands(sim[sel])}")

    titles = miner._titles([int(r) for r in row_idx])
    for flag, name in ((True, "WITH"), (False, "WITHOUT")):
        idx = np.flatnonzero(has_target == flag)
        order = np.lexsort((row_idx[idx], -np.round(sim[idx], 9)))[:top]
        out.append(f"Most similar recipes {name} {base}:")
        sets = miner._sets_of([int(row_idx[idx[i]]) for i in order])
        for i in order:
            r = int(row_idx[idx[i]])
            out.append(f"  sim {sim[idx[i]]:.2f} [{titles[r][0]}] {titles[r][1]}: "
                       f"{', '.join(sorted(sets[r]))}")

    if title_like:
        phrase = title_like.lower()
        rows = [r for (r,) in con.execute(
            "SELECT row_idx FROM recipes WHERE lower(title) LIKE ? AND row_idx <> ?",
            [f"%{phrase}%", o["row_idx"]]).fetchall()]
        out.append(f"Recipes whose title contains '{title_like}': {len(rows)}")
        if rows:
            having = {r for (r,) in con.execute(
                "SELECT DISTINCT row_idx FROM recipe_ingredient "
                "WHERE row_idx IN (SELECT unnest(?::INTEGER[])) "
                "AND (canonical_base = ? OR list_contains(?, canonical))",
                [rows, base, forms]).fetchall()}
            sim_of = dict(zip(row_idx.tolist(), sim.tolist()))
            scores = {r: sim_of.get(r, 0.0) for r in rows}
            with_rows = [r for r in rows if r in having]
            without_rows = [r for r in rows if r not in having]
            for name, group in (("WITH", with_rows), ("WITHOUT", without_rows)):
                s = np.array([scores[r] for r in group]
                             ) if group else np.zeros(0)
                out.append(f"  {name} {base}: {len(group)} recipes; "
                           f"similarity >= {cfg.related_min_sim}: {int((s >= cfg.related_min_sim).sum())}; "
                           f"median similarity {float(np.median(s)) if len(s) else 0:.2f}")
            low = sorted(rows, key=lambda r: (scores[r], r))[:top]
            sets = miner._sets_of(low)
            names = miner._titles(low)
            out.append("  Lowest-scoring recipes with that title phrase:")
            for r in low:
                out.append(f"    sim {scores[r]:.2f} [{names[r][0]}] {names[r][1]}: "
                           f"{', '.join(sorted(sets[r]))}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m recipebot.diagnose_substitution")
    parser.add_argument("--recipe-id", required=True)
    parser.add_argument("--replace", required=True)
    parser.add_argument("--title-like", default=None,
                        help="phrase to look for in other recipes' titles, e.g. 'banana bread'")
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args(argv)

    from recipebot.db import connect
    from recipebot.tools.matching import RecipeMatcher
    from recipebot.tools.stats import RecipeStats, UnknownIngredientError
    from recipebot.tools.substitution import SubstitutionError

    config.setup_logging(logging.WARNING)
    con = connect(read_only=True)
    try:
        stats = RecipeStats(con)
        miner = SubstitutionMiner(
            con, stats, staples=RecipeMatcher(con, stats).staples)
        try:
            print("\n".join(diagnose(con, miner, args.recipe_id, args.replace,
                                     args.title_like, args.top)))
        except (SubstitutionError, UnknownIngredientError) as exc:
            print(exc)
            return 1
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
