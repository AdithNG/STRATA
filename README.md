# STRATA — LangGraph agent

A small, runnable LangGraph implementation of the STRATA proposal
([TSAGENT_EVOLVE_SKILLS.md](TSAGENT_EVOLVE_SKILLS.md)): split a skill into a
**frozen, environment-agnostic procedure core** and a **typed, per-environment
convention adapter**, so adapting to a new data environment costs only the price
of re-fitting the adapter and can never corrupt the verified procedure.

The demo instantiates Appendix A: the cross-site clinical cohort-count question,
transferred from **MIMIC-III** to **eICU** by re-fitting only the adapter.

> *"How many distinct patients were diagnosed with `{condition}` within `{N}`
> days of admission?"*

## What's here

| Piece | File | Role |
|-------|------|------|
| Typed IR + **decidable cut** | [strata/ir.py](strata/ir.py) | The skill as an ordered IR; a static taint rule that labels each unit `core` / `adapter` / `unclassifiable` |
| Skill / adapter loader | [strata/loader.py](strata/loader.py) | Loads skills and adapters from JSON data files (see below) |
| Convention adapters | [strata/adapters.py](strata/adapters.py) | MIMIC-III and eICU bindings — the only thing that changes between sites |
| SQL compiler | [strata/compiler.py](strata/compiler.py) | Composes `core → adapter_c` into executable SQL |
| Execution verifier | [strata/verifier.py](strata/verifier.py) | Runs the SQL and enforces the core's sanity check |
| Synthetic databases | [strata/db.py](strata/db.py) | MIMIC-III- and eICU-shaped SQLite fixtures |
| **LangGraph agent** | [strata/graph.py](strata/graph.py) | `parse → cut → bind_adapter → compile → verify → respond` |
| NL parsing | [strata/nlu.py](strata/nlu.py) | Deterministic by default; optional Claude path |
| Adaptation-cost model | [strata/cost.py](strata/cost.py) | Four transfer strategies + a tunable edit-cost proxy |
| Instance discovery | [strata/discover.py](strata/discover.py) | Recover a site's adapter from its database by introspection + execution |
| Demo | [demo.py](demo.py) | The full MIMIC-III → eICU walkthrough |
| Benchmark | [bench.py](bench.py) | Adaptation cost + observed correctness across strategies |
| Tests | [tests/](tests/) | Cut classification, transfer, zero-interference, and cost |

## The agent graph

```
parse_task → apply_cut → bind_adapter → compile → execute_verify → respond
                                                          └─(sanity failed)→ flag
```

Re-targeting the skill to a new site changes only which adapter `bind_adapter`
selects. The frozen core, the cut, and every other node are unchanged — that is
the mechanism, made executable.

## The decidable cut

A unit belongs to the **adapter** iff its operation's purpose is to instantiate a
typed environment constant (`resolve` a vocabulary, pick a `table`). Every
procedure-algebra op (`join`, `filter`, `dedup`, `count_distinct`, `assert`) is
**core** — the reusable discipline — even when it references a slot as a typed
hole (the join key, the dialect time predicate). A procedure step whose *control
flow* depends on an environment constant is **unclassifiable** — the decidability
limit the proposal reports honestly, counted rather than forced into the adapter.

For the cohort-count skill the cut yields a 5-of-8 core-mass: `join`,
`filter_window`, `dedup`, `count`, `sanity` are frozen; only `resolve_codes`,
`pick_dx`, `pick_adm` re-fit per site.

## Where the skills and adapters live

Skills and adapters are **data files**, not hardcoded — adding a task or a site is
a JSON file, not a code change. The cut, compiler, and graph never change.

```
skills/cohort_count.json      # the skill IR (slots + ordered steps)
adapters/mimic_iii.json       # one site's typed bindings
adapters/eicu.json
```

At startup the loader reads both directories and builds the same `Skill` /
`Adapter` objects the code would; file definitions override the hardcoded
fallbacks in `ir.py` / `adapters.py` on a name clash, so the framework still runs
if the files are absent. A skill file is an ordered list of typed steps plus the
environment slots; an adapter file binds every slot to a concrete symbol for one
site and picks a `time_unit` (`timestamp` vs `offset_minutes`) that drives the
dialect-specific `WITHIN` predicate. This JSON shape is the contract for a **skill
dataset** — e.g. one entry per data environment.

