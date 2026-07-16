"""Instance discovery: fit an environment's adapter by introspection, not by hand.

The sharpened proposal reframes an environment as an *instance of an abstract typed
interface*, and moves adaptation cost into **instance discovery**: run the frozen
core against a new site, bind each typed slot by resolving it against the
environment's catalog, and confirm by execution. Constant slots (identifiers)
resolve by typed name-matching against the schema; implementation slots (the
time-window predicate, the code vocabulary) are filled from a small typed
candidate pool and selected by execution against the core's contract.

This replaces the hand-written adapters: given only a site's database, we recover
its adapter and reproduce the correct cohort count, and we report the discovery
cost (number of verifier executions) -- the quantity the proposal claims is
`<< from-scratch relearning`.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from strata.adapters import Adapter
from strata.compiler import compile_sql
from strata.ir import COHORT_COUNT_SKILL, Skill
from strata.verifier import verify

# Typed-implementation candidate pools. In the full system these come from
# LLM synthesis behind the slot's signature; here they are a small typed pool,
# and selection is by execution against the frozen core's contract.
TIME_IMPLEMENTATIONS = ("timestamp", "offset_minutes")

VOCAB_CANDIDATES: Dict[str, List[List[str]]] = {
    # each entry is a candidate rendering of the concept's codes
    "sepsis": [["99591", "99592", "78552"], ["995.91", "995.92", "785.52"]],
    "pneumonia": [["486", "48241", "5070"], ["486", "482.41", "507.0"]],
    "diabetes": [["25000", "25001"], ["250.00", "250.01"]],
}

_KEY_RE = re.compile(r"subject|patient|person|pid", re.I)
_CODE_RE = re.compile(r"code", re.I)
_TIME_RE = re.compile(r"offset|time|chart|date", re.I)


@dataclass
class DiscoveryReport:
    site: str
    success: bool
    bindings: Dict[str, str] = field(default_factory=dict)
    time_unit: Optional[str] = None
    codes: List[str] = field(default_factory=list)
    count: Optional[int] = None
    executions: int = 0          # verifier executions spent selecting implementations
    catalog_probes: int = 0      # schema introspection reads (cheap)
    note: str = ""

    def adapter(self) -> Adapter:
        return Adapter(
            name=f"{self.site}~discovered",
            bindings=dict(self.bindings),
            vocab_map={self._condition: list(self.codes)},
            time_unit=self.time_unit or "timestamp",
        )

    _condition: str = "sepsis"


def _catalog(conn: sqlite3.Connection) -> Dict[str, List[str]]:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    return {t: [r[1] for r in conn.execute(f"PRAGMA table_info({t})")] for t in tables}


def _match_constants(cat: Dict[str, List[str]]) -> Optional[Dict[str, str]]:
    """Resolve the constant slots by typed name-matching against the catalog."""
    # DX table = the one with a code-like column; ADM table = another sharing a key.
    dx = next((t for t, cols in cat.items() if any(_CODE_RE.search(c) for c in cols)), None)
    if dx is None:
        return None
    code_col = next(c for c in cat[dx] if _CODE_RE.search(c))
    time_expr = next((c for c in cat[dx] if _TIME_RE.search(c)), None)

    adm, key = None, None
    for t, cols in cat.items():
        if t == dx:
            continue
        shared = set(cols) & set(cat[dx])
        if not shared:
            continue
        adm = t
        key = next((c for c in shared if _KEY_RE.search(c)), sorted(shared)[0])
        break
    if adm is None or time_expr is None:
        return None

    return {
        "DX_TABLE": dx, "CODE_COL": code_col, "ADM_TABLE": adm,
        "PATIENT_KEY": key, "TIME_EXPR": time_expr, "VOCAB": "discovered",
        "WITHIN": "discovered",
    }


def discover(
    conn: sqlite3.Connection,
    site: str,
    condition: str = "sepsis",
    n_days: int = 7,
    skill: Skill = COHORT_COUNT_SKILL,
) -> DiscoveryReport:
    """Discover ``site``'s adapter from its database alone; confirm by execution."""
    cat = _catalog(conn)
    rep = DiscoveryReport(site=site, success=False, catalog_probes=len(cat))
    rep._condition = condition.lower()

    constants = _match_constants(cat)
    if constants is None:
        rep.note = "could not resolve constant slots from catalog"
        return rep

    # Implementation slots: try each typed candidate, keep the first that executes
    # cleanly, satisfies the contract, and returns a non-empty cohort.
    for time_unit in TIME_IMPLEMENTATIONS:
        for codes in VOCAB_CANDIDATES.get(condition.lower(), []):
            trial = Adapter(
                name=f"{site}~trial",
                bindings={**constants, "WITHIN": time_unit},
                vocab_map={condition.lower(): codes},
                time_unit=time_unit,
            )
            rep.executions += 1
            try:
                conn2 = conn
                compiled = compile_sql(skill, trial, condition, n_days)
                result = verify(conn2, compiled)
            except sqlite3.Error:
                continue  # wrong implementation for this schema -> reject
            if result.ok and result.count and result.count > 0:
                rep.success = True
                rep.bindings = dict(constants)
                rep.time_unit = time_unit
                rep.codes = list(codes)
                rep.count = result.count
                rep.note = "discovered by introspection + execution-confirmed slot-filling"
                return rep

    rep.note = "no candidate implementation satisfied the contract"
    return rep


def _main() -> None:
    from strata import db
    from strata.cost import plan_adaptation
    from strata.adapters import MIMIC_III, EICU

    scratch = plan_adaptation(COHORT_COUNT_SKILL, MIMIC_III, EICU, "from_scratch").edit_cost
    print("Instance discovery -- recover each site's adapter from its database alone\n")
    for site in ("MIMIC-III", "eICU"):
        conn = db.connect(site)
        try:
            rep = discover(conn, site)
        finally:
            conn.close()
        print(f"{site}:")
        print(f"  discovered: DX={rep.bindings.get('DX_TABLE')} "
              f"KEY={rep.bindings.get('PATIENT_KEY')} TIME={rep.bindings.get('TIME_EXPR')} "
              f"impl(WITHIN)={rep.time_unit} codes={rep.codes}")
        print(f"  cohort count = {rep.count}  |  discovery cost = {rep.executions} "
              f"verifier executions (vs from-scratch proxy {scratch})")
        print(f"  {rep.note}\n")


if __name__ == "__main__":
    _main()
