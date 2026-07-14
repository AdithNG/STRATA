# STRATA: Freezing a Skill's Procedure Core and Re-fitting Only a Typed Convention Adapter for Cheap Adaptation to New Data Environments

*Research proposal. STRATA = the two strata a skill is split into: an environment-agnostic procedure layer and an environment-bound convention layer. Working title.*

---

## **1. Problem**

LLM agents use external **skills** (text/code playbooks retrieved at decision time) to improve on procedural tasks without touching weights. But a task class usually recurs across **environments** that differ only in local conventions — a data-analysis procedure meets a new schema, hospital site, dialect, or spreadsheet layout. A skill entangles two parts that behave differently under such a shift: an environment-agnostic **procedure** (control flow, tool-call discipline, verification steps) and environment-bound **conventions** (table/column names, units, formats, dialect operators).

Because a skill is a monolith, moving to a new environment forces one of two bad options: **re-optimize wholesale** (pay again to relearn the procedure the agent already has, at every new environment) or **transfer wholesale** (drag along the old environment's conventions → negative transfer, as repeatedly observed for over-specialized skills). If the procedure could be *isolated and frozen* while only conventions are *re-fit*, adaptation would cost only the price of the conventions and could never corrupt the procedure.

The obstacle: "which part is procedure vs. convention" has only been handled by soft, latent, or LLM-judged mechanisms. STRATA's bet is that where **conventions are typed constants** (schemas, units, dialects, layouts), the cut can be made **decidable**, and decidability is what makes freezing the reusable part safe and cheap.

## **2. Research question (framed as measurement)**

> In a verifiable domain where conventions are typed constants, how much of a skill is a freezable, environment-agnostic **procedure core** vs. an irreducibly convention-bound remainder — as decided by a typed representation — and can freezing the core and fitting only a small typed **convention adapter** recover most of from-scratch performance in a new environment at a fraction of the budget, with zero interference on environments already covered?
> 

Both outcomes publish: a **large core** → a method (decidable disentanglement + frozen-core transfer); a **thin core** → a fine-grained result (the transferable signal in verifiable domains is dominated by convention bindings, localized by the typed cut — sharper than whole-skill "some skills transfer").

## **3. Approach**

**Dual representation.** Each skill = a natural-language body (frozen LLM consumes/edits it; auditable, zero extra inference) coupled to a **strongly-typed IR**: ordered procedure steps + control flow, typed *slots* for environment constants, and typed constraints. The IR is the source of truth for logical operations; the NL view is regenerated from it and the verifier catches drift.

**Decidable cut.** A skill unit belongs to the **convention adapter** for environment *c* **iff** it references an environment-bound symbol of *c* (schema/column id, unit, format token, dialect operator); otherwise it is **procedure core**. Operationally this is a def-use/taint analysis over the IR (environment constants = tainted sources). Because it is static and typed, the cut is decidable for expressible skills; conflict/redundancy reduce to type-clash/subsumption checks, and merging cores to typed anti-unification.

**Frozen-core transfer.** Deploy to *c* as `core ⊕ adapter_c`. Freezing `core` and only adding/replacing an adapter gives **backward interference ≡ 0 by construction** (a covered environment's pair is untouched). For a new environment *c**: compute the cut, freeze `core`, fit only `adapter_{c*}` with a small budget, gated by a symbolic type-check then the domain's execution verifier.

**Controller (secondary).** A heuristic per-gap policy — reuse / adapt (fit a new adapter on a frozen core) / create. Learning it with RL is an *optional* extension, not the contribution.

## **4. Metrics**

- **Adaptation cost** — optimizer tokens/edits for adapter-only fitting vs. from-scratch full optimization (headline claim).
- **Forward-transfer recovery** — fraction of from-scratch performance recovered by frozen-core + small adapter.
- **Backward interference** — change on previously covered environments (expected ≈ 0; verified empirically).
- **Core-mass spectrum** — fraction of units the cut assigns to core vs. adapter (main descriptive figure).
- **Cut validity** — agreement between the *decidable* core and a held-out cross-environment reusability estimate (does the statically-decided core actually transfer?).
- **Zero-shot core gain** — does `core` alone beat no-skill?

## **5. Domains, baselines, plan**

**Domains** (conventions are typed; verification automatic): flagship **SpreadsheetBench-style** cross-workbook (procedure non-trivial, not baked into weights); **cross-schema text-to-SQL (BIRD/Spider)** (also probes where the core shrinks as SQL moves into weights); **cross-site clinical SQL (EHRSQL: MIMIC-III + eICU)** (real convention shift).

**Baselines:** no-skill (floor); from-scratch full optimization (ceiling); whole-skill transfer; MASA-style whole-skill rewriter recast to the *environment* axis; latent recomposition (Learning-to-Compose–style); undifferentiated skill evolution across the stream; **random cut** (equal buckets, random assignment — proves the *decidable* cut matters); core-only zero-shot.

**Phased plan (with gates):**

- **P0** — build IR + decidable cut on cross-schema SQL; core-mass and cut-validity spectra. *Gate:* non-trivial core that beats the random cut on validity? else → measurement paper.
- **P1** — full transfer protocol vs. all baselines on SQL: adaptation cost, forward-transfer recovery, backward interference ≈ 0. *Publishable core, modest compute.*
- **P2** — flagship SpreadsheetBench + EHRSQL; environment-stream; source-count and adapter-budget sweeps.
- **P3 (optional)** — learned controller; NL-only vs. NL+IR ablation; decidability-limit analysis (fraction of un-classifiable, entangled units).

## **6. Risks and scope**

- **Thin core (domain-dependent).** Flagship chosen for thick procedure; either way a measurement result; report core-mass with a source-count sweep + bootstrap CIs.
- **Decidability limits.** Clean only when conventions are true typed constants; steps valid only given an environment-specific tool are neither pure core nor adapter. We *measure and report* the un-classifiable fraction; claims are scoped to typed-convention domains.
- **NL↔IR drift.** IR is source of truth; NL regenerated from it; verifier catches functional drift; ablate NL-only vs. NL+IR.
- **Out of scope:** open-ended/subjective tasks lacking typed conventions.

## **7. Related work**

STRATA sits among a dense recent literature but is subsumed by none; the delta for each strand is stated at its end.

**Skill-library agents & experiential memory.** Voyager (2305.16291), ReAct, Reflexion, ExpeL, AutoManual, JARVIS-1, Ghost-in-the-Minecraft, AgentTrek, Toolformer; surveys SoK: Agentic Skills (2602.20867) and *A Survey of Agent Skills* (Yang et al., 2026). *All treat a skill as one artifact to collect/retrieve/optimize; none isolates a freezable within-skill procedure core.*

**Genesis & evolution.** SkillComposer (2606.06079), EvoSkill, CoEvoSkills, SkillClaw (2604.08377), SkillOS (2605.06614), AlignEvoSkill (2506.23149), Trace2Skill, SKILL-DISCO (2606.26669), OptSkills (2605.29829), Workflow-to-Skill (2606.06893). *These study how skills are born/evolved, not how a skill's content is stratified for cross-environment reuse.*

**Frozen-model text-skill optimization.** SkillOpt (Microsoft, 2605.23904; skills as trainable parameters, edit-budget as learning rate, gains largest on procedural tasks), GEPA, TextGrad, CFPO, SoftSkill (2606.20333; soft-prefix delta). *STRATA uses such an optimizer as its engine but optimizes only a small typed adapter on transfer.*

**RL over skills / internalization.** Skill-R1 (2605.09359), SkillRL (2602.08234), SkillC (2605.27899), Skill0 (2604.02268), LatentSkill (2606.06087), Mem-Skill, ReuseRL (2605.31509), SkillGraph (2605.12039). *STRATA's RL is optional; unlike the internalization line it keeps skills as frozen, auditable external artifacts.*

**Decomposition, composition, routing.** **MASA (2605.30723)** — general/task-specific split + learned rewriter, but conditioned on the **model backbone**, rewriting the whole skill, no frozen core. **Learning to Compose (2602.11114)** — reusable **latent** capability bases + sparse composer + counterfactual marginal attribution, but latent/weight-internalized, one-pass, no frozen symbolic core. Also XSkill, SkillX, MMSkills (2605.13527), SkillRouter (2603.22455), SkillWeaver / Compositional Skill Routing (2606.18051), and robotics *Decompose and Recompose* (2605.01448). *STRATA differs on axis (data-convention, not model/latent), representation (decidable typed cut, not soft/latent), and a frozen core with a zero-interference guarantee.*

**Representation & portability.** SkCC (2605.03353; SkIR, a typed IR decoupling skill semantics from **framework formatting**, static, O(m+n)), SkVM (2604.03088). *STRATA repurposes the typed-IR idea for procedure-vs-data-convention disentanglement within content, plus transfer and measurement — not formatting portability.*

**Procedural-memory transfer: measurement.** AFTER (2606.23127; **whole-skill** transfer across tasks/roles/models; narrow experience over-specializes), a procedural-retrieval benchmark (2511.21730; abstractions that strip object-specific detail transfer better), SkillRet (2605.05726), SkillsBench. *STRATA moves the measurement from whole-skill to **within-skill** and turns "abstraction aids transfer" into a mechanism with a freezing guarantee.*

**Agentic memory (adjacent).** Mem0, EvolveMem (2605.13941), MemEvolve (2512.18746), AutoMEM (2606.04315). *These target what to remember/retrieve, complementary to structuring a skill for freezing.*

**Library learning & neurosymbolic abstraction (foundational).** DreamCoder (Ellis et al., 2021), LILO (Grand et al., 2024), ReGAL. *A procedure core with typed slots is a learned abstraction whose arguments are the adapter; STRATA adapts this from program synthesis to frozen-LLM skills on the data-convention axis.*

**Transfer theory.** Successor Features + GPI (Barreto et al., 2017), options (Sutton, Precup & Singh, 1999) motivate the frozen-core/light-specializer split and reporting a source-count curve.

| Prior line | adaptation axis | representation | core frozen? | reuse decided by | granularity |
| --- | --- | --- | --- | --- | --- |
| SkillOpt / GEPA / SoftSkill | task/model | NL / soft prefix | no | — | — |
| MASA | **model backbone** | NL | no | learned rewriter | — |
| Learning to Compose | domain | **latent, in-weights** | no | counterfactual attribution | — |
| SkCC / SkVM | **framework/format** | **typed IR** | n/a (static) | — | — |
| AFTER / 2511.21730 | tasks/roles/models | NL | no | empirical transfer | **whole-skill** |
| **STRATA** | **data-convention env.** | **dual NL + typed IR** | **yes (by construction)** | **decidable typed cut** | **within-skill** |

No prior jointly makes the procedure/convention cut **decidable and typed**, **freezes** the core for cross-environment transfer with **zero interference**, and measures reusability **within** a skill.

## **8. Contributions**

1. **A decidable, typed procedure/convention cut** for agent skills (dual NL + typed IR; a unit is adapter iff it references a typed environment constant), reducing conflict/merge to typed operations — extending typed-IR ideas from formatting portability to within-content disentanglement.
2. **Frozen-core, typed-adapter transfer with a zero-interference guarantee**, and evidence it beats whole-skill rewriting, latent recomposition, and undifferentiated evolution on adaptation cost.
3. **A within-skill reusability measurement** — how much of a procedural skill is freezable transferable core vs. convention-bound in typed-convention domains — with a validity test that the decidable core actually transfers.

---

## **Appendix A — Worked example: cross-site clinical SQL (MIMIC-III → eICU)**

The most apt demonstration is a **cohort-count question answered over two hospital databases**. The *question class* recurs unchanged across sites; the *procedure* (cohort logic) is non-trivial and reusable; and the *conventions* (table/column names, code vocabulary, time encoding, dialect) are fully typed and change completely between sites. This is the ideal stress case: everything that changes is a typed constant, and the thing that stays is the discipline a naive from-scratch attempt tends to get wrong (double-counting patients).

**Task class.** "How many distinct patients were diagnosed with *{condition}* within *{N}* days of admission?"

**Skill as learned on MIMIC-III (monolithic, NL sketch).**

> Resolve the condition to ICD-9 codes. Join `diagnoses_icd` to `admissions` on `subject_id`. Keep diagnoses within N days of `admittime`. **Deduplicate to distinct `subject_id`** (a patient may have many diagnosis rows). Count distinct patients. **Check the count does not exceed the number of admitted patients.**
> 

The bolded steps are the reusable discipline; the identifiers and time handling are site-specific.

**Typed IR (same for every site; environment constants marked `⟨…⟩`).**

SMT / SAT

```
PROCEDURE cohort_count(condition, N):
  codes    := resolve(condition, ⟨VOCAB⟩)                     # adapter binding
  dx       := TABLE(⟨DX_TABLE⟩)   ; adm := TABLE(⟨ADM_TABLE⟩)  # adapter binding
  joined   := join(dx, adm, on = ⟨PATIENT_KEY⟩)               # core op, adapter-bound key
  filtered := filter(joined, ⟨WITHIN⟩(⟨TIME_EXPR⟩, N))        # core op, adapter-bound predicate
  uniq     := dedup(filtered, by = ⟨PATIENT_KEY⟩)             # CORE discipline
  n        := count_distinct(uniq, ⟨PATIENT_KEY⟩)             # CORE
  assert   n <= count_distinct(adm, ⟨PATIENT_KEY⟩)            # CORE sanity check
  return n
```

**Decidable cut** (a unit is *adapter* iff its value flows from a typed constant `⟨…⟩`; else *core*):

| Unit | Core / Adapter | Reason |
| --- | --- | --- |
| resolve condition → codes | adapter | binds `VOCAB` |
| pick DX / ADM tables | adapter | binds `DX_TABLE`, `ADM_TABLE` |
| join on patient key | **core** op with adapter-bound key `⟨PATIENT_KEY⟩` | the *join discipline* is site-agnostic; the identifier is a slot |
| time-window filter | **core** op with adapter-bound `⟨WITHIN⟩`, `⟨TIME_EXPR⟩` | "filter within a window" is site-agnostic; the time encoding is a slot |
| dedup by patient | **core** | pure discipline |
| count distinct / sanity check | **core** | pure discipline |

**Adapters (the only things that change between sites).**

```
MIMIC-III:  VOCAB=ICD9  DX_TABLE=diagnoses_icd(icd9_code)  ADM_TABLE=admissions
            PATIENT_KEY=subject_id  TIME_EXPR=admittime
            WITHIN(t,N) := charttime BETWEEN admittime AND admittime + N days   # absolute timestamps

eICU:       VOCAB=ICD(mixed, string)  DX_TABLE=diagnosis(icd9code)  ADM_TABLE=patient
            PATIENT_KEY=patienthealthsystemstayid  TIME_EXPR=diagnosisoffset
            WITHIN(t,N) := diagnosisoffset BETWEEN 0 AND N*24*60                # minutes-from-admit offset
```

*(Bindings illustrative.)* Note eICU encodes time as a **minutes-since-admission offset**, not an absolute timestamp — a genuinely different convention that the adapter absorbs while the core operation ("filter within a window") is untouched.

**Payoff demonstrated.**

- **Adaptation cost.** Transfer MIMIC-III → eICU freezes the whole `PROCEDURE` core and re-fits only the ~5-line eICU adapter (four identifier bindings + the `WITHIN` predicate). The dedup + sanity-check discipline is not re-optimized.
- **Zero interference (by construction).** The MIMIC-III adapter is never touched, so MIMIC-III performance cannot change when eICU is added.
- **Why the frozen core matters.** The dedup-then-count and the count ≤ admitted check are exactly what a from-scratch attempt on a new schema tends to get wrong (patients with multiple diagnosis rows inflate the count). Freezing verified discipline prevents relearning — and re-breaking — it at every new site.

**Decidability limit (reported honestly).** Here the time difference is adapter-absorbable because the core op is unchanged. If a site instead required a *structurally different procedure* — e.g., diagnoses split across two tables needing an extra `UNION`, or a window computed via a correlated subquery — that step's control flow would depend on a site constant and be **neither pure core nor pure adapter**. STRATA counts such units in the decidability-limit metric (§6) rather than silently forcing them into the adapter.

*The same pattern instantiates in the other target domains: cross-workbook spreadsheets (core = the aggregate/pivot/validate discipline; adapter = sheet/column layout and number formats) and cross-dialect SQL (adapter = `LIMIT` vs `TOP`, date arithmetic, quoting).*