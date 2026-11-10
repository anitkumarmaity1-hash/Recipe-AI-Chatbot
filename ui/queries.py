"""Small READ-ONLY lookups the pages need to draw themselves (titles for cards, an ingredient
dropdown, a step-count histogram). They only read tables the backend already built.

Anything that is a recipe fact with business rules (search, matching, substitution, statistics,
restriction checks) is NOT done here; it goes through the backend (see `ui/services.py`).
"""

from __future__ import annotations

from typing import Any, Sequence

import duckdb

from recipebot.data_loading import SOURCE_LABELS
from ui.engine import Engine

HIST_MAX_STEPS = 30


def recipe_record(engine: Engine, recipe_id: str) -> dict[str, Any] | None:
    with engine.locked():
        row = engine.con.execute(
            "SELECT r.row_idx, r.id, r.title, r.source, r.ingredients_clean, r.instructions_clean, "
            "rs.n_steps FROM recipes r JOIN recipe_stats rs ON rs.row_idx = r.row_idx "
            "WHERE r.id = ?", [recipe_id]).fetchone()
    if row is None:
        return None
    row_idx, rid, title, source, lines, instructions, n_steps = row
    return {"row_idx": row_idx, "id": rid, "title": title, "source": source,
            "source_label": SOURCE_LABELS.get(source, source), "lines": list(lines or []),
            "instructions": instructions or "", "n_steps": n_steps}


def summaries(engine: Engine, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """id -> title, source label, n_steps, n_ingredients (for recipe cards)."""
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    with engine.locked():
        rows = engine.con.execute(
            "SELECT r.id, r.title, r.source, rs.n_steps, rs.n_ingredients FROM recipes r "
            f"JOIN recipe_stats rs ON rs.row_idx = r.row_idx WHERE r.id IN ({marks})",
            list(ids)).fetchall()
    return {rid: {"title": t, "source": SOURCE_LABELS.get(s, s), "n_steps": n, "n_ingredients": i}
            for rid, t, s, n, i in rows}


def ingredient_bases(engine: Engine, recipe_id: str) -> list[str]:
    """The ingredient names of one recipe that the substitution tool understands."""
    with engine.locked():
        rows = engine.con.execute(
            "SELECT DISTINCT canonical_base FROM recipe_ingredient WHERE recipe_id = ? ORDER BY 1",
            [recipe_id]).fetchall()
    return [r[0] for r in rows]


def dataset_overview(engine: Engine) -> dict[str, Any]:
    """Counts the statistics tool does not offer: recipes per source, excluded records, and a
    summary of the step counts. Plain aggregates over the backend's own tables.

    Step rule (backend, docs/DESIGN.md): one step = one sentence; 0 steps = no usable instructions.
    The step summary below counts only recipes with at least one step.
    """
    out: dict[str, Any] = {}
    with engine.locked():
        con = engine.con
        out["usable"] = con.execute(
            "SELECT count(*) FROM recipe_stats").fetchone()[0]
        out["by_source"] = [
            {"source": s, "label": SOURCE_LABELS.get(s, s), "recipes": n,
             "mean_steps": None if m is None else float(m), "median_steps": None if md is None else float(md)}
            for s, n, m, md in con.execute(
                "SELECT r.source, count(*), avg(rs.n_steps) FILTER (WHERE rs.n_steps >= 1), "
                "median(rs.n_steps) FILTER (WHERE rs.n_steps >= 1) FROM recipes r "
                "JOIN recipe_stats rs ON rs.row_idx = r.row_idx GROUP BY r.source ORDER BY 2 DESC"
            ).fetchall()]
        n, mean, median, lo, hi = con.execute(
            "SELECT count(*), avg(n_steps), median(n_steps), min(n_steps), max(n_steps) "
            "FROM recipe_stats WHERE n_steps >= 1").fetchone()
        out["n_zero_steps"] = con.execute(
            "SELECT count(*) FROM recipe_stats WHERE n_steps = 0").fetchone()[0]
        out["steps"] = None if not n else {"n": n, "mean": float(mean), "median": float(median),
                                           "min": lo, "max": hi}
        hist = con.execute(
            "SELECT least(n_steps, ?) AS bucket, count(*) FROM recipe_stats WHERE n_steps >= 1 "
            "GROUP BY 1 ORDER BY 1", [HIST_MAX_STEPS]).fetchall()
        out["step_histogram"] = [
            {"steps": int(b), "recipes": int(c)} for b, c in hist]
        out["hist_cap"] = HIST_MAX_STEPS
        try:
            out["excluded"] = [{"reason": r, "records": int(c)} for r, c in con.execute(
                "SELECT reason, count(*) FROM recipes_excluded GROUP BY reason ORDER BY 2 DESC"
            ).fetchall()]
        except duckdb.CatalogException:
            # table not present in this database
            out["excluded"] = None
    return out
