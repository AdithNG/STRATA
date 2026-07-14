"""Tests for frozen-core transfer, execution correctness, and zero interference."""

import copy

from strata.adapters import EICU, MIMIC_III
from strata.graph import build_agent
from strata.ir import COHORT_COUNT_SKILL, Class, cut

QUESTION = "How many distinct patients were diagnosed with sepsis within 7 days of admission?"


def test_mimic_count_correct_and_deduped():
    agent = build_agent()
    state = agent.invoke({"question": QUESTION, "site": "MIMIC-III"})
    # Ground truth: subjects {1,2,3,4,5} = 5 distinct, despite 8 diagnosis rows.
    assert state["result"].count == 5
    assert state["result"].ok
    assert "5 distinct patients" in state["answer"]


def test_eicu_count_correct_and_deduped():
    agent = build_agent()
    state = agent.invoke({"question": QUESTION, "site": "eICU"})
    # Ground truth: patients {1001,1002,1003} = 3 distinct; 1004 is outside window.
    assert state["result"].count == 3
    assert state["result"].ok


def test_parse_extracts_condition_and_window():
    agent = build_agent()
    state = agent.invoke(
        {"question": "distinct patients with pneumonia within 3 days of admission?",
         "site": "MIMIC-III"}
    )
    assert state["condition"] == "pneumonia"
    assert state["n_days"] == 3


def test_transfer_reuses_frozen_core():
    # Both sites are served by the same skill IR / same cut. Only the adapter
    # bound by the graph differs.
    units = cut(COHORT_COUNT_SKILL)
    core_ids = {u.step.id for u in units if u.cls is Class.CORE}
    assert core_ids == {"join", "filter_window", "dedup", "count", "sanity"}


def test_zero_backward_interference():
    # Snapshot MIMIC-III's adapter, run eICU through the agent, confirm the
    # MIMIC-III adapter (its covered pair) is byte-for-byte untouched.
    before = copy.deepcopy(MIMIC_III.bindings)
    agent = build_agent()
    agent.invoke({"question": QUESTION, "site": "eICU"})
    assert MIMIC_III.bindings == before
    # And MIMIC-III still answers exactly as before.
    state = agent.invoke({"question": QUESTION, "site": "MIMIC-III"})
    assert state["result"].count == 5


def test_eicu_time_convention_is_offset_not_timestamp():
    # The genuinely different convention (minutes offset vs timestamp) lives
    # entirely in the adapter's WITHIN predicate; the core filter is unchanged.
    pred = EICU.within_predicate("dx", "adm", 7)
    assert "diagnosisoffset BETWEEN 0 AND 10080" in pred
    pred_m = MIMIC_III.within_predicate("dx", "adm", 7)
    assert "datetime" in pred_m and "+7 days" in pred_m
