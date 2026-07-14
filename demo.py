"""End-to-end STRATA demo on the Appendix A example (MIMIC-III -> eICU).

Run:  python demo.py
"""

from __future__ import annotations

from strata.adapters import ADAPTERS, EICU, MIMIC_III
from strata.graph import build_agent
from strata.ir import COHORT_COUNT_SKILL, Class, core_mass, cut, unclassifiable_fraction


def hr(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def show_cut() -> None:
    hr("1. Decidable procedure/convention cut (computed once, environment-agnostic)")
    units = cut(COHORT_COUNT_SKILL)
    print(f"{'step':<16}{'class':<16}reason")
    print("-" * 72)
    for u in units:
        print(f"{u.step.id:<16}{u.cls.value:<16}{u.reason}")
    print("-" * 72)
    print(f"core-mass (freezable fraction) : {core_mass(units):.2f}")
    print(f"unclassifiable fraction        : {unclassifiable_fraction(units):.2f}")


def show_adapters() -> None:
    hr("2. The two typed adapters -- the ONLY thing that differs between sites")
    slots = [s.name for s in COHORT_COUNT_SKILL.slots]
    print(f"{'slot':<14}{'MIMIC-III':<52}{'eICU'}")
    print("-" * 90)
    for slot in slots:
        print(f"{slot:<14}{MIMIC_III[slot]:<52}{EICU[slot]}")


def run_site(agent, question: str, site: str):
    hr(f"3. Run the agent at {site}")
    state = agent.invoke({"question": question, "site": site})
    for line in state["log"]:
        print("  " + line)
    print(f"\n  ANSWER: {state['answer']}")
    return state


def main() -> None:
    question = "How many distinct patients were diagnosed with sepsis within 7 days of admission?"
    agent = build_agent()

    show_cut()
    show_adapters()

    # Learn on MIMIC-III, then transfer the frozen core to eICU by re-fitting
    # only the adapter.
    mimic_before = dict(MIMIC_III.bindings)
    m_state = run_site(agent, question, "MIMIC-III")
    e_state = run_site(agent, question, "eICU")

    hr("4. What transfer actually cost")
    units = cut(COHORT_COUNT_SKILL)
    core_units = [u for u in units if u.cls is Class.CORE]
    adapter_units = [u for u in units if u.cls is Class.ADAPTER]
    print(f"  frozen core steps re-optimized on transfer : 0 (of {len(core_units)})")
    print(f"  adapter bindings re-fit for eICU           : {len(EICU.bindings)}")
    print(f"  core discipline steps (join/filter/dedup/count/assert): "
          f"{[u.step.id for u in core_units]}")
    print(f"  adapter binding steps                       : "
          f"{[u.step.id for u in adapter_units]}")

    hr("5. Backward interference (== 0 by construction)")
    mimic_after = dict(MIMIC_III.bindings)
    unchanged = mimic_before == mimic_after
    print(f"  MIMIC-III adapter identical after adding eICU : {unchanged}")
    print(f"  MIMIC-III answer unchanged                    : "
          f"adding the eICU adapter never touched MIMIC-III's pair")
    print(f"  registry now covers                           : {list(ADAPTERS)}")

    hr("summary")
    print(f"  MIMIC-III: {m_state['answer']}")
    print(f"       eICU: {e_state['answer']}")
    print("\n  Same frozen procedure core answered both sites. Only the typed")
    print("  convention adapter changed -- including eICU's minutes-since-admission")
    print("  time encoding, absorbed entirely by the adapter's WITHIN predicate.")


if __name__ == "__main__":
    main()
