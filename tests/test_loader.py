"""Tests for the data-driven skill/adapter loader."""

import json
import os

from strata import loader
from strata.adapters import EICU, MIMIC_III
from strata.ir import COHORT_COUNT_SKILL


def test_skill_file_matches_hardcoded_fallback():
    # The JSON file must parse to an object identical to the code literal, so
    # the data files are a faithful externalization, not a divergent copy.
    loaded = loader.load_skill(os.path.join(loader.SKILLS_DIR, "cohort_count.json"))
    assert loaded == COHORT_COUNT_SKILL


def test_adapter_files_match_hardcoded_fallback():
    mimic = loader.load_adapter(os.path.join(loader.ADAPTERS_DIR, "mimic_iii.json"))
    eicu = loader.load_adapter(os.path.join(loader.ADAPTERS_DIR, "eicu.json"))
    assert mimic == MIMIC_III
    assert eicu == EICU


def test_registries_populated_from_files():
    assert "cohort_count" in loader.SKILLS
    assert set(loader.ADAPTERS) >= {"MIMIC-III", "eICU"}


def test_new_adapter_file_is_discovered(tmp_path):
    # Dropping a JSON file into an adapters dir is enough to add a site.
    site = {
        "name": "SYNTH",
        "time_unit": "offset_minutes",
        "bindings": {
            "VOCAB": "ICD",
            "DX_TABLE": "dx",
            "CODE_COL": "code",
            "ADM_TABLE": "adm",
            "PATIENT_KEY": "pid",
            "TIME_EXPR": "offset",
            "WITHIN": "offset BETWEEN 0 AND N*24*60",
        },
        "vocab_map": {"sepsis": ["1", "2"]},
    }
    (tmp_path / "synth.json").write_text(json.dumps(site), encoding="utf-8")
    found = loader.load_adapters(str(tmp_path))
    assert "SYNTH" in found
    assert found["SYNTH"].within_predicate("dx", "adm", 7).endswith("0 AND 10080")
