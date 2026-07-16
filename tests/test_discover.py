"""Tests for instance discovery and the interface/instance slot kinds."""

from strata import db
from strata.discover import VOCAB_CANDIDATES, discover
from strata.ir import COHORT_COUNT_SKILL


def _discover(site):
    conn = db.connect(site)
    try:
        return discover(conn, site)
    finally:
        conn.close()


def test_discovers_mimic_adapter_from_schema_alone():
    rep = _discover("MIMIC-III")
    assert rep.success
    assert rep.bindings["DX_TABLE"] == "diagnoses_icd"
    assert rep.bindings["ADM_TABLE"] == "admissions"
    assert rep.bindings["PATIENT_KEY"] == "subject_id"
    assert rep.bindings["TIME_EXPR"] == "charttime"
    assert rep.time_unit == "timestamp"
    assert rep.count == 5  # ground truth, recovered without a hand-written adapter


def test_discovers_eicu_adapter_including_offset_encoding():
    rep = _discover("eICU")
    assert rep.success
    assert rep.bindings["DX_TABLE"] == "diagnosis"
    assert rep.bindings["PATIENT_KEY"] == "patienthealthsystemstayid"
    assert rep.bindings["TIME_EXPR"] == "diagnosisoffset"
    # The genuinely different time convention is discovered, not hand-set.
    assert rep.time_unit == "offset_minutes"
    assert rep.count == 3


def test_discovery_cost_is_bounded_and_small():
    # At most one execution per (time-impl, vocab-candidate) combination.
    max_probes = len(("timestamp", "offset_minutes")) * len(VOCAB_CANDIDATES["sepsis"])
    for site in ("MIMIC-III", "eICU"):
        rep = _discover(site)
        assert 1 <= rep.executions <= max_probes


def test_slot_kinds_mark_implementation_slots():
    kinds = {s.name: s.kind for s in COHORT_COUNT_SKILL.slots}
    # WITHIN (dialect predicate) and VOCAB are typed-implementation slots;
    # identifiers are plain constants.
    assert kinds["WITHIN"] == "implementation"
    assert kinds["VOCAB"] == "implementation"
    assert kinds["DX_TABLE"] == "constant"
    assert kinds["PATIENT_KEY"] == "constant"
