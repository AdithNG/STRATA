# Developing STRATA

How to pick this project back up and extend it. See [README.md](README.md) for what
STRATA is; this file is the working guide.

## Pick it back up (every session)

The virtualenv already exists (`.venv/`). You don't reinstall each time — just use it.

```bash
cd STRATA

# Windows (PowerShell / Git Bash)
.venv/Scripts/python -m pytest -q     # 15 tests, ~1s — confirms nothing is broken
.venv/Scripts/python demo.py          # end-to-end MIMIC-III -> eICU walkthrough

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
  nlu.py        # question -> (condition, N); deterministic, optional Claude path
  loader.py     # load skills/adapters from JSON; merges files over fallbacks
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

- **Measured adaptation cost (headline).** Replace hand-written adapter bindings
  with a real skill optimizer, so "fit the adapter" is a measured token/edit cost
  vs. from-scratch full optimization.
- **Baselines.** Add whole-skill transfer and the **random-cut** baseline so
  "the *decidable* cut matters" is measurable, not asserted.
- **Cut-validity metric.** Check that the statically-decided core actually
  transfers (agreement with a held-out cross-environment reusability estimate).
- **Second domain.** Cross-schema text-to-SQL (BIRD/Spider) — also probes where
  the core shrinks as SQL knowledge moves into weights.
- **Real data.** Move from synthetic fixtures to credentialed MIMIC-III / eICU.
- **Team interface.** Align the `skills/` + `adapters/` JSON format with Kratika's
  skill dataset so it plugs straight into the loader.