To add a new site: drop `adapters/<site>.json` with the seven slot bindings and a
`time_unit`; the agent can then target it by name with no code change.

## What the demo shows

- **Correct, deduplicated counts** — MIMIC-III returns 5 distinct patients from 8
  diagnosis rows; eICU returns 3. The dedup discipline (which a naive from-scratch
  attempt tends to get wrong) is frozen, not relearned.
- **Adaptation cost** — 0 core steps re-optimized on transfer; only the ~7-binding
  adapter is fit for eICU, including its *minutes-since-admission offset* time
  encoding, absorbed entirely by the adapter's `WITHIN` predicate while the core
  `filter` op is untouched.
- **Backward interference == 0 by construction** — adding the eICU adapter leaves
  the MIMIC-III adapter (and its answer) byte-for-byte unchanged.

## Adaptation cost (the headline metric)

`bench.py` transfers the skill MIMIC-III → eICU under four strategies, runs each
against the eICU database, and reports re-fit cost against *observed* correctness:

| strategy | edit cost | vs from-scratch | result |
|----------|----------:|----------------:|--------|
| from_scratch | 18 | 100% | correct |
| whole_skill | 18 | 100% | correct (risks negative transfer) |
| **strata** | **3** | **17%** | **correct** |
| random_cut | 7.5 | 42% | **0/8 correct** |

STRATA re-fits only the 3 adapter units (freezing the 5 core steps) at 17% of
from-scratch cost, and stays correct. The random cut is *cheaper than* from-scratch
too — but freezing whole units without the typed op/hole separation strands
MIMIC-III's constants and fails on every seed. **The saving comes from the
*decidable* cut, not from freezing per se.**

Cost is a transparent, tunable proxy for optimizer edits (`CORE_WEIGHT` /
`ADAPTER_WEIGHT` in [strata/cost.py](strata/cost.py)) — not LLM token cost yet;
wiring a real optimizer in is the next step. The qualitative result is robust to
the weights.

## Instance discovery (fit a site's adapter with no hand-written bindings)

The sharpened proposal reframes an environment as an *instance of an abstract typed
interface* and puts adaptation cost in **instance discovery**: run the frozen core
against a new site, resolve each typed slot against the environment's catalog, and
confirm by execution. `strata/discover.py` does this — given only a site's database
it recovers the adapter and reproduces the correct cohort count:

```
MIMIC-III:  DX=diagnoses_icd KEY=subject_id TIME=charttime impl(WITHIN)=timestamp
            cohort count = 5  |  discovery cost = 1 verifier execution
eICU:       DX=diagnosis KEY=patienthealthsystemstayid TIME=diagnosisoffset
            impl(WITHIN)=offset_minutes  cohort count = 3  |  discovery cost = 4
```

Constant slots (identifiers) resolve by typed name-matching against the schema;
**implementation slots** — the time-window predicate and the code vocabulary,
marked `kind: "implementation"` on the skill — are filled from a small typed
candidate pool and selected by execution against the core's contract. The eICU
minutes-offset time encoding is *discovered*, not hand-set. Discovery cost (1 and 4
verifier executions) is far below the from-scratch proxy (18).

Run: `python -m strata.discover`

## Run it

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # POSIX

python demo.py          # full MIMIC-III → eICU walkthrough
python bench.py         # adaptation-cost benchmark across strategies
python -m pytest -q     # 21 tests
python -m strata.db     # (optional) materialize the SQLite fixtures under data/
```

## Notes and scope

- The databases are **synthetic fixtures** with the real conventions (table/column
  names, code vocabularies, and the two different time encodings). Real MIMIC-III /
  eICU are credentialed; the framework connects to any SQLite database with the
  expected shape. `diagnoses_icd` has no per-row timestamp in real MIMIC-III — a
  `charttime` is added here to make the time-window step exercisable, following the
  proposal's Appendix A model.
- NL parsing is deterministic by default so the agent runs offline. Set
  `STRATA_USE_LLM=1` (with Claude credentials configured) to route parsing through
  the model; it falls back to the deterministic parser otherwise.
- This is a reference implementation of the mechanism, not the full experimental
  harness — the phased plan (baselines, core-mass spectra, adapter-budget sweeps)
  in the proposal is future work built on these primitives.
