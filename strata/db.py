"""Build small, synthetic MIMIC-III- and eICU-shaped SQLite databases.

Real MIMIC-III / eICU are credentialed; this module stands up tiny fixtures with
the same *conventions* (table/column names, code vocabularies, and -- crucially --
the two different time encodings from Appendix A: absolute timestamps in MIMIC-III,
minutes-since-admission offsets in eICU). The data is deliberately seeded so that
patients have multiple diagnosis rows, which is exactly what makes the core's
dedup-then-count discipline load-bearing.

Note: real ``diagnoses_icd`` has no per-row timestamp; we add ``charttime`` to make
the time-window step exercisable, following the proposal's Appendix A model.
"""

from __future__ import annotations

import os
import sqlite3

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def build_mimic(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS admissions;
        DROP TABLE IF EXISTS diagnoses_icd;
        CREATE TABLE admissions (
            subject_id INTEGER,
            hadm_id    INTEGER,
            admittime  TEXT
        );
        CREATE TABLE diagnoses_icd (
            subject_id INTEGER,
            hadm_id    INTEGER,
            icd9_code  TEXT,
            charttime  TEXT
        );
        """
    )
    # 8 admitted patients.
    admits = [(i, 100 + i, "2130-01-01 10:00:00") for i in range(1, 9)]
    cur.executemany("INSERT INTO admissions VALUES (?, ?, ?)", admits)

    # Sepsis, within 7 days -- note the multiple rows per patient (dedup matters).
    dx = [
        # subject 1: three sepsis rows within window -> counts once
        (1, 101, "99591", "2130-01-02 08:00:00"),
        (1, 101, "99592", "2130-01-03 08:00:00"),
        (1, 101, "78552", "2130-01-04 08:00:00"),
        # subject 2: two sepsis rows within window -> counts once
        (2, 102, "99591", "2130-01-02 08:00:00"),
        (2, 102, "99591", "2130-01-05 08:00:00"),
        # subjects 3,4,5: one sepsis row each within window
        (3, 103, "99591", "2130-01-03 08:00:00"),
        (4, 104, "78552", "2130-01-06 08:00:00"),
        (5, 105, "99592", "2130-01-02 08:00:00"),
        # subject 6: sepsis row OUTSIDE the 7-day window -> excluded
        (6, 106, "99591", "2130-01-20 08:00:00"),
        # subjects 7,8: pneumonia (different condition)
        (7, 107, "486", "2130-01-02 08:00:00"),
        (8, 108, "5070", "2130-01-02 08:00:00"),
    ]
    cur.executemany("INSERT INTO diagnoses_icd VALUES (?, ?, ?, ?)", dx)
    conn.commit()
    # Ground truth for sepsis within 7 days: subjects {1,2,3,4,5} = 5 distinct.


def build_eicu(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS patient;
        DROP TABLE IF EXISTS diagnosis;
        CREATE TABLE patient (
            patienthealthsystemstayid INTEGER,
            uniquepid                 TEXT,
            hospitaladmitoffset       INTEGER
        );
        CREATE TABLE diagnosis (
            patienthealthsystemstayid INTEGER,
            icd9code                  TEXT,
            diagnosisoffset           INTEGER
        );
        """
    )
    # 6 admitted patients (a genuinely different database from MIMIC).
    patients = [(1000 + i, f"pid-{i}", 0) for i in range(1, 7)]
    cur.executemany("INSERT INTO patient VALUES (?, ?, ?)", patients)

    # diagnosisoffset is MINUTES since admission. 7-day window = 10080 minutes.
    dx = [
        # 1001: two sepsis rows within window -> counts once
        (1001, "995.91", 120),
        (1001, "995.92", 1440),
        # 1002: one sepsis row within window
        (1002, "785.52", 60),
        # 1003: one sepsis row within window
        (1003, "995.91", 5000),
        # 1004: sepsis row OUTSIDE the 7-day window (11000 > 10080) -> excluded
        (1004, "995.91", 11000),
        # 1005, 1006: pneumonia
        (1005, "486", 200),
        (1006, "507.0", 200),
    ]
    cur.executemany("INSERT INTO diagnosis VALUES (?, ?, ?)", dx)
    conn.commit()
    # Ground truth for sepsis within 7 days: patients {1001,1002,1003} = 3 distinct.


def build_eicu_split(conn: sqlite3.Connection) -> None:
    """An eICU-shaped site that SPLITS diagnoses across two tables.

    Some real sites separate active vs. resolved diagnoses. Getting all diagnoses
    then requires a UNION before the join -- a *structural* change to the
    procedure, not a renaming. This is the decidability-limit case: the single-DX
    frozen core cannot express it and silently undercounts, which is exactly what
    the cut-validity negative control is meant to catch.
    """
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS patient;
        DROP TABLE IF EXISTS diagnosis_active;
        DROP TABLE IF EXISTS diagnosis_resolved;
        CREATE TABLE patient (
            patienthealthsystemstayid INTEGER,
            uniquepid                 TEXT,
            hospitaladmitoffset       INTEGER
        );
        CREATE TABLE diagnosis_active (
            patienthealthsystemstayid INTEGER,
            icd9code                  TEXT,
            diagnosisoffset           INTEGER
        );
        CREATE TABLE diagnosis_resolved (
            patienthealthsystemstayid INTEGER,
            icd9code                  TEXT,
            diagnosisoffset           INTEGER
        );
        """
    )
    patients = [(2000 + i, f"pid-{i}", 0) for i in range(1, 7)]  # 6 admitted
    cur.executemany("INSERT INTO patient VALUES (?, ?, ?)", patients)

    # Window = 10080 minutes (7 days).
    active = [
        (2001, "995.91", 120),    # within
        (2002, "785.52", 60),     # within
        (2005, "995.91", 11000),  # OUTSIDE window -> excluded
    ]
    resolved = [
        (2003, "995.91", 200),    # within
        (2004, "995.92", 500),    # within
        (2001, "995.92", 1440),   # within, duplicate patient (already counted)
    ]
    cur.executemany("INSERT INTO diagnosis_active VALUES (?, ?, ?)", active)
    cur.executemany("INSERT INTO diagnosis_resolved VALUES (?, ?, ?)", resolved)
    conn.commit()
    # Truth (UNION of both tables, distinct, within window): {2001,2002,2003,2004} = 4.
    # Single-table core (diagnosis_active only): {2001,2002} = 2  -> undercount.


BUILDERS = {"MIMIC-III": build_mimic, "eICU": build_eicu, "eICU-split": build_eicu_split}


def connect(site: str, path: str | None = None) -> sqlite3.Connection:
    """Return a connection to a freshly built database for ``site``.

    ``path=None`` builds in memory (used by tests and the demo).
    """
    conn = sqlite3.connect(path or ":memory:")
    BUILDERS[site](conn)
    return conn


def build_files() -> None:
    """Materialize both databases as files under ``data/`` (optional convenience)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    for site in BUILDERS:
        fname = os.path.join(DATA_DIR, site.replace("-", "_").lower() + ".sqlite")
        if os.path.exists(fname):
            os.remove(fname)
        conn = sqlite3.connect(fname)
        BUILDERS[site](conn)
        conn.close()


if __name__ == "__main__":
    build_files()
    print(f"Built MIMIC-III and eICU databases under {DATA_DIR}")
