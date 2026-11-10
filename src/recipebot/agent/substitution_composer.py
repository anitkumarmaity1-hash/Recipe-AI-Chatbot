"""Answer text for ingredient substitution (Step 12). No LLM, no database.

Every number and recipe id printed here comes from a SubstitutionEvidence or an AdaptedRecipe.
The four-label uncertainty block and the disclaimers are built here, in code, so the labels
cannot drift. Plain ASCII on purpose (Windows consoles, saved transcripts).
"""

from __future__ import annotations

from typing import Sequence

from recipebot.agent.composer import ALLERGEN_DISCLAIMER, constraints_text, fmt_int
from recipebot.tools.adaptation import AdaptedRecipe
from recipebot.tools.substitution import Candidate, SubstitutionEvidence

SAFETY_NOTE = ("This is a recipe-text analysis, not medical or allergy advice. I cannot "
               "promise any adapted recipe is safe for you.")
LEVEL_TEXT = {
    "direct": "DIRECT evidence (same dish family)",
    "indirect": "INDIRECT evidence (related recipes only)",
    "none": "NO dataset evidence (general cooking knowledge only)",
}


def cited_ids(ev: SubstitutionEvidence) -> set[str]:
    """Every recipe id that may appear in the answer."""
    ids = {ev.original["id"]}
    for cand in ev.candidates:
        ids |= {e.id for e in cand.evidence}
    return ids


def expected_numbers(ev: SubstitutionEvidence) -> list[str]:
    """Strings the output guard requires in the answer."""
    return [fmt_int(ev.pools["n_related_with"]), fmt_int(ev.pools["n_related_without"])]


def _names(values: Sequence[str]) -> str:
    return ", ".join(v.replace("_", " ") for v in values) or "none"


def _candidate_lines(n: int, c: Candidate) -> list[str]:
    rates = ""
    if c.rate_without is not None:
        with_ = "n/a" if c.rate_with is None else f"{c.rate_with:.0%}"
        rates = f", used by {c.rate_without:.0%} of the related recipes without it vs {with_} with it"
    vocab = "" if c.in_vocabulary else "  [not an ingredient in the dataset]"
    out = [f"{n}. {c.name}: {LEVEL_TEXT[c.level]}  ({c.n_support} recipes, "
           f"{c.n_direct} of them same dish{rates}){vocab}"]
    for e in c.evidence:
        out.append(f"     [{e.id}] {e.title} ({e.tier}, similarity {e.similarity:.2f}, "
                   f"{e.n_steps} steps): " + "; ".join(e.lines))
    return out


def uncertainty_block(ev: SubstitutionEvidence, cand: Candidate, adapted: AdaptedRecipe) -> list[str]:
    """The four labels the assignment asks for, written from the evidence only."""
    p, base = ev.pools, ev.target["base"]
    lost = sorted(set(ev.role["roles"]) - set(cand.shared_roles))
    supported = (f"{cand.n_support} related recipes without {base} use {cand.name} "
                 f"({cand.n_direct} of the same dish family): "
                 + ", ".join(f"[{i}]" for i in adapted.supporting_ids)
                 + f". Evidence level: {cand.level}.")
    inferred = (f"Recipes count as 'similar' by shared ingredient names (Jaccard overlap), not by "
                f"method or amounts. Out of {fmt_int(p['n_without_used'])} related recipes without "
                f"{base}, the dataset suggests {cand.name} can play a similar part; it does not show "
                f"that it works in THIS recipe.")
    shared = _names(cand.shared_roles) if cand.shared_roles else "none known"
    predicted = (f"General cooking knowledge, not from the dataset: {cand.name} shares the roles "
                 f"[{shared}] with {base}"
                 + (f" but may not provide [{_names(lost)}]" if lost else "") + ". "
                 + (ev.role["removal_effect"] if ev.role["removal_effect"]
                    else "No removal effect is written down for this ingredient.")
                 + " Taste and texture changes are predictions.")
    unknown = ("The amount of the substitute (the dataset line shown is another recipe's amount); "
               "whether the revised steps still read correctly (they are a plain word swap); "
               "hidden sources of an allergen; whether you will like the result.")
    return ["Uncertainty:",
            f"  Supported by the dataset: {supported}",
            f"  Inferred from similar recipes: {inferred}",
            f"  Predicted taste/texture: {predicted}",
            f"  Unknown or unverified: {unknown}"]


