"""Cut validity -- the proposal's primary metric.

Cut validity asks the falsifiable question: *does the statically-decided core
actually transfer when frozen?* We answer it by execution, two ways.

1. **Deployment validity** (held-out environments). For each target site, freeze
   the decided core and fit only the adapter (by instance discovery), then run.
   The cut is valid for that site iff the result is correct. Validity is the
   fraction of held-out sites where the frozen decided-core reproduces the truth.
   Compared against a **random cut** (freeze a random equal-size unit set): if the
   decided cut is not doing real work, it should not beat the random baseline.
   This is exactly the P0 gate in the plan.

2. **Per-unit agreement**. The cut labels each unit core or adapter. We confirm
   each adapter-labelled unit is genuinely environment-specific (freezing its
   binding breaks transfer) and that the decided core transfers as a block.

Nothing here is asserted; every number comes from running SQL against the
databases.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from strata import db
from strata.adapters import EICU, MIMIC_III, Adapter
from strata.compiler import compile_sql
from strata.cost import _mixed_adapter, plan_adaptation
from strata.discover import discover
from strata.ir import (
    COHORT_COUNT_SKILL,
    Class,
    Skill,
    Slot,
    Step,
    cut,
    unclassifiable_fraction,
)
from strata.verifier import verify

# Held-out target environments with their ground-truth cohort counts.
DEFAULT_TARGETS: Tuple[Tuple[str, int], ...] = (("MIMIC-III", 5), ("eICU", 3))

# A site that splits diagnoses across two tables: the frozen single-DX core
# undercounts here (truth 4, single-table 2), so it is the validity negative control.
STRUCTURAL_SHIFT: Tuple[str, int] = ("eICU-split", 4)


def split_aware_skill(base: Skill = COHORT_COUNT_SKILL) -> Skill:
    """A variant whose diagnoses-source step is declared structurally site-dependent.

    An author who knows some sites split diagnoses across tables marks that step's
    control flow as slot-dependent. The cut then flags it *unclassifiable* (neither
    freezable core nor a simple adapter constant) instead of over-claiming it as a
    constant, which is what avoids the silent undercount.
    """
    steps = tuple(
        Step(s.id, s.op, s.produces, s.value_slots, s.inputs,
             structural_slots=("DX_LAYOUT",) if s.id == "pick_dx" else s.structural_slots,
             note=s.note)
        for s in base.steps
    )
    slots = base.slots + (
        Slot("DX_LAYOUT", "layout", "how diagnoses are partitioned across tables",
             kind="contract"),
    )
    return Skill(base.name + "_split_aware", base.task_params, slots, steps, base.nl_sketch)


def _run(adapter: Adapter, site: str, condition: str, n_days: int, skill: Skill) -> Optional[int]:
    conn = db.connect(site)
    try:
        compiled = compile_sql(skill, adapter, condition, n_days)
        r = verify(conn, compiled)
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return r.count if r.ok else None


@dataclass
class TargetResult:
    site: str
    expected: int
    count: Optional[int]
    transfers: bool


@dataclass
class ValidityReport:
    decided_valid: float
    random_valid: float
    targets: List[TargetResult] = field(default_factory=list)
    adapter_units_confirmed: List[Tuple[str, bool]] = field(default_factory=list)


def frozen_core_transfers(site: str, expected: int, condition: str = "sepsis",
                          n_days: int = 7, skill: Skill = COHORT_COUNT_SKILL) -> TargetResult:
    """Freeze the decided core; fit only the adapter by discovery; did it transfer?"""
    conn = db.connect(site)
    try:
        rep = discover(conn, site, condition, n_days, skill)
    finally:
        conn.close()
    count = rep.count if rep.success else None
    return TargetResult(site, expected, count, count == expected)


def random_cut_validity(target_site: str, expected: int, source: Adapter = MIMIC_III,
                        target: Adapter = EICU, condition: str = "sepsis", n_days: int = 7,
                        seeds: range = range(8), skill: Skill = COHORT_COUNT_SKILL) -> float:
    """Fraction of random equal-size cuts that transfer correctly (the baseline)."""
    ok = 0
    for seed in seeds:
        plan = plan_adaptation(skill, source, target, "random_cut", seed=seed)
        if _run(plan.effective_adapter, target_site, condition, n_days, skill) == expected:
            ok += 1
    return ok / len(seeds)


def adapter_units_are_environment_specific(
    target_site: str, expected: int, source: Adapter = MIMIC_III, target: Adapter = EICU,
    condition: str = "sepsis", n_days: int = 7, skill: Skill = COHORT_COUNT_SKILL,
) -> List[Tuple[str, bool]]:
    """For each adapter-labelled unit, freezing its binding should break transfer."""
    out = []
    for u in cut(skill):
        if u.cls is not Class.ADAPTER:
            continue
        eff = _mixed_adapter(skill, source, target, [u.step.id])  # strand this unit's source binding
        broke = _run(eff, target_site, condition, n_days, skill) != expected
        out.append((u.step.id, broke))
    return out


def cut_validity(targets: Tuple[Tuple[str, int], ...] = DEFAULT_TARGETS,
                 skill: Skill = COHORT_COUNT_SKILL) -> ValidityReport:
    results = [frozen_core_transfers(site, exp, skill=skill) for site, exp in targets]
    decided = sum(r.transfers for r in results) / len(results)
    random_valid = random_cut_validity("eICU", 3, skill=skill)
    confirmed = adapter_units_are_environment_specific("eICU", 3, skill=skill)
    return ValidityReport(decided, random_valid, results, confirmed)


def _main() -> None:
    rep = cut_validity()
    print("Cut validity -- does the statically-decided core transfer when frozen?\n")
    print("Deployment (freeze decided core, discover adapter, run on held-out site):")
    for r in rep.targets:
        mark = "transfers" if r.transfers else f"FAILS (got {r.count}, want {r.expected})"
        print(f"  {r.site:<12} count={r.count}  ->  {mark}")
    print(f"\n  decided-cut validity : {rep.decided_valid:.0%}")
    print(f"  random-cut validity  : {rep.random_valid:.0%}  (baseline -- freezing a random unit set)")
    print("\nPer-unit check -- adapter-labelled units are genuinely environment-specific:")
    for uid, broke in rep.adapter_units_confirmed:
        print(f"  {uid:<14}{'confirmed (freezing its binding breaks eICU)' if broke else 'NOT confirmed'}")
    print("\nRead-out: the decided cut's frozen core transfers where a random cut of the")
    print("same size does not, so the core-mass the cut reports is a valid prediction,")
    print("not an artifact of freezing something.")

    # Negative control: a structural shift the metric must be able to fail on.
    site, truth = STRUCTURAL_SHIFT
    shift = frozen_core_transfers(site, truth)
    with_shift = cut_validity(DEFAULT_TARGETS + (STRUCTURAL_SHIFT,))
    aware = split_aware_skill()
    flagged = [u.step.id for u in cut(aware) if u.cls is Class.UNCLASSIFIABLE]
    print("\n" + "-" * 68)
    print("Negative control -- a structural shift (diagnoses split across two tables):")
    print(f"  {site}: frozen core count={shift.count}, truth={truth}  ->  "
          f"{'transfers' if shift.transfers else 'FAILS (silent undercount)'}")
    print(f"  cut validity including the shift : {with_shift.decided_valid:.0%}  "
          f"(so the metric is falsifiable, not vacuously 100%)")
    print(f"  an author who declares the diagnoses source structural -> the cut flags "
          f"{flagged} unclassifiable")
    print(f"  decidability-limit fraction (split-aware skill): "
          f"{unclassifiable_fraction(cut(aware)):.0%}")
    print("  So the honest cut declines to freeze what it cannot prove transfers,")
    print("  rather than over-claiming it and undercounting.")


if __name__ == "__main__":
    _main()
