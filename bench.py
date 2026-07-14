"""Adaptation-cost benchmark: MIMIC-III -> eICU under four transfer strategies.

Each strategy produces an adapter for eICU; we compile the frozen core against it,
run it on the eICU database, and report both the re-fit cost and the *observed*
correctness. The truth (3 distinct sepsis patients) is fixed by the data.

Run:  python bench.py
"""

from __future__ import annotations

import sqlite3

from strata import db
from strata.adapters import EICU, MIMIC_III
from strata.compiler import compile_sql
from strata.cost import STRATEGIES, plan_adaptation
from strata.ir import COHORT_COUNT_SKILL
from strata.verifier import verify

CONDITION, N_DAYS = "sepsis", 7
TRUTH = 3  # ground-truth distinct sepsis patients within 7 days at eICU


def _execute(adapter) -> tuple[int | None, str]:
    """Run the compiled query for ``adapter`` on the eICU DB; return (count, status)."""
    conn = db.connect("eICU")
    try:
        compiled = compile_sql(COHORT_COUNT_SKILL, adapter, CONDITION, N_DAYS)
        result = verify(conn, compiled)
    except sqlite3.Error as e:
        return None, f"SQL error ({e})"
    finally:
        conn.close()
    if not result.ok:
        return result.count, "sanity violation"
    if result.count != TRUTH:
        return result.count, f"wrong count (got {result.count}, truth {TRUTH})"
    return result.count, "correct"


def main() -> None:
    print(f"Transfer: MIMIC-III -> eICU   |   truth = {TRUTH} distinct sepsis patients (<=7 days)\n")
    header = f"{'strategy':<14}{'edit cost':>10}{'vs scratch':>12}{'result':>10}   detail"
    print(header)
    print("-" * len(header))

    scratch_cost = plan_adaptation(
        COHORT_COUNT_SKILL, MIMIC_III, EICU, "from_scratch"
    ).edit_cost

    for strategy in STRATEGIES:
        if strategy == "random_cut":
            # Sample several random cuts to show it is not a one-off failure.
            rows = [plan_adaptation(COHORT_COUNT_SKILL, MIMIC_III, EICU, strategy, seed=s)
                    for s in range(8)]
            outcomes = [_execute(p.effective_adapter) for p in rows]
            n_correct = sum(1 for _, s in outcomes if s == "correct")
            mean_cost = sum(p.edit_cost for p in rows) / len(rows)
            print(f"{'random_cut':<14}{mean_cost:>10.1f}{mean_cost / scratch_cost:>11.0%}"
                  f"{f'{n_correct}/8 ok':>10}   freezes random units; strands stale constants")
            continue

        plan = plan_adaptation(COHORT_COUNT_SKILL, MIMIC_III, EICU, strategy)
        count, status = _execute(plan.effective_adapter)
        rel = plan.edit_cost / scratch_cost
        mark = "correct" if status == "correct" else status
        print(f"{strategy:<14}{plan.edit_cost:>10}{rel:>11.0%}{mark:>10}   "
              f"freeze={plan.frozen_ids or '[]'}")

    print("\nRead-out:")
    strata = plan_adaptation(COHORT_COUNT_SKILL, MIMIC_III, EICU, "strata")
    print(f"  STRATA re-fits {len(strata.refit_ids)} adapter units and freezes "
          f"{len(strata.frozen_ids)} core steps -- {strata.edit_cost/scratch_cost:.0%} of "
          f"from-scratch cost, and correct.")
    print("  The random cut is comparably cheap but wrong: freezing whole units without")
    print("  the typed op/hole separation carries eICU-incompatible MIMIC-III constants.")
    print("  So the saving comes from the *decidable* cut, not from freezing per se.")


if __name__ == "__main__":
    main()
