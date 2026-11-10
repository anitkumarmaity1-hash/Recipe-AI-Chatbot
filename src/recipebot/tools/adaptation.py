"""Adapted recipe builder and validator, Task 3 (Step 12). Deterministic: no LLM.

Input:  a SubstitutionEvidence (Step 11) = the original recipe plus ranked substitutes
        with cited recipe ids.
Output: an AdaptedRecipe = a SEPARATE copy of the recipe in which
          * every ingredient line that contains the replaced ingredient is replaced by the
            substitute (the amount is NOT invented: the line says it is unverified, and a real
            dataset line of another recipe is kept in changed_lines for reference),
          * every instruction step that names the replaced ingredient is revised by a plain
            word swap,
          * every other line and step is copied word for word.
The original recipe is never touched.

validate_adaptation() re-checks the finished copy independently (see its docstring). If it
finds a problem, the agent withholds the answer instead of showing a wrong recipe.
Nothing here claims a recipe is safe for an allergy.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from recipebot import config
from recipebot.normalization.allergens import AllergenMatcher
from recipebot.normalization.steps import split_steps
from recipebot.retrieval.masks import Constraints
from recipebot.tools.substitution import Candidate, SubstitutionEvidence

AMOUNT_NOTE = "amount not verified from the dataset"


# ----------------------------------------------------------------------
# Small text helpers
# ----------------------------------------------------------------------
def form_pattern(words: Iterable[str]) -> re.Pattern[str]:
    """Whole-word, case-insensitive pattern for any of the words (optional plural -s/-es).

    'egg' matches 'egg' and 'Eggs' but not 'eggplant' or 'egg-free'. Longest words first,
    so 'unsalted butter' wins over 'butter'.
    """
    cleaned = sorted({w.strip().lower().replace("_", " ")
                      for w in words if w and w.strip()}, key=len, reverse=True)
    if not cleaned:
        return re.compile(r"(?!x)x")            # matches nothing
    alt = "|".join(r"\s+".join(re.escape(part) for part in w.split())
                   for w in cleaned)
    return re.compile(rf"(?<![A-Za-z-])(?:{alt})(?:e?s)?(?![A-Za-z]|-[A-Za-z])", re.I)


def _swap(text: str, pattern: re.Pattern[str], name: str) -> str:
    """Replace every match by `name`, keeping a capital letter at the start of a match."""
    def one(match: re.Match[str]) -> str:
        return name[:1].upper() + name[1:] if match.group(0)[:1].isupper() else name
    return pattern.sub(one, text)


def _without_name(text: str, name: str) -> str:
    """Remove the substitute's own name, so a substitute called 'egg replacer' is not 'egg'."""
    return re.sub(re.escape(name), " ", text, flags=re.I)


# ----------------------------------------------------------------------
# Result object
# ----------------------------------------------------------------------
@dataclass
class AdaptedRecipe:
    original_id: str
    original_title: str
    ingredient: str                    # base name of the replaced ingredient
    substitute: str
    level: str                         # evidence level of the substitute: direct | indirect
    # complete adapted list (same length as the original)
    ingredient_lines: list[str]
    # {position, original, adapted, reference_id, reference_line}
    changed_lines: list[dict[str, Any]]
    steps: list[str]                   # complete adapted steps
    step_changes: list[dict[str, Any]]  # {position, original, revised}
    original_steps: list[str]
    supporting_ids: list[str]          # recipes cited for the substitute
    # unchanged lines that still mention the ingredient
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# Choosing and building
# ----------------------------------------------------------------------
def choose_candidate(evidence: SubstitutionEvidence,
                     min_support: int = config.SUB_ADAPT_MIN_SUPPORT) -> Candidate | None:
    """The best-supported substitute that is strong enough to build a recipe from, else None.

    Strong enough = level "direct" (same dish family), or level "indirect" with at least
    `min_support` recipes. A candidate with level "none" (cooking knowledge only) is never
    chosen. Weaker evidence is still listed in the answer, but no adapted recipe is built.
    The Step 11 order is direct first, then indirect, so the first match is the best one.
    """
    if evidence.status != "ok":
        return None
    for cand in evidence.candidates:
        if not cand.evidence:
            continue
        if cand.level == "direct" or (cand.level == "indirect" and cand.n_support >= min_support):
            return cand
    return None


