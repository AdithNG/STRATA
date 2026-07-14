"""Turn the natural-language question into typed task parameters.

Deterministic by default so the agent runs with no API key. Set
``STRATA_USE_LLM=1`` (and have credentials configured) to route parsing through
Claude instead; the deterministic parser is the fallback either way.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Tuple

from strata.adapters import MIMIC_III

# Conditions the demo vocabularies know about.
_KNOWN = sorted(set(MIMIC_III.vocab_map.keys()), key=len, reverse=True)


def _parse_deterministic(question: str) -> Tuple[str, int]:
    q = question.lower()
    condition = next((c for c in _KNOWN if c in q), "sepsis")
    m = re.search(r"within\s+(\d+)\s*day", q)
    n_days = int(m.group(1)) if m else 7
    return condition, n_days


def _parse_llm(question: str) -> Optional[Tuple[str, int]]:
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
        schema = {
            "type": "object",
            "properties": {
                "condition": {"type": "string"},
                "n_days": {"type": "integer"},
            },
            "required": ["condition", "n_days"],
            "additionalProperties": False,
        }
        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=256,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{
                "role": "user",
                "content": (
                    "Extract the clinical condition and the day window from this "
                    f"cohort-count question. Question: {question!r}"
                ),
            }],
        )
        import json
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
        return str(data["condition"]).lower(), int(data["n_days"])
    except Exception:
        return None


def parse_question(question: str) -> Tuple[str, int]:
    """Return ``(condition, n_days)``."""
    if os.environ.get("STRATA_USE_LLM") == "1":
        parsed = _parse_llm(question)
        if parsed is not None:
            return parsed
    return _parse_deterministic(question)
