"""Execution verifier: run the compiled SQL and enforce the core's sanity check.

This is the domain's automatic verifier from the proposal. The core discipline
carries an assertion -- distinct-patient count must not exceed the number of
admitted patients -- and the verifier enforces it against the live database. A
from-scratch attempt that forgets to deduplicate inflates the count and fails
here; the frozen core cannot regress this because the discipline is never re-fit.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from strata.compiler import CompiledSQL


@dataclass(frozen=True)
class Result:
    count: int
    bound: int
    ok: bool
    message: str


def verify(conn: sqlite3.Connection, compiled: CompiledSQL) -> Result:
    cur = conn.cursor()
    cur.execute(compiled.main_sql, compiled.params)
    count = cur.fetchone()[0] or 0
    cur.execute(compiled.bound_sql)
    bound = cur.fetchone()[0] or 0

    ok = count <= bound
    if ok:
        msg = f"OK: {count} distinct patients <= {bound} admitted patients"
    else:
        msg = (
            f"SANITY VIOLATION: {count} distinct patients > {bound} admitted "
            f"patients (double-counting -- dedup discipline broken)"
        )
    return Result(count=count, bound=bound, ok=ok, message=msg)
