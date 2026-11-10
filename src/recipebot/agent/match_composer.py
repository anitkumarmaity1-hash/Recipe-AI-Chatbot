"""Answer text for ingredient matching (Step 10). No LLM, no database.

Every number and recipe id printed here comes from a MatchResult. The text
states the ingredients used, the hard filters, the denominators, the scoring
formula and, for every recipe, matched / missing / extra / steps and the
score arithmetic. Plain ASCII on purpose (Windows consoles, saved transcripts).
"""

from __future__ import annotations

from typing import Sequence

from recipebot.agent.composer import ALLERGEN_DISCLAIMER, constraints_text, fmt_int, plural
from recipebot.tools.matching import QUANTITY_NOTE, MatchResult


def expected_numbers(res: MatchResult) -> list[str]:
    """Strings the output guard requires in the answer."""
    if not res.terms:
        return []
    return [fmt_int(res.n_candidates), fmt_int(res.n_eligible)]


def _list(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "none"


def compose_match(res: MatchResult, unenforced: Sequence[str] = (),
                  changes: Sequence[str] = ()) -> str:
    c, s = res.constraints, res.settings
    lines = list(changes)
    if res.terms:
        lines.append(
            f"Ingredient match for: {', '.join(res.terms)} ({plural(len(res.terms), 'ingredient')})")
    for item in res.unknown:
        hint = f" Did you mean: {', '.join(item['suggestions'])}?" if item["suggestions"] else ""
        lines.append(f"Not recognized, ignored: '{item['term']}'.{hint}")
    for name in res.dropped:
        lines.append(
            f"Not counted: '{name}' is in your ingredient list but you also excluded it.")
    if not res.terms:
        lines.append(res.note)
        lines.append("Tell me which ingredients you have, for example "
                     "'I have eggs, flour and milk'.")
        return "\n".join(lines)

    lines.append("Hard filters applied: " + constraints_text(c, unenforced))
    lines.append(f"Recipes using at least one of your ingredients: {fmt_int(res.n_candidates)} "
                 f"of {fmt_int(res.n_total)}.")
    lines.append(f"Of these, {fmt_int(res.n_eligible)} pass the hard filters; nothing was relaxed. "
                 "Recipes without instructions are not ranked.")
    if not res.hits:
        lines.append(res.note)
        if res.alternatives:
            lines.append("")
            lines.append("NOT ELIGIBLE - these recipes use your ingredients but VIOLATE a hard "
                         "constraint. They are shown only so you can decide whether to change a "
                         "restriction; none of them is a result.")
            for pos, a in enumerate(res.alternatives, 1):
                lines.append(
                    f"{pos}. {a.title}  [{a.id}]  (closest by score {a.score:.2f}, NOT eligible)")
                lines.append("   VIOLATES: " + "; ".join(a.violations))
                lines.append(f"   Matched ({a.n_matched} of {len(res.terms)}): {_list(a.matched)} | "
                             f"extra needed ({a.n_extra}): {_list(a.extra)} | {plural(a.n_steps, 'step')}")
            lines.append("")
        lines.append("You can remove a restriction (for example 'dairy is fine now') "
                     "or list other ingredients.")
    else:
        lines.append(
            f"Ranking: score = {s['w_coverage']:g} x coverage - {s['w_extra']:g} x extra "
            f"- {s['w_steps']:g} x steps (steps counted up to {s['step_cap']}). "
            "coverage = matched / your ingredients; extra = extra needed / ingredients the "
            "recipe needs (pantry staples are not counted). Weights are design choices "
            "(src/recipebot/config.py), not measured values.")
        lines.append("")
        for pos, h in enumerate(res.hits, 1):
            lines.append(f"{pos}. {h.title}  [{h.id}]  score {h.score:.2f}")
            lines.append(
                f"   Matched ({h.n_matched} of {len(res.terms)}): {_list(h.matched)}")
            lines.append(f"   Missing, you have it but the recipe does not use it ({len(h.unused)}): "
                         f"{_list(h.unused)}")
            lines.append(f"   Extra needed, the recipe requires it and it is not in your list "
                         f"({h.n_extra}): {_list(h.extra)}")
            if h.staples:
                lines.append(
                    f"   Pantry staples assumed, not scored: {_list(h.staples)}")
            lines.append(
                f"   {plural(h.n_steps, 'step')} | score = {s['w_coverage']:g} x {h.coverage:.2f} "
                f"- {s['w_extra']:g} x {h.extra_ratio:.2f} "
                f"- {s['w_steps']:g} x {min(h.n_steps, s['step_cap'])} = {h.score:.2f}")
            lines.append("   Check: " + ("hard filters re-verified from the database, none violated"
                                         if any([c.get("include"), c.get("exclude"),
                                                 c.get("exclude_allergens"),
                                                 c.get("max_steps") is not None])
                                         else "no hard filters active"))
        lines.append("")
        lines.append(
            "Ask for 'the second one' to see its ingredients and steps.")
    lines.append(f"Quantities: {QUANTITY_NOTE}")
    if c.get("exclude_allergens"):
        lines.append(ALLERGEN_DISCLAIMER)
    return "\n".join(lines)
