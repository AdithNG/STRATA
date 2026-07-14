"""The STRATA LangGraph agent.

The graph wires the STRATA mechanism into an executable agent:

    parse_task -> apply_cut -> bind_adapter -> compile -> execute_verify -> respond
                                                                    |
                                                                    +--> flag (sanity failed)

`apply_cut` runs the *decidable* procedure/convention cut once; `bind_adapter`
selects the typed adapter for the target environment; `compile` composes the
frozen core with that adapter; `execute_verify` runs the SQL and enforces the
core's sanity check. Re-targeting to a new site changes only which adapter
`bind_adapter` picks -- the core, the cut, and every other node are unchanged.
"""

from __future__ import annotations

import operator
import sqlite3
from typing import Annotated, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from strata import db, loader
from strata.adapters import Adapter
from strata.compiler import CompiledSQL, compile_sql
from strata.ir import Class, Skill, Unit, core_mass, cut
from strata.nlu import parse_question
from strata.verifier import Result, verify


class AgentState(TypedDict, total=False):
    question: str
    site: str
    condition: str
    n_days: int
    units: List[Unit]
    core_mass: float
    adapter: Adapter
    compiled: CompiledSQL
    result: Result
    answer: str
    log: Annotated[List[str], operator.add]


def _connect(state: AgentState) -> sqlite3.Connection:
    """Open a fresh database for the target site (in-memory fixture)."""
    return db.connect(state["site"])


def build_agent(skill: Skill | None = None):
    """Compile and return the STRATA agent graph for a given (frozen) skill.

    Defaults to the loader's default skill (from ``skills/*.json`` when present,
    else the hardcoded fallback).
    """
    if skill is None:
        skill = loader.DEFAULT_SKILL

    def parse_task(state: AgentState) -> AgentState:
        condition, n_days = parse_question(state["question"])
        return {
            "condition": condition,
            "n_days": n_days,
            "log": [f"parse_task: condition={condition!r}, N={n_days}"],
        }

    def apply_cut(state: AgentState) -> AgentState:
        units = cut(skill)
        cm = core_mass(units)
        core = [u.step.id for u in units if u.cls is Class.CORE]
        adapt = [u.step.id for u in units if u.cls is Class.ADAPTER]
        unclass = [u.step.id for u in units if u.cls is Class.UNCLASSIFIABLE]
        log = [
            f"apply_cut: core={core}",
            f"apply_cut: adapter={adapt}",
            f"apply_cut: core_mass={cm:.2f}"
            + (f", unclassifiable={unclass}" if unclass else ""),
        ]
        return {"units": units, "core_mass": cm, "log": log}

    def bind_adapter(state: AgentState) -> AgentState:
        site = state["site"]
        if site not in loader.ADAPTERS:
            raise KeyError(f"no adapter fitted for environment {site!r}")
        adapter = loader.ADAPTERS[site]
        return {
            "adapter": adapter,
            "log": [f"bind_adapter: {site} -> {dict(adapter.bindings)}"],
        }

    def compile_node(state: AgentState) -> AgentState:
        compiled = compile_sql(
            skill, state["adapter"], state["condition"], state["n_days"]
        )
        return {
            "compiled": compiled,
            "log": [f"compile: {compiled.main_sql.splitlines()[0]} ... (codes={compiled.params})"],
        }

    def execute_verify(state: AgentState) -> AgentState:
        conn = _connect(state)
        try:
            result = verify(conn, state["compiled"])
        finally:
            conn.close()
        return {"result": result, "log": [f"execute_verify: {result.message}"]}

    def respond(state: AgentState) -> AgentState:
        r = state["result"]
        answer = (
            f"{r.count} distinct patients were diagnosed with "
            f"{state['condition']} within {state['n_days']} days of admission "
            f"at {state['site']}."
        )
        return {"answer": answer, "log": [f"respond: {answer}"]}

    def flag(state: AgentState) -> AgentState:
        r = state["result"]
        answer = (
            f"REFUSED at {state['site']}: {r.message}. The frozen core's sanity "
            f"check failed, which indicates an adapter binding is wrong -- the "
            f"procedure discipline itself is verified and never re-fit."
        )
        return {"answer": answer, "log": [f"flag: {answer}"]}

    def route(state: AgentState) -> str:
        return "respond" if state["result"].ok else "flag"

    g = StateGraph(AgentState)
    g.add_node("parse_task", parse_task)
    g.add_node("apply_cut", apply_cut)
    g.add_node("bind_adapter", bind_adapter)
    g.add_node("compile", compile_node)
    g.add_node("execute_verify", execute_verify)
    g.add_node("respond", respond)
    g.add_node("flag", flag)

    g.add_edge(START, "parse_task")
    g.add_edge("parse_task", "apply_cut")
    g.add_edge("apply_cut", "bind_adapter")
    g.add_edge("bind_adapter", "compile")
    g.add_edge("compile", "execute_verify")
    g.add_conditional_edges("execute_verify", route, {"respond": "respond", "flag": "flag"})
    g.add_edge("respond", END)
    g.add_edge("flag", END)
    return g.compile()


def run(question: str, site: str) -> AgentState:
    """Convenience one-shot runner."""
    agent = build_agent()
    return agent.invoke({"question": question, "site": site})
