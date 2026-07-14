"""STRATA: a LangGraph agent that splits a skill into a frozen, environment-agnostic
procedure core and a per-environment typed convention adapter.

See the research proposal in TSAGENT_EVOLVE_SKILLS.md. This package is a small,
runnable reference implementation of the mechanism described there, demonstrated on
the Appendix A worked example (cross-site clinical SQL, MIMIC-III -> eICU).
"""

from strata.ir import Skill, Step, Slot, Unit, cut, COHORT_COUNT_SKILL
from strata.adapters import Adapter, MIMIC_III, EICU, ADAPTERS
from strata.compiler import compile_sql
from strata.verifier import verify

__all__ = [
    "Skill",
    "Step",
    "Slot",
    "Unit",
    "cut",
    "COHORT_COUNT_SKILL",
    "Adapter",
    "MIMIC_III",
    "EICU",
    "ADAPTERS",
    "compile_sql",
    "verify",
]
