"""Adaptation-cost model and transfer strategies (the headline STRATA metric).

Compares what it costs to move a skill to a new environment under four strategies
(Section 5 of the proposal):

* ``from_scratch``   -- full optimization: re-fit every unit at the new site.
* ``whole_skill``    -- transfer the monolith and rewrite the whole skill.
* ``strata``         -- freeze the decidable core; re-fit only the typed adapter.
* ``random_cut``     -- freeze a random equal-size bucket of units instead of the
                        decidable core (the baseline that proves the *decidable*
                        cut matters).

Cost is a transparent, tunable proxy for optimizer edits: re-fitting one unit
costs ``CORE_WEIGHT`` for a core-discipline step (you must re-derive and re-verify
control flow -- the expensive, error-prone part) and ``ADAPTER_WEIGHT`` for a
convention binding (mechanical: plug in a typed constant). This is *not* LLM token
cost yet; wiring a real optimizer in is the next step. The qualitative result
(strata << from_scratch; random cut is cheap but wrong) is robust to the weights.

Correctness is not asserted here -- callers execute the resulting adapter against
the target database (see ``bench.py``) and observe it. STRATA and the two full
re-fits end with a fully correct adapter; the random cut, because it freezes whole
units without the typed op/hole separation, strands stale constants and fails.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

from strata.adapters import Adapter
from strata.ir import Class, Skill, cut

# Modeling assumptions (tunable). See module docstring.
CORE_WEIGHT = 3      # cost to re-derive + re-verify one control-flow discipline
ADAPTER_WEIGHT = 1   # cost to bind one convention (mechanical)

STRATEGIES = ("from_scratch", "whole_skill", "strata", "random_cut")


@dataclass(frozen=True)
class AdaptationPlan:
    strategy: str
    frozen_ids: List[str]
    refit_ids: List[str]
    edit_cost: int
    effective_adapter: Adapter  # the adapter that would actually be deployed
    note: str


def _unit_weight(cls: Class) -> int:
    return CORE_WEIGHT if cls is Class.CORE else ADAPTER_WEIGHT


def _mixed_adapter(skill: Skill, source: Adapter, target: Adapter, frozen_ids) -> Adapter:
    """A random-cut adapter: frozen units strand the *source* site's constants.

    Freezing a whole unit (rather than a typed core op with adapter-bound holes)
    carries over every environment constant that unit references. On a new site
    those constants are wrong -- this is exactly the negative transfer STRATA's
    typed cut avoids.
    """
    frozen = set(frozen_ids)
    steps = {s.id: s for s in skill.steps}
    bindings = dict(target.bindings)
    for uid in frozen:
        for slot in steps[uid].value_slots:
            bindings[slot] = source.bindings[slot]  # stranded old constant

    vocab_step = next((s.id for s in skill.steps if "VOCAB" in s.value_slots), None)
    within_step = next((s.id for s in skill.steps if "WITHIN" in s.value_slots), None)
    vocab = source.vocab_map if vocab_step in frozen else target.vocab_map
    time_unit = source.time_unit if within_step in frozen else target.time_unit

    return Adapter(
        name=f"{target.name}~random-cut",
        bindings=bindings,
        vocab_map=vocab,
        time_unit=time_unit,
    )


def plan_adaptation(
    skill: Skill,
    source: Adapter,
    target: Adapter,
    strategy: str,
    seed: Optional[int] = None,
) -> AdaptationPlan:
    """Plan how ``strategy`` moves ``skill`` from ``source`` to ``target``."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")

    units = cut(skill)
    core_ids = [u.step.id for u in units if u.cls is Class.CORE]
    adapter_ids = [u.step.id for u in units if u.cls is Class.ADAPTER]
    cls_of = {u.step.id: u.cls for u in units}

    if strategy in ("from_scratch", "whole_skill"):
        frozen, refit = [], [u.step.id for u in units]
        eff = target
        note = (
            "re-optimizes the whole skill at the new site"
            + ("; risks negative transfer from the old conventions" if strategy == "whole_skill"
               else "")
        )
    elif strategy == "strata":
        # Freeze the decidable core; re-fit only the typed adapter. The core ops
        # are frozen but their holes are filled fresh from the target adapter, so
        # every binding is correct -- that is what the typed cut buys.
        frozen, refit = list(core_ids), list(adapter_ids)
        eff = target
        note = "freezes the decidable core; re-fits only the typed adapter"
    else:  # random_cut
        rng = random.Random(seed)
        k = len(core_ids)  # equal-size bucket
        frozen = sorted(rng.sample([u.step.id for u in units], k))
        refit = [u.step.id for u in units if u.step.id not in set(frozen)]
        eff = _mixed_adapter(skill, source, target, frozen)
        note = f"freezes {k} random units (seed={seed}); no typed op/hole separation"

    edit_cost = sum(_unit_weight(cls_of[i]) for i in refit)
    return AdaptationPlan(strategy, sorted(frozen), sorted(refit), edit_cost, eff, note)
