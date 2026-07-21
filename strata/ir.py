"""Typed IR for a skill, plus the decidable procedure/convention cut.

A skill is an ordered list of typed steps over a small procedure algebra. Some
steps *bind* environment constants (typed ``Slot``s: schema ids, vocabularies,
dialect predicates); the rest are environment-agnostic control-flow / discipline
steps that merely *reference* those slots as typed holes.

The cut (`cut`) is a static def-use / taint classification:

* A step whose operation's purpose is to instantiate an environment constant
  (a *binding* op) is **ADAPTER** -- its output value is convention-bound.
* A step from the procedure algebra is **CORE** -- it is the reusable discipline,
  even when it references slots as holes (the join key, the time predicate).
* A procedure step whose *control flow / structure* depends on an environment
  constant is **UNCLASSIFIABLE** -- neither pure core nor pure adapter. This is
  the decidability limit the proposal reports honestly (Section 6); we count it
  rather than silently forcing it into the adapter.

Because the rule is a static property of each step (operation category plus the
presence of a structural slot dependency), the cut is decidable for expressible
skills.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


# Two kinds of operation, which is what makes taint propagation decidable:
#
# * BINDING_OPS resolve/select environment symbols. Their output *is* a convention,
#   so taint flows THROUGH them: their result is tainted if they reference a slot
#   or consume an already-tainted value (a binding chain).
# * CORE_OPS are the procedure algebra. They transform tainted arguments into task
#   data, so they *launder* taint: their output is never tainted, even when they
#   consume tainted values or reference a slot as a typed hole (`dedup(by=<KEY>)`).
#
# A unit is ADAPTER iff its output is tainted; CORE otherwise. Laundering is what
# lets a core op carry an adapter-bound hole without becoming adapter itself.
BINDING_OPS = frozenset({"resolve", "table"})
CORE_OPS = frozenset({"join", "filter", "dedup", "count_distinct", "assert"})


class Class(str, Enum):
    CORE = "core"
    ADAPTER = "adapter"
    UNCLASSIFIABLE = "unclassifiable"  # decidability limit (Section 6)


@dataclass(frozen=True)
class Slot:
    """A typed environment-bound entity -- the taint source of the cut.

    Under the interface/instance model, a slot's filler is not only a constant.
    ``kind`` records what an instance may put here:

    * ``constant``       -- a literal binding (a table or column identifier).
    * ``implementation`` -- arbitrary code behind a fixed signature (e.g. the
      time-window predicate: absolute timestamps vs. minute offsets). Lets the
      convention layer absorb *structural* variation, not just renaming.
    * ``contract``       -- an invariant any valid instance must preserve.

    Discovery treats these differently: constants resolve by catalog name-matching;
    implementations are filled by typed synthesis confirmed by execution.
    """

    name: str
    type: str  # e.g. "table", "column", "vocab", "predicate"
    description: str = ""
    kind: str = "constant"  # "constant" | "implementation" | "contract"


@dataclass(frozen=True)
class Step:
    """One IR unit.

    ``value_slots`` are slots referenced as typed *holes* (fill a value: a table
    name, a join key, a dialect predicate). ``structural_slots`` are slots whose
    value would change the step's *control flow / shape* -- their presence makes
    the step neither pure core nor pure adapter.
    """

    id: str
    op: str
    produces: str  # symbolic name this step binds
    value_slots: tuple = ()          # slot names referenced as holes
    inputs: tuple = ()               # produced-value names this step consumes (def-use edges)
    structural_slots: tuple = ()     # slot names the control flow depends on
    note: str = ""


@dataclass(frozen=True)
class Unit:
    """A classified step: the result of applying the cut to one ``Step``."""

    step: Step
    cls: Class
    reason: str


@dataclass(frozen=True)
class Skill:
    """A skill = an ordered IR (the source of truth) plus its declared slots.

    The natural-language body is regenerated from the IR; here we keep the NL
    sketch alongside for auditability, matching the proposal's dual representation.
    """

    name: str
    task_params: tuple
    slots: tuple  # tuple[Slot]
    steps: tuple  # tuple[Step]
    nl_sketch: str = ""

    def slot(self, name: str) -> Slot:
        for s in self.slots:
            if s.name == name:
                return s
        raise KeyError(f"no such slot: {name}")


def _output_tainted(step: Step, tainted_values: set) -> bool:
    """Is this step's produced value tainted? (taint / binding-time propagation)

    CORE_OPS launder -- their output is task data, never tainted. BINDING_OPS
    propagate -- tainted iff they reference a slot or consume a tainted value.
    """
    if step.op in CORE_OPS:
        return False
    if step.op not in BINDING_OPS:
        raise ValueError(f"unknown op '{step.op}' in step {step.id!r}")
    references_slot = bool(step.value_slots)
    consumes_tainted = any(inp in tainted_values for inp in step.inputs)
    return references_slot or consumes_tainted


def taint_map(skill: Skill) -> dict:
    """Propagate taint along def-use edges; return {step_id: output_tainted}.

    Steps are in dependency order by construction, so a single forward pass is a
    fixpoint. The environment-bound slots are the taint sources.
    """
    tainted_values: set = set()
    out: dict = {}
    for step in skill.steps:
        t = _output_tainted(step, tainted_values)
        out[step.id] = t
        if t:
            tainted_values.add(step.produces)
    return out


def classify(step: Step, tainted: bool | None = None) -> Unit:
    """Classify one step given whether its output is tainted.

    ``tainted`` comes from the whole-skill taint propagation in ``cut``. When
    called standalone (no dataflow context) it falls back to the step's own slot
    references, which is exact for every step except a binding op that is tainted
    only *transitively* through a binding chain.
    """
    if step.structural_slots:
        return Unit(
            step,
            Class.UNCLASSIFIABLE,
            f"control flow depends on environment constant(s) "
            f"{', '.join(step.structural_slots)}; neither pure core nor pure adapter",
        )
    if step.op in CORE_OPS:
        if step.value_slots:
            holes = ", ".join(step.value_slots)
            return Unit(
                step,
                Class.CORE,
                f"procedure-algebra op ('{step.op}') launders taint; adapter-bound "
                f"hole(s) {holes} are typed slots, the discipline is environment-agnostic",
            )
        return Unit(step, Class.CORE, f"pure discipline ('{step.op}') launders taint")
    if step.op not in BINDING_OPS:
        raise ValueError(f"unknown op '{step.op}' in step {step.id!r}")

    if tainted is None:
        tainted = bool(step.value_slots)
    if tainted:
        via = ", ".join(step.value_slots) if step.value_slots else "a tainted input (binding chain)"
        return Unit(step, Class.ADAPTER, f"output tainted -- binds {via}")
    return Unit(step, Class.CORE, "environment-independent binding (untainted)")


def cut(skill: Skill) -> List[Unit]:
    """Apply the decidable cut to every step, using taint propagation."""
    taint = taint_map(skill)
    return [classify(s, tainted=taint[s.id]) for s in skill.steps]


def core_mass(units: List[Unit]) -> float:
    """Fraction of *classifiable* units assigned to the frozen core."""
    classifiable = [u for u in units if u.cls is not Class.UNCLASSIFIABLE]
    if not classifiable:
        return 0.0
    core = sum(1 for u in classifiable if u.cls is Class.CORE)
    return core / len(classifiable)


def unclassifiable_fraction(units: List[Unit]) -> float:
    """Fraction of units the cut cannot statically classify (Section 6 metric)."""
    if not units:
        return 0.0
    return sum(1 for u in units if u.cls is Class.UNCLASSIFIABLE) / len(units)


# ---------------------------------------------------------------------------
# The Appendix A worked example: cohort-count clinical SQL.
#
#   "How many distinct patients were diagnosed with {condition}
#    within {N} days of admission?"
#
# The IR is identical for every site; environment constants are the slots.
# ---------------------------------------------------------------------------

_SLOTS = (
    Slot("VOCAB", "vocab", "diagnosis code vocabulary (e.g. ICD-9)", kind="implementation"),
    Slot("DX_TABLE", "table", "diagnoses table"),
    Slot("CODE_COL", "column", "diagnosis-code column on the diagnoses table"),
    Slot("ADM_TABLE", "table", "admissions table"),
    Slot("PATIENT_KEY", "column", "distinct-patient identifier"),
    Slot("TIME_EXPR", "column", "diagnosis-time column/expression"),
    Slot("WITHIN", "predicate", "within-N-days-of-admission dialect predicate", kind="implementation"),
)

_STEPS = (
    Step("resolve_codes", "resolve", "codes", value_slots=("VOCAB",),
         note="resolve the condition to codes in the site's vocabulary"),
    Step("pick_dx", "table", "dx", value_slots=("DX_TABLE",),
         note="select the diagnoses table"),
    Step("pick_adm", "table", "adm", value_slots=("ADM_TABLE",),
         note="select the admissions table"),
    Step("join", "join", "joined", value_slots=("PATIENT_KEY",), inputs=("dx", "adm"),
         note="join diagnoses to admissions on the patient key"),
    Step("filter_window", "filter", "filtered", value_slots=("WITHIN", "TIME_EXPR"),
         inputs=("joined",), note="keep diagnoses within N days of admission"),
    Step("dedup", "dedup", "uniq", value_slots=("PATIENT_KEY",), inputs=("filtered",),
         note="deduplicate to distinct patients (a patient has many rows)"),
    Step("count", "count_distinct", "n", value_slots=("PATIENT_KEY",), inputs=("uniq",),
         note="count distinct patients"),
    Step("sanity", "assert", "checked", value_slots=("PATIENT_KEY",), inputs=("n", "adm"),
         note="assert count <= number of admitted patients"),
)

_NL_SKETCH = """\
Resolve the condition to codes in the site vocabulary. Join the diagnoses table to
the admissions table on the patient key. Keep diagnoses within N days of admission.
Deduplicate to distinct patients (a patient may have many diagnosis rows). Count
distinct patients. Check the count does not exceed the number of admitted patients."""

COHORT_COUNT_SKILL = Skill(
    name="cohort_count",
    task_params=("condition", "N"),
    slots=_SLOTS,
    steps=_STEPS,
    nl_sketch=_NL_SKETCH,
)
