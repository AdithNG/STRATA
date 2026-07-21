"""Tests for cut validity -- does the statically-decided core transfer when frozen?"""

from strata.validity import (
    adapter_units_are_environment_specific,
    cut_validity,
    frozen_core_transfers,
    random_cut_validity,
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
