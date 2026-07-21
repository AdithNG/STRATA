"""Tests for the cross-ecosystem tool-workflow domain (Appendix B)."""

from strata.ir import Class, core_mass, cut
from strata.toolflow import (
    TOOL_SKILL,
    github_adapter,
    jira_adapter,
    run_workflow,
    transition_aware_skill,
    verify_idempotent,
)


def _labels(skill):
    return {u.step.id: u.cls for u in cut(skill)}


def test_cut_freezes_discipline_adapts_owner_source():
    labels = _labels(TOOL_SKILL)
    assert labels["resolve_owner"] is Class.ADAPTER
    for core_step in ("find_dup", "guard", "create_issue", "verify"):
        assert labels[core_step] is Class.CORE
    assert abs(core_mass(cut(TOOL_SKILL)) - 4 / 5) < 1e-9


def test_workflow_is_idempotent_on_both_ecosystems():
    for make in (github_adapter, jira_adapter):
        adapter = make()
        res = verify_idempotent(adapter, "auth", "CI failing on main", "red build")
        assert res.ok
        assert res.issue_count == 1
        assert res.idempotent and res.assignee_ok


def test_second_run_returns_existing_ref_not_a_duplicate():
    adapter = github_adapter()
    r1 = run_workflow(adapter, "auth", "flaky test", "x")
    r2 = run_workflow(adapter, "auth", "flaky test", "x")
    assert r1.created and not r2.created
    assert r1.ref == r2.ref


def test_find_implementation_differs_structurally():
    # Same frozen core, but GitHub does a single search and Jira paginates:
    # the typed-implementation FIND slot absorbs the structural difference.
    gh, jira = github_adapter(), jira_adapter()
    verify_idempotent(gh, "auth", "t", "b")
    verify_idempotent(jira, "auth", "t", "b")
    assert jira.eco.find_calls > gh.eco.find_calls


def test_owner_binding_is_environment_specific():
    # The one adapter unit really is convention-bound: the two ecosystems resolve
    # different owners for the same component.
    assert github_adapter().resolve_owner("auth") != jira_adapter().resolve_owner("auth")


def test_create_then_transition_is_decidability_limit():
    labels = _labels(transition_aware_skill())
    assert labels["create_issue"] is Class.UNCLASSIFIABLE
    # base skill has no unclassifiable units; the variant introduces exactly one
    assert not any(u.cls is Class.UNCLASSIFIABLE for u in cut(TOOL_SKILL))
