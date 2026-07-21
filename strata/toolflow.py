"""Cross-ecosystem tool workflow (Appendix B): GitHub -> Jira.

This is the interface-generalization domain -- the one that makes STRATA an
agent-skill theory rather than a text-to-SQL result. The task class:

    "File a tracking issue for a failing check and assign it to the code owner,
     without creating a duplicate."

The discipline is invariant: find-before-create (idempotency) and verify-after
(the created item is retrievable with the expected assignee). The *tool ecosystem*
is the environment instance. The interesting slot is FIND, a **typed-implementation
slot**: GitHub resolves a duplicate with a single search call, Jira with a
paginated JQL query -- structurally different code behind one signature
``(project, title) -> Optional[ref]``. The adapter absorbs that structural
difference while the core find-guard-create-verify discipline is frozen.

Everything runs in a sandbox (in-memory trackers), so idempotency and the
assignment contract are checked by execution, exactly as the SQL domain checks
the cohort count against SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from strata.ir import Skill, Slot, Step


# --- The two tool ecosystems (environment instances) ------------------------

@dataclass
class Issue:
    ref: str
    title: str
    body: str
    assignee: str


class Ecosystem:
    """Base in-memory issue tracker. Subclasses differ only in how FIND works."""

    kind = "base"

    def __init__(self) -> None:
        self.store: Dict[str, Issue] = {}
        self._n = 0
        self.find_calls = 0  # to show the two FIND implementations really differ

    def _new_ref(self) -> str:
        raise NotImplementedError

    def find(self, project: str, title: str) -> Optional[str]:
        raise NotImplementedError

    def create(self, project: str, title: str, body: str, assignee: str) -> str:
        ref = self._new_ref()
        self.store[ref] = Issue(ref, title, body, assignee)
        return ref

    def get(self, ref: str) -> Issue:
        return self.store[ref]

    def count_with_title(self, title: str) -> int:
        return sum(1 for i in self.store.values() if i.title == title)


class GitHubLike(Ecosystem):
    kind = "github"

    def _new_ref(self) -> str:
        self._n += 1
        return f"#{self._n}"

    def find(self, project: str, title: str) -> Optional[str]:
        # single search call over all issues
        self.find_calls += 1
        for issue in self.store.values():
            if issue.title == title:
                return issue.ref
        return None


class JiraLike(Ecosystem):
    kind = "jira"
    PAGE = 2

    def _new_ref(self) -> str:
        self._n += 1
        return f"{project_key()}-{self._n}"

    def find(self, project: str, title: str) -> Optional[str]:
        # paginated JQL search -- structurally different, same signature/result
        refs = list(self.store)
        for start in range(0, len(refs) or 1, self.PAGE):
            self.find_calls += 1
            for ref in refs[start:start + self.PAGE]:
                if self.store[ref].title == title:
                    return ref
        return None


def project_key() -> str:
    return "PK"


# --- The adapter: the only thing that changes between ecosystems ------------

@dataclass
class ToolAdapter:
    name: str
    project: str
    owner_src: str                 # OWNER_SRC binding (doc: CODEOWNERS vs component_lead)
    owner_map: Dict[str, str]      # component -> owner (the resolved convention)
    eco: Ecosystem = field(default_factory=Ecosystem)

    def resolve_owner(self, component: str) -> str:
        return self.owner_map[component]


def _seed_noise(eco: Ecosystem, n: int = 5) -> Ecosystem:
    """Pre-populate unrelated issues so the single-vs-paginated FIND difference shows."""
    for i in range(n):
        eco.create("_", f"unrelated-{i}", "", "system")
    eco.find_calls = 0  # count only the workflow's own searches
    return eco


def github_adapter() -> ToolAdapter:
    return ToolAdapter(
        name="GitHub", project="octo/repo", owner_src="CODEOWNERS",
        owner_map={"auth": "alice", "billing": "bob"}, eco=_seed_noise(GitHubLike()),
    )


def jira_adapter() -> ToolAdapter:
    return ToolAdapter(
        name="Jira", project="PK", owner_src="component_lead",
        owner_map={"auth": "alice@corp", "billing": "bob@corp"}, eco=_seed_noise(JiraLike()),
    )


# --- Frozen procedure core (identical across ecosystems) --------------------

@dataclass
class RunResult:
    ref: str
    created: bool


def run_workflow(adapter: ToolAdapter, component: str, title: str, body: str) -> RunResult:
    """The frozen core: resolve owner -> find -> guard(idempotency) -> create -> verify."""
    owner = adapter.resolve_owner(component)                 # adapter binding
    dup = adapter.eco.find(adapter.project, title)           # CORE find (impl varies)
    if dup is not None:                                      # CORE idempotency discipline
        return RunResult(dup, created=False)
    ref = adapter.eco.create(adapter.project, title, body, owner)  # CORE create
    assert adapter.eco.get(ref).assignee == owner            # CORE contract
    return RunResult(ref, created=True)


@dataclass
class VerifyResult:
    idempotent: bool
    assignee_ok: bool
    issue_count: int
    ok: bool
    message: str


def verify_idempotent(adapter: ToolAdapter, component: str, title: str, body: str) -> VerifyResult:
    """Run the workflow twice; the contract is: no duplicate, assignee correct."""
    r1 = run_workflow(adapter, component, title, body)
    r2 = run_workflow(adapter, component, title, body)
    owner = adapter.resolve_owner(component)
    count = adapter.eco.count_with_title(title)
    idempotent = (r1.ref == r2.ref) and r1.created and not r2.created
    assignee_ok = adapter.eco.get(r1.ref).assignee == owner
    ok = idempotent and assignee_ok and count == 1
    msg = (f"OK: one issue {r1.ref}, assignee correct, second call deduped"
           if ok else f"CONTRACT VIOLATION: count={count}, idempotent={idempotent}")
    return VerifyResult(idempotent, assignee_ok, count, ok, msg)


# --- The skill IR (same steps for both ecosystems) --------------------------

_SLOTS = (
    Slot("OWNER_SRC", "source", "where the code owner is resolved from"),
    Slot("PROJECT", "id", "the project/repo identifier"),
    Slot("FIND", "predicate", "duplicate finder, signature (project,title)->Option<ref>",
         kind="implementation"),
    Slot("CREATE", "predicate", "issue creator", kind="implementation"),
    Slot("GET", "predicate", "issue getter for the verify contract", kind="implementation"),
)

_STEPS = (
    Step("resolve_owner", "resolve_owner", "owner", value_slots=("OWNER_SRC",),
         note="resolve the code owner for the component"),
    Step("find_dup", "find", "dup", value_slots=("FIND", "PROJECT"),
         note="look for an existing issue with this title"),
    Step("guard", "guard", "decision", inputs=("dup",),
         note="idempotency: if a duplicate exists, return it and stop"),
    Step("create_issue", "create", "ref", value_slots=("CREATE", "PROJECT"),
         inputs=("owner", "decision"), note="create the issue assigned to the owner"),
    Step("verify", "assert", "checked", value_slots=("GET",), inputs=("ref", "owner"),
         note="contract: the created issue is retrievable with the expected assignee"),
)

TOOL_SKILL = Skill(
    name="file_tracking_issue",
    task_params=("component", "title", "body"),
    slots=_SLOTS,
    steps=_STEPS,
    nl_sketch=(
        "Resolve the code owner for the component. Search for an existing issue with "
        "the title; if one exists, return it (idempotency). Otherwise create the issue "
        "assigned to the owner, then verify it is retrievable with that assignee."
    ),
)


def transition_aware_skill(base: Skill = TOOL_SKILL) -> Skill:
    """Variant for the decidability limit: an ecosystem that needs create-then-transition.

    If one ecosystem creates an issue in a draft state that must then be transitioned
    to Open (a second control-flow step) while another creates it Open in one call,
    the create step's *shape* depends on the ecosystem -- neither core nor adapter.
    Declaring that makes the cut flag it unclassifiable instead of over-claiming it.
    """
    steps = tuple(
        Step(s.id, s.op, s.produces, s.value_slots, s.inputs,
             structural_slots=("CREATE_PROTOCOL",) if s.id == "create_issue" else s.structural_slots,
             note=s.note)
        for s in base.steps
    )
    slots = base.slots + (
        Slot("CREATE_PROTOCOL", "protocol", "one-call create vs create-then-transition",
             kind="contract"),
    )
    return Skill(base.name + "_transition_aware", base.task_params, slots, steps, base.nl_sketch)


def _main() -> None:
    from strata.ir import Class, core_mass, cut

    print("Cross-ecosystem tool workflow (Appendix B): file a tracking issue, no duplicate\n")
    units = cut(TOOL_SKILL)
    core = [u.step.id for u in units if u.cls is Class.CORE]
    adapt = [u.step.id for u in units if u.cls is Class.ADAPTER]
    print(f"decidable cut: core={core}")
    print(f"               adapter={adapt}")
    print(f"               core-mass={core_mass(units):.2f}\n")

    for make in (github_adapter, jira_adapter):
        adapter = make()
        res = verify_idempotent(adapter, "auth", "CI failing on main", "The build is red.")
        print(f"{adapter.name:<8} FIND={adapter.eco.kind} search  ->  {res.message}  "
              f"(find calls: {adapter.eco.find_calls})")

    print("\nSame frozen core (find-guard-create-verify) on both ecosystems; only the")
    print("adapter changes. FIND is a typed-implementation slot -- GitHub uses a single")
    print("search, Jira a paginated one (see the differing find-call counts) -- and the")
    print("adapter absorbs that structural difference while the idempotency discipline is")
    print("frozen and its contract holds on both.")

    ta = transition_aware_skill()
    flagged = [u.step.id for u in cut(ta) if u.cls is Class.UNCLASSIFIABLE]
    print(f"\nDecidability limit: an ecosystem needing create-then-transition makes the cut")
    print(f"flag {flagged} unclassifiable rather than forcing a 2-step shape into a 1-call slot.")


if __name__ == "__main__":
    _main()