def _line_is_clean(text: str, forms: Sequence[str], constraints: Constraints,
                   matcher: AllergenMatcher | None) -> bool:
    """True if a text mentions neither the replaced ingredient, an excluded ingredient nor an excluded allergen."""
    if form_pattern(forms).search(text):
        return False
    if constraints.exclude and form_pattern(constraints.exclude).search(text):
        return False
    if constraints.exclude_allergens:
        # Fail closed: missing allergen taxonomy must never make an evidence line look safe.
        if matcher is None:
            return False
        return not any(matcher.matches(text, a) for a in constraints.exclude_allergens)
    return True


def adapt(evidence: SubstitutionEvidence, candidate: Candidate, constraints: Constraints | None = None,
          matcher: AllergenMatcher | None = None) -> AdaptedRecipe:
    """Build the adapted copy. Pure function of its inputs (same input, same output)."""
    constraints = constraints or Constraints()
    original = evidence.original
    name = candidate.name
    forms = evidence.target["forms"]
    pattern = form_pattern(forms)
    target_positions = {t["position"] for t in evidence.target["lines"]}

    # a real dataset line for the substitute, shown as a reference for the amount
    reference = next(((ev.id, line) for ev in candidate.evidence for line in ev.lines
                      if _line_is_clean(line, forms, constraints, matcher)), None)

    lines = list(original["ingredient_lines"])
    changed: list[dict[str, Any]] = []
    for position in sorted(target_positions):
        if position >= len(lines):
            continue
        # the list line stays clean; the reference amount is kept beside it (reference_id/line)
        new = f"{name} ({AMOUNT_NOTE})"
        changed.append({"position": position, "original": lines[position], "adapted": new,
                        "reference_id": reference[0] if reference else None,
                        "reference_line": reference[1] if reference else None})
        lines[position] = new

    original_steps = split_steps(original["instructions"])
    steps, step_changes = [], []
    for position, step in enumerate(original_steps):
        revised = _swap(step, pattern, name)
        if revised != step:
            step_changes.append(
                {"position": position, "original": step, "revised": revised})
        steps.append(revised)

    warnings = [f"ingredient line {i + 1} still mentions {evidence.target['base']}: '{line}'"
                for i, line in enumerate(lines)
                if i not in target_positions and pattern.search(line)]
    return AdaptedRecipe(
        original_id=original["id"], original_title=original["title"],
        ingredient=evidence.target["base"], substitute=name, level=candidate.level,
        ingredient_lines=lines, changed_lines=changed, steps=steps, step_changes=step_changes,
        original_steps=original_steps, supporting_ids=[
            ev.id for ev in candidate.evidence],
        warnings=warnings)