def compose_substitution(ev: SubstitutionEvidence, adapted: AdaptedRecipe | None,
                         chosen: Candidate | None, unenforced: Sequence[str] = (),
                         changes: Sequence[str] = (), notes: Sequence[str] = ()) -> str:
    o, t, p, role = ev.original, ev.target, ev.pools, ev.role
    c = ev.constraints
    lines = [*changes, *notes]
    lines.append(
        f'Substitution: replace {t["base"]} in "{o["title"]}" [{o["id"]}] ({o["n_steps"]} steps)')
    lines += [f"  original line {x['position'] + 1}: {x['line']}" for x in t["lines"]]
    lines.append("Hard filters applied to the evidence recipes: " + constraints_text(
        {**c, "include": []}, unenforced) + ". Nothing was relaxed.")
    lines.append(("Role of " + t["base"] + " (general cooking knowledge, not dataset evidence): "
                  + (_names(role["roles"]) if role["known"] else "not in the roles file")))
    lines.append(f"Dataset search: {fmt_int(p['n_related_with'])} related recipes with {t['base']}, "
                 f"{fmt_int(p['n_related_without'])} without; {fmt_int(p['n_without_allowed'])} of the "
                 f"latter obey the filters and have steps ({fmt_int(p['n_direct'])} same dish family, "
                 f"{fmt_int(p['n_indirect'])} related only). Similarity = overlap of ingredient names.")

    shown = ev.candidates
    if shown:
        lines.append("")
        lines.append("Substitutes considered:")
        for n, cand in enumerate(shown, 1):
            lines += _candidate_lines(n, cand)
    for r in ev.rejected:
        lines.append(f"Rejected: {r['name']} - {r['reason']}")

    if adapted is None or chosen is None:
        lines.append("")
        lines.append("Result: INSUFFICIENT EVIDENCE. " + (ev.note or
                     "No substitute has dataset evidence, so I did not build an adapted recipe."))
        lines.append("I did not build an adapted recipe, because I will not present a swap the "
                     "dataset does not support. Options above marked NO dataset evidence are "
                     "unverified cooking knowledge only.")
    else:
        lines.append("")
        lines.append(f"Chosen substitute: {chosen.name} - the best-supported option "
                     f"({LEVEL_TEXT[chosen.level]}). Ranking: direct evidence first, then more "
                     "same-dish recipes, then more recipes, then enrichment. Other options are "
                     "listed above.")
        lines.append("")
        lines.append(f'ADAPTED RECIPE (a separate copy of "{o["title"]}" [{o["id"]}]; '
                     "the original is unchanged in the database)")
        lines.append("Ingredients:")
        changed = {x["position"] for x in adapted.changed_lines}
        for i, text in enumerate(adapted.ingredient_lines):
            lines.append(f"  - {text}" +
                         ("   <- CHANGED" if i in changed else ""))
        lines.append("Instructions:")
        revised = {x["position"] for x in adapted.step_changes}
        for i, text in enumerate(adapted.steps):
            lines.append(f"  {i + 1}. {text}" +
                         ("   <- REVISED" if i in revised else ""))
        if not adapted.steps:
            lines.append("  (the original recipe has no instructions)")
        lines.append("Changes made:")
        for x in adapted.changed_lines:
            lines.append(f'  - ingredient line {x["position"] + 1}: "{x["original"]}" -> '
                         f'"{x["adapted"]}"')
        for x in adapted.step_changes:
            lines.append(
                f'  - step {x["position"] + 1}: was "{x["original"]}"')
        if not adapted.step_changes:
            lines.append(
                "  - no instruction step names the ingredient, so the steps are unchanged.")
        lines.append("")
        lines += uncertainty_block(ev, chosen, adapted)
        lines += [f"Warning: {w}" for w in adapted.warnings]

    for r in ev.residual_conflicts:
        lines.append(f"STILL CONFLICTS with your restrictions: line {r['position'] + 1} "
                     f"'{r['line']}' ({r['constraint']}). Only {t['base']} was replaced, so this "
                     "recipe does NOT yet satisfy them.")
    if c.get("exclude_allergens"):
        lines.append(ALLERGEN_DISCLAIMER)
    lines.append(SAFETY_NOTE)
    return "\n".join(lines)
