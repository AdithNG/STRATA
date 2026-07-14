"""Tests for the adaptation-cost model and transfer strategies."""

import sqlite3

from strata import db
from strata.adapters import EICU, MIMIC_III
from strata.compiler import compile_sql
from strata.cost import plan_adaptation
from strata.ir import COHORT_COUNT_SKILL

SKILL = COHORT_COUNT_SKILL
TRUTH = 3  # distinct sepsis patients within 7 days at eICU


def _run(adapter):
    """Execute the compiled query on eICU; return count or None on SQL error."""
    conn = db.connect("eICU")
    try:
        compiled = compile_sql(SKILL, adapter, "sepsis", 7)
        result = conn.execute(compiled.main_sql, compiled.params).fetchone()[0]
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return result


def test_strata_is_cheaper_than_from_scratch():
    strata = plan_adaptation(SKILL, MIMIC_III, EICU, "strata")
    scratch = plan_adaptation(SKILL, MIMIC_III, EICU, "from_scratch")
    assert strata.edit_cost < scratch.edit_cost


def test_strata_freezes_core_refits_adapter():
    strata = plan_adaptation(SKILL, MIMIC_III, EICU, "strata")
    assert set(strata.frozen_ids) == {"join", "filter_window", "dedup", "count", "sanity"}
    assert set(strata.refit_ids) == {"resolve_codes", "pick_dx", "pick_adm"}


def test_strata_deploys_full_target_adapter_and_is_correct():
    # Freezing the core does NOT strand constants: the effective adapter is the
    # full target, so execution is correct.
    strata = plan_adaptation(SKILL, MIMIC_III, EICU, "strata")
    assert strata.effective_adapter.bindings == EICU.bindings
    assert _run(strata.effective_adapter) == TRUTH


def test_from_scratch_is_correct():
    scratch = plan_adaptation(SKILL, MIMIC_III, EICU, "from_scratch")
    assert _run(scratch.effective_adapter) == TRUTH


def test_random_cut_strands_constants_and_fails():
    # Across seeds, the random cut carries MIMIC-III constants into eICU and never
    # reproduces the truth -- proving the *decidable* cut is what makes freezing safe.
    correct = 0
    for seed in range(8):
        plan = plan_adaptation(SKILL, MIMIC_III, EICU, "random_cut", seed=seed)
        if _run(plan.effective_adapter) == TRUTH:
            correct += 1
    assert correct == 0


def test_whole_skill_flags_negative_transfer():
    plan = plan_adaptation(SKILL, MIMIC_III, EICU, "whole_skill")
    assert "negative transfer" in plan.note
