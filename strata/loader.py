"""Load skills and adapters from JSON data files.

Skills live in ``skills/*.json`` and adapters in ``adapters/*.json`` at the repo
root. Adding a new site or task is a data file, not a code change -- the cut,
compiler, and graph are untouched. The parsed objects are exactly the same
``Skill`` / ``Adapter`` types defined in code, so everything downstream is
identical whether a skill came from a file or a literal.

The module-level ``SKILLS`` and ``ADAPTERS`` registries merge file-based
definitions over the hardcoded fallbacks in ``ir.py`` / ``adapters.py`` (files
win on a name clash), so the framework still works if the data files are absent.

This JSON shape is the contract for a skill dataset -- e.g. one produced per
data environment for the STRATA experiments.
"""

from __future__ import annotations

import json
import os
from typing import Dict

from strata.adapters import ADAPTERS as _FALLBACK_ADAPTERS
from strata.adapters import Adapter
from strata.ir import COHORT_COUNT_SKILL as _FALLBACK_SKILL
from strata.ir import Skill, Slot, Step

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(_ROOT, "skills")
ADAPTERS_DIR = os.path.join(_ROOT, "adapters")


def skill_from_dict(d: dict) -> Skill:
    slots = tuple(
        Slot(s["name"], s["type"], s.get("description", ""), kind=s.get("kind", "constant"))
        for s in d["slots"]
    )
    steps = tuple(
        Step(
            id=s["id"],
            op=s["op"],
            produces=s["produces"],
            value_slots=tuple(s.get("value_slots", [])),
            structural_slots=tuple(s.get("structural_slots", [])),
            note=s.get("note", ""),
        )
        for s in d["steps"]
    )
    return Skill(
        name=d["name"],
        task_params=tuple(d.get("task_params", [])),
        slots=slots,
        steps=steps,
        nl_sketch=d.get("nl_sketch", ""),
    )


def adapter_from_dict(d: dict) -> Adapter:
    return Adapter(
        name=d["name"],
        bindings=dict(d["bindings"]),
        vocab_map={k: list(v) for k, v in d.get("vocab_map", {}).items()},
        time_unit=d["time_unit"],
    )


def load_skill(path: str) -> Skill:
    with open(path, encoding="utf-8") as f:
        return skill_from_dict(json.load(f))


def load_adapter(path: str) -> Adapter:
    with open(path, encoding="utf-8") as f:
        return adapter_from_dict(json.load(f))


def _load_dir(directory: str, parse) -> Dict[str, object]:
    out: Dict[str, object] = {}
    if not os.path.isdir(directory):
        return out
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".json"):
            continue
        obj = parse(os.path.join(directory, fname))
        out[obj.name] = obj
    return out


def load_skills(directory: str = SKILLS_DIR) -> Dict[str, Skill]:
    """All skills in ``directory``, keyed by skill name; empty if none."""
    return _load_dir(directory, load_skill)  # type: ignore[return-value]


def load_adapters(directory: str = ADAPTERS_DIR) -> Dict[str, Adapter]:
    """All adapters in ``directory``, keyed by site name; empty if none."""
    return _load_dir(directory, load_adapter)  # type: ignore[return-value]


# Registries: file-based definitions override the hardcoded fallbacks.
SKILLS: Dict[str, Skill] = {_FALLBACK_SKILL.name: _FALLBACK_SKILL, **load_skills()}
ADAPTERS: Dict[str, Adapter] = {**_FALLBACK_ADAPTERS, **load_adapters()}

DEFAULT_SKILL: Skill = SKILLS.get(_FALLBACK_SKILL.name, _FALLBACK_SKILL)
