"""Tests for the decidable procedure/convention cut."""

from strata.ir import (
    COHORT_COUNT_SKILL,
    Class,
    Skill,
    Step,
    classify,
    core_mass,
    cut,
    unclassifiable_fraction,
)


def _by_id(units):
    return {u.step.id: u for u in units}


def test_cohort_cut_matches_appendix_a():
    units = _by_id(cut(COHORT_COUNT_SKILL))
    # Binding steps -> adapter.
    assert units["resolve_codes"].cls is Class.ADAPTER
    assert units["pick_dx"].cls is Class.ADAPTER
    assert units["pick_adm"].cls is Class.ADAPTER
    # Procedure-algebra steps -> core, even when they reference slot holes.
    assert units["join"].cls is Class.CORE
    assert units["filter_window"].cls is Class.CORE
    assert units["dedup"].cls is Class.CORE
    assert units["count"].cls is Class.CORE
    assert units["sanity"].cls is Class.CORE


def test_core_steps_may_reference_slots_but_stay_core():
    units = _by_id(cut(COHORT_COUNT_SKILL))
    join = units["join"]
    assert join.cls is Class.CORE
    assert "PATIENT_KEY" in join.step.value_slots  # references a slot as a hole


def test_core_mass_is_five_of_eight():
    units = cut(COHORT_COUNT_SKILL)
    assert abs(core_mass(units) - 5 / 8) < 1e-9
    assert unclassifiable_fraction(units) == 0.0


def test_structural_slot_dependency_is_unclassifiable():
    # A step whose control flow depends on an environment constant is the
    # decidability limit -- neither pure core nor pure adapter.
    step = Step(
        id="union_split",
        op="join",
        produces="joined",
        structural_slots=("SPLIT_TABLES",),
        note="some sites split diagnoses across two tables needing a UNION",
    )
    unit = classify(step)
    assert unit.cls is Class.UNCLASSIFIABLE


def test_cut_is_deterministic():
    assert cut(COHORT_COUNT_SKILL) == cut(COHORT_COUNT_SKILL)