# ----------------------------------------------------------------------
# The validator
# ----------------------------------------------------------------------
def validate_adaptation(adapted: AdaptedRecipe, evidence: SubstitutionEvidence,
                        constraints: Constraints | None = None,
                        matcher: AllergenMatcher | None = None) -> list[str]:
    """Independent checks on the finished copy. An empty list means it is consistent.

    1. The copy has the same number of ingredient lines as the original, and every line that
       is not listed as changed is identical to the original line.
    2. Exactly the lines that contain the replaced ingredient were changed.
    3. No ingredient line or instruction step still names the replaced ingredient (the
       substitute's own name is ignored).
    4. EVERY ingredient line and instruction step is checked against every hard ingredient and
       allergen exclusion. This is intentionally stricter than checking only replacement lines:
       a dairy-free adaptation must not leave butter or Parmesan elsewhere in the recipe.
    5. The candidate name itself is checked against the hard exclusions, so an allergen-derived
       substitute such as egg white cannot be selected for an egg-free adaptation.
    6. The substitute is one of the evidence candidates with real dataset evidence, is in the
       dataset vocabulary and is not the replaced ingredient.
    7. Every supporting id is one of the recipes cited for that substitute.
    8. The step count is unchanged.

    Any pre-existing hard-constraint conflict in the original recipe prevents an adapted recipe
    from being returned. The caller may explain the conflicting line and ask the user whether
    they want to remove or replace that additional ingredient too.
    """
    constraints = constraints or Constraints()
    original = evidence.original
    problems: list[str] = []
    forms = evidence.target["forms"]
    pattern = form_pattern(forms)
    name = adapted.substitute

    lines, source = adapted.ingredient_lines, original["ingredient_lines"]
    changed_at = {c["position"] for c in adapted.changed_lines}
    expected = {t["position"] for t in evidence.target["lines"]}
    if len(lines) != len(source):
        problems.append(
            f"adapted recipe has {len(lines)} ingredient lines, the original has {len(source)}")
    else:
        for i, (new, old) in enumerate(zip(lines, source)):
            if i not in changed_at and new != old:
                problems.append(
                    f"ingredient line {i + 1} differs from the original but is not listed as changed")
    if changed_at != expected:
        problems.append(
            f"changed lines {sorted(changed_at)} differ from the lines that contain "
            f"{evidence.target['base']}: {sorted(expected)}")

    excluded_pattern = form_pattern(constraints.exclude)
    if constraints.exclude_allergens and matcher is None:
        problems.append(
            "an allergen matcher is required to validate every adapted ingredient line and instruction")

    # Check the COMPLETE adapted ingredient list, not only the lines that were changed.
    for i, text in enumerate(lines):
        if pattern.search(_without_name(text, name)):
            line_kind = "changed line" if i in changed_at else "ingredient line"
            problems.append(
                f"{line_kind} {i + 1} still names {adapted.ingredient}")
        if excluded_pattern.search(text):
            problems.append(
                f"ingredient line {i + 1} contains an excluded ingredient")
        if matcher is not None:
            for allergen in constraints.exclude_allergens:
                terms = matcher.matches(text, allergen)
                if terms:
                    problems.append(
                        f"ingredient line {i + 1} contains {allergen} (excluded allergen; '{terms[0]}')")

    # Also check the complete instructions: removing a listed ingredient is not enough if a
    # preparation step still tells the user to add it or another excluded item.
    for i, step in enumerate(adapted.steps):
        if pattern.search(_without_name(step, name)):
            problems.append(f"step {i + 1} still names {adapted.ingredient}")
        if excluded_pattern.search(step):
            problems.append(f"step {i + 1} mentions an excluded ingredient")
        if matcher is not None:
            for allergen in constraints.exclude_allergens:
                terms = matcher.matches(step, allergen)
                if terms:
                    problems.append(
                        f"step {i + 1} mentions excluded allergen {allergen} ('{terms[0]}')")
    if len(adapted.steps) != len(split_steps(original["instructions"])):
        problems.append("the number of steps changed")

    # Check the proposed substitute name directly, independently of how it appears in a line.
    if excluded_pattern.search(name):
        problems.append(f"substitute '{name}' is an excluded ingredient")
    if constraints.exclude_allergens and matcher is not None:
        for allergen in constraints.exclude_allergens:
            terms = matcher.matches(name, allergen)
            if terms:
                problems.append(
                    f"substitute '{name}' belongs to excluded allergen {allergen} ('{terms[0]}')")

    cand = next((c for c in evidence.candidates if c.name == name), None)
    if cand is None:
        problems.append(f"substitute '{name}' is not an evidence candidate")
    else:
        if cand.level not in ("direct", "indirect") or not cand.evidence:
            problems.append(
                f"substitute '{name}' has no dataset evidence (level {cand.level})")
        if not cand.in_vocabulary:
            problems.append(
                f"substitute '{name}' is not an ingredient in the dataset")
        cited = {ev.id for ev in cand.evidence}
        for rid in adapted.supporting_ids:
            if rid not in cited:
                problems.append(
                    f"supporting id {rid} is not cited for '{name}'")
    if name in set(forms) | {evidence.target["base"]}:
        problems.append("the substitute is the ingredient being replaced")
    return problems
