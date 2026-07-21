"""Tests for cut validity -- does the statically-decided core transfer when frozen?"""

from strata.ir import Class, cut, unclassifiable_fraction
from strata.validity import (
    DEFAULT_TARGETS,
    STRUCTURAL_SHIFT,
    adapter_units_are_environment_specific,
    cut_validity,
    frozen_core_transfers,
    random_cut_validity,
    split_aware_skill,
)


def test_decided_cut_is_fully_valid_across_held_out_sites():
    rep = cut_validity()
    # The frozen decided-core, with only the adapter discovered, transfers to both
    # held-out sites.
    assert rep.decided_valid == 1.0
    assert all(r.transfers for r in rep.targets)


def test_random_cut_is_not_valid():
    # Same-size random cut of units does not transfer -- so the decided cut's
    # validity is doing real work (the P0 gate: beat the random cut).
    assert random_cut_validity("eICU", 3) == 0.0


def test_frozen_core_transfers_to_eicu():
    r = frozen_core_transfers("eICU", 3)
    assert r.transfers and r.count == 3


def test_every_adapter_unit_is_environment_specific():
    confirmed = adapter_units_are_environment_specific("eICU", 3)
    assert confirmed  # non-empty
    assert all(broke for _, broke in confirmed)


# --- Negative control: a structural shift the metric must be able to fail on ---

def test_frozen_core_undercounts_on_structural_shift():
    site, truth = STRUCTURAL_SHIFT
    r = frozen_core_transfers(site, truth)
    assert not r.transfers
    assert r.count == 2  # single-DX core misses the split-out (resolved) table


def test_validity_drops_below_one_with_structural_shift():
    rep = cut_validity(DEFAULT_TARGETS + (STRUCTURAL_SHIFT,))
    # 2 of 3 sites transfer -> the metric is falsifiable, not vacuously 100%.
    assert rep.decided_valid == 2 / 3


def test_split_aware_author_flags_the_structural_step():
    units = {u.step.id: u.cls for u in cut(split_aware_skill())}
    assert units["pick_dx"] is Class.UNCLASSIFIABLE
    assert unclassifiable_fraction(cut(split_aware_skill())) == 1 / 8
