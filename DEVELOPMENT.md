# Developing STRATA

How to pick this project back up and extend it. See [README.md](README.md) for what
STRATA is; this file is the working guide.

## Pick it back up (every session)

The virtualenv already exists (`.venv/`). You don't reinstall each time — just use it.

```bash
cd STRATA

# Windows (PowerShell / Git Bash)
.venv/Scripts/python -m pytest -q      # 32 tests, ~1s — confirms nothing is broken
.venv/Scripts/python demo.py           # end-to-end MIMIC-III -> eICU walkthrough
.venv/Scripts/python bench.py          # adaptation-cost benchmark
.venv/Scripts/python -m strata.discover  # recover each site's adapter from its DB

# macOS / Linux
.venv/bin/python -m pytest -q
.venv/bin/python demo.py
```

If `.venv/` is ever missing (fresh clone on a new machine):

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # POSIX
```

Run the test suite first thing — a green run means the last change is intact and
you're safe to build on it.

## Where things live

```
strata/
  ir.py         # skill IR + the decidable cut (core / adapter / unclassifiable)
  adapters.py   # Adapter type + hardcoded MIMIC-III/eICU fallbacks + WITHIN logic
  compiler.py   # core + adapter  ->  SQL
  verifier.py   # run SQL, enforce the core's sanity check
  db.py         # synthetic MIMIC-III / eICU SQLite fixtures
  nlu.py        # question -> (condition, N); deterministic, optional OpenAI path
  loader.py     # load skills/adapters from JSON; merges files over fallbacks
  cost.py       # transfer strategies + tunable adaptation-cost model
  discover.py   # recover a site's adapter from its DB (introspection + execution)
  validity.py   # cut validity: does the frozen decided-core transfer? (vs random cut)
  graph.py      # the LangGraph agent (parse -> cut -> bind -> compile -> verify -> respond)
skills/*.json   # skill definitions (the IR as data)
adapters/*.json # per-site typed bindings (the data-driven adapters)
tests/          # test_cut, test_transfer, test_loader
demo.py         # the full walkthrough
```

## Everyday tasks

### Add a new hospital site (a new adapter)
1. Add `adapters/<site>.json` — seven slot bindings plus a `time_unit`
   (`timestamp` or `offset_minutes`). Copy `adapters/eicu.json` as a template.
2. If you want to *execute* against it (not just compile), add a builder for it in
   `strata/db.py` and register it in `BUILDERS`.
3. Target it: `build_agent().invoke({"question": ..., "site": "<site>"})`.

No change to the cut, compiler, or graph — that's the whole point.

### Add a new task (a new skill)
1. Add `skills/<name>.json` — the ordered `steps` plus the environment `slots`.
   Copy `skills/cohort_count.json` as a template. Each step's `op` is either a
   binding op (`resolve`, `table` -> adapter) or a procedure-algebra op
   (`join`, `filter`, `dedup`, `count_distinct`, `assert` -> core).
2. If a step's *control flow* depends on a site constant, put that slot in the
   step's `structural_slots` — the cut will mark it `unclassifiable` (the
   decidability-limit case) instead of forcing it into the adapter.
3. Build the agent on it: `build_agent(loader.load_skill("skills/<name>.json"))`.

### Extend the procedure algebra
New op kinds go in `ir.py`: add to `BINDING_OPS` (adapter) or `CORE_OPS` (core),
and teach `compiler.py` how to emit SQL for it.

### Turn on the LLM parse path
`STRATA_USE_LLM=1` routes question parsing through Claude (needs `anthropic`
installed and credentials configured); it falls back to the deterministic parser.

## Verifying a change

Always run both before committing:

```bash
.venv/Scripts/python -m pytest -q     # regression check
.venv/Scripts/python demo.py          # eyeball the end-to-end behavior
```

Add a test for anything new — `tests/test_cut.py` for classification,
`tests/test_transfer.py` for execution/transfer, `tests/test_loader.py` for data files.

## Git workflow

`origin` is already set (github.com/AdithNG/STRATA). Typical loop:

```bash
git add -A
git commit -m "…"
git push
```

## Roadmap (tied to the proposal)

Rough order, matching the phased plan in [TSAGENT_EVOLVE_SKILLS.md](TSAGENT_EVOLVE_SKILLS.md):

- **Cut validity (primary metric).** *Done* — [strata/validity.py](strata/validity.py)
  freezes the decided core, fits only the adapter by discovery, and checks transfer
  on held-out sites (100%) against a random-cut baseline (0%). **Open:** a
  structural-shift target that drops validity below 100%, to exercise the
  decidability limit end to end.
- **Decidable cut as taint propagation.** *Done* — the cut is now a def-use taint
  analysis (binding ops propagate, procedure ops launder), not op-category
  matching; see [strata/ir.py](strata/ir.py) `taint_map`.
- **Measured adaptation cost (headline).** *Done as a proxy* — [strata/cost.py](strata/cost.py)
  + [bench.py](bench.py) score four strategies by a tunable edit-cost model and by
  observed correctness (STRATA 17% of from-scratch, correct; random cut cheap but
  0/8 correct). **Still open:** replace the edit-cost proxy with a real skill
  optimizer so the number is measured LLM tokens/edits, not a model.
- **Baselines.** *Done* — whole-skill transfer and the **random-cut** baseline are
  in the benchmark; the random cut fails on every seed, so "the *decidable* cut
  matters" is observed, not asserted.
- **Cut-validity metric.** Check that the statically-decided core actually
  transfers (agreement with a held-out cross-environment reusability estimate).
- **Instance discovery.** *Done for the schema case* — [strata/discover.py](strata/discover.py)
  recovers a site's adapter from its database by catalog introspection (constant
  slots) plus execution-confirmed slot-filling (implementation slots), reproducing
  the correct counts at 1–4 verifier executions. **Still open:** LLM synthesis for
  implementation slots (instead of a fixed candidate pool), and GUI/tool catalogs.
- **Second domain.** Cross-schema text-to-SQL (BIRD/Spider), then the tool/MCP
  workflow axis from Appendix B (GitHub → Jira) — the interface-generalization
  domain that makes STRATA an agent-skill theory, not a text-to-SQL result.
- **Real data.** Move from synthetic fixtures to credentialed MIMIC-III / eICU
  (EHRSQL), and add the OMOP/OHDSI common-data-model baseline.
- **Team interface.** Align the `skills/` + `adapters/` JSON format with Kratika's
  skill dataset so it plugs straight into the loader.

## Optional LLM path (OpenAI)

`STRATA_USE_LLM=1` routes NL question parsing through OpenAI. The key is read from
`OPENAI_API_KEY` (never hardcoded — a committed key leaks permanently in git
history). Set it locally: `setx OPENAI_API_KEY "sk-..."` (Windows) or
`export OPENAI_API_KEY="sk-..."` (POSIX); override the model with `OPENAI_MODEL`.
Install the optional dep: `.venv/Scripts/python -m pip install openai`.
