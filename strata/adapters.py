"""Typed convention adapters -- the only thing that changes between sites.

An adapter binds every slot of the frozen core to concrete, environment-bound
values. Deploying the skill to environment *c* is ``core -> adapter_c``. Fitting a
new adapter never touches the core, so a covered environment's pair is untouched
(backward interference == 0 by construction).

The bindings here are illustrative but faithful to Appendix A: eICU encodes
diagnosis time as a minutes-since-admission *offset*, a genuinely different
convention that the adapter absorbs while the core "filter within a window"
operation is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Adapter:
    name: str
    bindings: Dict[str, str]        # slot name -> concrete symbol
    vocab_map: Dict[str, List[str]]  # condition -> resolved codes (the VOCAB binding)
    time_unit: str                  # "timestamp" | "offset_minutes" -- doc only

    def __getitem__(self, slot: str) -> str:
        return self.bindings[slot]

    def resolve(self, condition: str) -> List[str]:
        """The `resolve(condition, <VOCAB>)` binding for this site."""
        return self.vocab_map.get(condition.lower(), [])

    def within_predicate(self, dx: str, adm: str, n_days: int) -> str:
        """The dialect-specific `<WITHIN>(<TIME_EXPR>, N)` predicate.

        This is the adapter hole the core `filter` step references. The core op
        ("keep rows within a window") is identical across sites; only the time
        encoding differs, and it lives entirely here.
        """
        time_expr = self.bindings["TIME_EXPR"]
        if self.time_unit == "timestamp":
            # Absolute timestamps: charttime BETWEEN admittime AND admittime + N days.
            admit = f"{adm}.admittime"
            return (
                f"{dx}.{time_expr} BETWEEN {admit} "
                f"AND datetime({admit}, '+{int(n_days)} days')"
            )
        elif self.time_unit == "offset_minutes":
            # Minutes-since-admission offset: 0 <= offset <= N*24*60.
            return f"{dx}.{time_expr} BETWEEN 0 AND {int(n_days) * 24 * 60}"
        raise ValueError(f"unknown time_unit {self.time_unit!r}")


MIMIC_III = Adapter(
    name="MIMIC-III",
    bindings={
        "VOCAB": "ICD9",
        "DX_TABLE": "diagnoses_icd",
        "CODE_COL": "icd9_code",
        "ADM_TABLE": "admissions",
        "PATIENT_KEY": "subject_id",
        "TIME_EXPR": "charttime",
        "WITHIN": "charttime BETWEEN admittime AND admittime + N days",
    },
    vocab_map={
        "sepsis": ["99591", "99592", "78552"],
        "pneumonia": ["486", "48241", "5070"],
        "diabetes": ["25000", "25001"],
    },
    time_unit="timestamp",
)

EICU = Adapter(
    name="eICU",
    bindings={
        "VOCAB": "ICD(mixed,string)",
        "DX_TABLE": "diagnosis",
        "CODE_COL": "icd9code",
        "ADM_TABLE": "patient",
        "PATIENT_KEY": "patienthealthsystemstayid",
        "TIME_EXPR": "diagnosisoffset",
        "WITHIN": "diagnosisoffset BETWEEN 0 AND N*24*60",
    },
    vocab_map={
        "sepsis": ["995.91", "995.92", "785.52"],
        "pneumonia": ["486", "482.41", "507.0"],
        "diabetes": ["250.00", "250.01"],
    },
    time_unit="offset_minutes",
)

ADAPTERS = {a.name: a for a in (MIMIC_III, EICU)}
