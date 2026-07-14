"""Compile the frozen procedure core + a typed adapter into executable SQL.

The core supplies the *shape* of the query -- the join discipline, the
dedup-then-count-distinct, the sanity bound. The adapter fills every typed hole:
table names, the patient key, the code column, the resolved codes, and the
dialect-specific time-window predicate. Swapping adapters re-targets the skill to
a new site without touching the core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from strata.adapters import Adapter
from strata.ir import Skill


@dataclass(frozen=True)
class CompiledSQL:
    main_sql: str
    params: List[str]         # parameter values for the codes IN (...) clause
    bound_sql: str            # denominator for the sanity check
    site: str


def compile_sql(skill: Skill, adapter: Adapter, condition: str, n_days: int) -> CompiledSQL:
    """Compose ``skill`` (frozen core) with ``adapter`` for one task instance."""
    key = adapter["PATIENT_KEY"]
    dx_table = adapter["DX_TABLE"]
    adm_table = adapter["ADM_TABLE"]
    code_col = adapter["CODE_COL"]
    codes = adapter.resolve(condition)

    placeholders = ", ".join("?" for _ in codes) or "NULL"
    within = adapter.within_predicate("dx", "adm", n_days)

    # CORE discipline: join on the patient key, filter within the window,
    # dedup by patient (COUNT DISTINCT), all environment-agnostic.
    main_sql = (
        f"SELECT COUNT(DISTINCT dx.{key}) AS n\n"
        f"FROM {dx_table} dx\n"
        f"JOIN {adm_table} adm ON dx.{key} = adm.{key}\n"
        f"WHERE dx.{code_col} IN ({placeholders})\n"
        f"  AND {within}"
    )

    # CORE sanity bound: distinct admitted patients.
    bound_sql = f"SELECT COUNT(DISTINCT {key}) AS bound FROM {adm_table}"

    return CompiledSQL(main_sql=main_sql, params=codes, bound_sql=bound_sql, site=adapter.name)
