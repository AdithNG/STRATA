"""Turn the natural-language question into typed task parameters.

Deterministic by default so the agent runs with no API key. Set
``STRATA_USE_LLM=1`` to route parsing through OpenAI instead; the deterministic
parser is the fallback either way.

The OpenAI key is read from the ``OPENAI_API_KEY`` environment variable and is
never hardcoded (a key committed to git would leak permanently). Set it locally:

    setx OPENAI_API_KEY "sk-..."      # Windows, new shells
    export OPENAI_API_KEY="sk-..."    # POSIX

Override the model with ``OPENAI_MODEL`` (default ``gpt-4o-mini``).
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


def _load_env_file() -> None:
    """Load a gitignored repo-root ``.env`` into the environment.

    Minimal parser so there's no python-dotenv dependency. Values in ``.env`` take
    precedence for this project (they override ambient environment variables), so a
    stale ``OPENAI_API_KEY`` left in the shell can't shadow the project key. Delete
    ``.env`` to fall back to the ambient environment.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip().strip('"').strip("'")


def _parse_openai(question: str) -> Optional[Tuple[str, int]]:
    _load_env_file()
    if not os.environ.get("OPENAI_API_KEY"):
        return None  # never hardcode a key; require it in the environment or .env
    try:
        import json

        from openai import OpenAI

        client = OpenAI()  # reads OPENAI_API_KEY from the environment
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract the clinical condition and the day window from a "
                        "cohort-count question. Reply with JSON: "
                        '{"condition": <string>, "n_days": <integer>}.'
                    ),
                },
                {"role": "user", "content": question},
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return str(data["condition"]).lower(), int(data["n_days"])
    except Exception:
        return None


def parse_question(question: str) -> Tuple[str, int]:
    """Return ``(condition, n_days)``."""
    if os.environ.get("STRATA_USE_LLM") == "1":
        parsed = _parse_openai(question)
        if parsed is not None:
            return parsed
    return _parse_deterministic(question)
